import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import type { components } from "@/api/generated";
import { InspectionSettingsCard } from "@/features/settings/InspectionSettingsCard";
import { server } from "../msw/server";

type Settings = components["schemas"]["SettingsModel"];

function settingsFixture(overrides: Partial<Settings> = {}): Settings {
  return {
    proxy: { configured: false, scheme: null, host: null, masked_url: null, revision: 1 },
    providers: [],
    inspection: {
      mode: "fast",
      timeout_spotify_s: 8,
      timeout_spotdl_s: 150,
      timeout_ytdlp_s: 60,
      revision: 1,
    },
    spotify_api: { configured: false, revision: 1 },
    ...overrides,
  };
}

function renderCard(settings: Settings = settingsFixture()) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <InspectionSettingsCard
        inspection={settings.inspection}
        spotifyApi={settings.spotify_api}
      />
    </QueryClientProvider>,
  );
}

function serveSettings(initial = settingsFixture()) {
  let current = initial;
  const credentialBodies: unknown[] = [];
  const inspectionBodies: unknown[] = [];

  server.use(
    http.get("/api/v1/settings", () => HttpResponse.json(current)),
    http.patch("/api/v1/settings/providers/spotify_api", async ({ request }) => {
      const body = (await request.json()) as {
        clear_secret?: boolean;
        client_id?: string;
        client_secret?: string;
      };
      credentialBodies.push(body);
      current = {
        ...current,
        spotify_api: {
          configured: !body.clear_secret,
          revision: current.spotify_api.revision + 1,
        },
      };
      return HttpResponse.json(current.spotify_api);
    }),
    http.patch("/api/v1/settings/inspection", async ({ request }) => {
      const body = (await request.json()) as Settings["inspection"];
      inspectionBodies.push(body);
      current = {
        ...current,
        inspection: { ...body },
      };
      return HttpResponse.json(current.inspection);
    }),
  );

  return { credentialBodies, inspectionBodies };
}

afterEach(() => server.resetHandlers());

const originalScrollIntoView = Element.prototype.scrollIntoView;

beforeAll(() => {
  Element.prototype.scrollIntoView = () => {};
});

afterAll(() => {
  Element.prototype.scrollIntoView = originalScrollIntoView;
});

describe("S12 link inspection settings", () => {
  it("saves credentials without echoing the secret, then clears them", async () => {
    const requests = serveSettings();
    const user = userEvent.setup();
    renderCard();

    await user.type(await screen.findByLabelText("Client ID"), "client-id");
    await user.type(screen.getByLabelText("Client secret"), "sentinel-secret");
    await user.click(screen.getByRole("button", { name: "Save credentials" }));

    await waitFor(() => expect(screen.getByText(/Configured\./)).toBeTruthy());
    expect(requests.credentialBodies).toEqual([
      {
        client_id: "client-id",
        client_secret: "sentinel-secret",
        clear_secret: false,
        revision: 1,
      },
    ]);
    expect(screen.queryByDisplayValue("sentinel-secret")).toBeNull();
    expect(screen.queryByText("sentinel-secret")).toBeNull();

    await user.click(screen.getByRole("button", { name: "Clear credentials" }));

    await waitFor(() => expect(screen.getByText(/Not configured\./)).toBeTruthy());
    expect(requests.credentialBodies[1]).toEqual({ clear_secret: true, revision: 2 });
    expect(screen.getByText(/Spotify links use SpotDL instead/)).toBeTruthy();
  });

  it("persists the selected mode and all three timeout values", async () => {
    const requests = serveSettings();
    const user = userEvent.setup();
    renderCard();

    const mode = screen.getByRole("combobox", { name: "Mode" });
    mode.focus();
    await user.keyboard("{ArrowDown}");
    await user.click(await screen.findByRole("option", { name: /Thorough/ }));
    await user.clear(screen.getByLabelText("Spotify API timeout"));
    await user.type(screen.getByLabelText("Spotify API timeout"), "12");
    await user.clear(screen.getByLabelText("SpotDL timeout"));
    await user.type(screen.getByLabelText("SpotDL timeout"), "240");
    await user.click(screen.getByRole("button", { name: "Save inspection settings" }));

    await waitFor(() => expect(requests.inspectionBodies).toHaveLength(1));
    expect(requests.inspectionBodies[0]).toEqual({
      mode: "thorough",
      timeout_spotify_s: 12,
      timeout_spotdl_s: 240,
      timeout_ytdlp_s: 60,
      revision: 1,
    });
  });

  it("rejects an out-of-range timeout at the field without saving", async () => {
    const requests = serveSettings();
    const user = userEvent.setup();
    renderCard();

    const spotifyTimeout = screen.getByLabelText("Spotify API timeout");
    await user.clear(spotifyTimeout);
    await user.type(spotifyTimeout, "31");
    await user.click(screen.getByRole("button", { name: "Save inspection settings" }));

    expect(await screen.findByText("Enter a whole number from 1 to 30 seconds.")).toBeTruthy();
    expect(spotifyTimeout.getAttribute("aria-invalid")).toBe("true");
    expect(requests.inspectionBodies).toEqual([]);
  });
});
