import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AddLinkDialog } from "@/features/acquisition/AddLinkDialog";
import type { LinkInspection } from "@/features/acquisition/acquisitionQueries";
import { server } from "../msw/server";

class FakeEventSource {
  static instances: FakeEventSource[] = [];
  readonly url: string;
  readonly listeners = new Map<string, (event: Event) => void>();
  readonly close = vi.fn();

  constructor(url: string) {
    this.url = url;
    FakeEventSource.instances.push(this);
  }

  addEventListener(name: string, listener: (event: Event) => void) {
    this.listeners.set(name, listener);
  }

  emit(name: string, data: unknown) {
    this.listeners.get(name)?.(new MessageEvent(name, { data: JSON.stringify(data) }));
  }
}

const inspectedTrack: LinkInspection = {
  source_type: "spotify_track",
  provider: "spotdl",
  review_required: false,
  is_playable: false,
  existing_track_id: null,
  candidate: {
    provider: "spotdl",
    source_id: "2cGxRwrMyEAp8dEbuZaVv6",
    source_url: "https://open.spotify.com/track/2cGxRwrMyEAp8dEbuZaVv6",
    title: "Hoppípolla",
    artist: "Sigur Rós",
    album: "Takk...",
    release_year: 2005,
    disc_number: 1,
    track_number: 4,
    duration_ms: 268000,
    isrc: null,
    artwork_url: null,
    acquisition_locator: "spotify:track:2cGxRwrMyEAp8dEbuZaVv6",
    raw_fingerprint: null,
  },
};

function renderDialog() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <AddLinkDialog open onOpenChange={vi.fn()} />
    </QueryClientProvider>,
  );
}

function serveAccepted() {
  server.use(
    http.post("/api/v1/links/inspect", () =>
      HttpResponse.json(
        {
          inspection_id: "inspection-1",
          phase: "reading_spotify",
          started_at: "2026-07-29T10:00:00.000Z",
        },
        { status: 202 },
      ),
    ),
  );
}

async function activeStream() {
  return waitFor(() => {
    const stream = FakeEventSource.instances[0];
    if (!stream) {
      throw new Error("inspection stream was not opened");
    }
    return stream;
  });
}

describe("S4 inspection feedback", () => {
  beforeEach(() => {
    FakeEventSource.instances = [];
    vi.stubGlobal("EventSource", FakeEventSource);
    serveAccepted();
  });

  afterEach(() => {
    vi.stubGlobal("EventSource", undefined);
  });

  it("shows named phases and a rising elapsed value without percentage progress", async () => {
    renderDialog();
    await userEvent.type(
      screen.getByLabelText("Link"),
      "https://open.spotify.com/track/example",
    );
    await userEvent.click(screen.getByRole("button", { name: "Continue" }));

    expect(await screen.findByText("Reading Spotify details")).toBeTruthy();
    const stream = await activeStream();
    act(() => {
      stream.emit("inspection.changed", {
        phase: "matching_spotdl",
        elapsed_ms: 1200,
        provider: "spotdl",
        terminal: false,
      });
    });

    expect(await screen.findByText("Matching with SpotDL")).toBeTruthy();
    expect(screen.getByText("1.2 seconds elapsed")).toBeTruthy();
    expect((screen.getByRole("button", { name: "Cancel" }) as HTMLButtonElement).disabled).toBe(
      false,
    );
    expect(document.body.textContent).not.toContain("%");
  });

  it("keeps elapsed time across the SpotDL fallback and preserves input on cancel", async () => {
    server.use(
      http.delete(
        "/api/v1/links/inspect/:inspectionId",
        () => new HttpResponse(null, { status: 204 }),
      ),
    );
    renderDialog();
    const input = screen.getByLabelText("Link");
    await userEvent.type(input, "https://open.spotify.com/track/fallback");
    await userEvent.click(screen.getByRole("button", { name: "Continue" }));
    const stream = await activeStream();
    act(() => {
      stream.emit("inspection.changed", {
        phase: "reading_spotify",
        elapsed_ms: 800,
        provider: "spotify_api",
        terminal: false,
      });
      stream.emit("inspection.changed", {
        phase: "matching_spotdl",
        elapsed_ms: 2400,
        provider: "spotdl",
        terminal: false,
      });
    });

    expect(await screen.findByText("Matching with SpotDL")).toBeTruthy();
    expect(screen.getByText("2.4 seconds elapsed")).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));

    await waitFor(() => expect((input as HTMLInputElement).disabled).toBe(false));
    expect((input as HTMLInputElement).value).toBe("https://open.spotify.com/track/fallback");
    expect(stream.close).toHaveBeenCalled();
  });

  it("renders expiry as its own terminal state", async () => {
    renderDialog();
    const input = screen.getByLabelText("Link");
    await userEvent.type(input, "https://open.spotify.com/track/expired");
    await userEvent.click(screen.getByRole("button", { name: "Continue" }));
    const stream = await activeStream();
    act(() => {
      stream.emit("inspection.changed", {
        phase: "expired",
        elapsed_ms: 300000,
        provider: "spotify_api",
        terminal: true,
        error: { code: "inspection_expired", message: "This inspection expired. Try again." },
      });
    });

    expect(await screen.findByText("Inspection expired")).toBeTruthy();
    expect(screen.queryByText("Inspection failed")).toBeNull();
    expect((input as HTMLInputElement).disabled).toBe(false);
  });

  it("hands a completed Spotify result back to the existing download action", async () => {
    renderDialog();
    await userEvent.type(screen.getByLabelText("Link"), "https://open.spotify.com/track/done");
    await userEvent.click(screen.getByRole("button", { name: "Continue" }));
    const stream = await activeStream();
    act(() => {
      stream.emit("inspection.changed", {
        phase: "done",
        elapsed_ms: 1800,
        provider: "spotdl",
        terminal: true,
        result: inspectedTrack,
      });
    });

    expect(await screen.findByText("Hoppípolla")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Download" })).toBeTruthy();
  });
});
