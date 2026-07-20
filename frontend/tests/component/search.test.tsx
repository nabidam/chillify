import { QueryClient } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it, vi } from "vitest";
import { AppProviders } from "@/app/AppProviders";
import { ACTIVE_PROFILE_STORAGE_KEY } from "@/app/activeProfile";
import { routes } from "@/app/routes";
import {
  profileFixture,
  remoteResultFixture,
  systemStatusFixture,
  trackSummaryFixture,
} from "../msw/handlers";
import { server } from "../msw/server";

function renderSearch() {
  window.localStorage.setItem(ACTIVE_PROFILE_STORAGE_KEY, profileFixture().id);
  window.history.replaceState(null, "", routes.search);
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  });
  return render(<AppProviders queryClient={queryClient} />);
}

describe("S3 local-first search", () => {
  it("never contacts Deezer while the person is typing", async () => {
    const online = vi.fn(() => HttpResponse.json({ items: [], next_cursor: null }));
    server.use(http.get("/api/v1/search/deezer", online));
    renderSearch();

    await userEvent.type(await screen.findByLabelText("Track or artist"), "daft punk");

    await waitFor(() => expect(screen.getByText(/In your library/)).toBeTruthy());
    expect(online).not.toHaveBeenCalled();
    expect(screen.getByText(/Nothing has been sent to Deezer/)).toBeTruthy();
  });

  it("contacts Deezer only when the explicit action is used", async () => {
    const online = vi.fn(() =>
      HttpResponse.json({ items: [remoteResultFixture()], next_cursor: null }),
    );
    server.use(http.get("/api/v1/search/deezer", online));
    renderSearch();

    await userEvent.type(await screen.findByLabelText("Track or artist"), "daft punk");
    await userEvent.click(screen.getByRole("button", { name: "Search Deezer" }));

    expect(await screen.findByText("Harder Better Faster Stronger")).toBeTruthy();
    expect(online).toHaveBeenCalledTimes(1);
  });

  it("keeps local results usable while pointing at the online action", async () => {
    server.use(
      http.get("/api/v1/library/tracks", () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
    );
    renderSearch();

    await userEvent.type(await screen.findByLabelText("Track or artist"), "unknown");

    expect(await screen.findByText("No local matches")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Search Deezer" })).toBeTruthy();
  });
});

describe("S3 internet results", () => {
  it("offers Download and never offers Play", async () => {
    renderSearch();

    await userEvent.type(await screen.findByLabelText("Track or artist"), "daft");
    await userEvent.click(screen.getByRole("button", { name: "Search Deezer" }));

    expect(
      await screen.findByRole("button", { name: "Download Harder Better Faster Stronger" }),
    ).toBeTruthy();
    expect(screen.queryByRole("button", { name: /^Play Harder Better/ })).toBeNull();
  });

  it("links a duplicate to the local track instead of downloading it again", async () => {
    server.use(
      http.get("/api/v1/search/deezer", () =>
        HttpResponse.json({
          items: [remoteResultFixture({ existing_track_id: trackSummaryFixture().id })],
          next_cursor: null,
        }),
      ),
    );
    renderSearch();

    await userEvent.type(await screen.findByLabelText("Track or artist"), "daft");
    await userEvent.click(screen.getByRole("button", { name: "Search Deezer" }));

    expect(await screen.findByRole("link", { name: /Already in your library/ })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /^Download/ })).toBeNull();
  });

  it("queues a download and acknowledges it", async () => {
    renderSearch();

    await userEvent.type(await screen.findByLabelText("Track or artist"), "daft");
    await userEvent.click(screen.getByRole("button", { name: "Search Deezer" }));
    await userEvent.click(
      await screen.findByRole("button", { name: "Download Harder Better Faster Stronger" }),
    );

    expect(await screen.findByText("Queued for download")).toBeTruthy();
  });

  it("reports a refused download without losing the results", async () => {
    server.use(
      http.post("/api/v1/downloads", () =>
        HttpResponse.json(
          {
            error: {
              code: "duplicate_record",
              message: "That track is already queued or downloading.",
              field: null,
              retryable: false,
              request_id: "test",
              detail: {},
            },
          },
          { status: 409 },
        ),
      ),
    );
    renderSearch();

    await userEvent.type(await screen.findByLabelText("Track or artist"), "daft");
    await userEvent.click(screen.getByRole("button", { name: "Search Deezer" }));
    await userEvent.click(
      await screen.findByRole("button", { name: "Download Harder Better Faster Stronger" }),
    );

    expect(
      await screen.findByText("That track is already queued or downloading."),
    ).toBeTruthy();
    expect(screen.getByText("Harder Better Faster Stronger")).toBeTruthy();
  });

  it("explains a provider failure and keeps local results readable", async () => {
    server.use(
      http.get("/api/v1/search/deezer", () =>
        HttpResponse.json(
          {
            error: {
              code: "proxy_connection_failed",
              message: "Could not reach Deezer through the configured proxy.",
              field: null,
              retryable: true,
              request_id: "test",
              detail: { provider: "deezer" },
            },
          },
          { status: 503 },
        ),
      ),
    );
    renderSearch();

    await userEvent.type(await screen.findByLabelText("Track or artist"), "daft");
    await userEvent.click(screen.getByRole("button", { name: "Search Deezer" }));

    expect(await screen.findByText("Deezer could not be searched")).toBeTruthy();
    expect(
      screen.getByText("Could not reach Deezer through the configured proxy."),
    ).toBeTruthy();
    expect(screen.getByText("Hoppipolla")).toBeTruthy();
  });

  it("allows discovery but disables Download while the queue is unreachable", async () => {
    server.use(
      http.get("/api/v1/system/status", () =>
        HttpResponse.json(
          systemStatusFixture({
            degraded: true,
            redis: { name: "redis", health: "unavailable", detail: "unreachable" },
          }),
        ),
      ),
    );
    renderSearch();

    await userEvent.type(await screen.findByLabelText("Track or artist"), "daft");
    await userEvent.click(screen.getByRole("button", { name: "Search Deezer" }));

    const download = await screen.findByRole("button", {
      name: "Download Harder Better Faster Stronger",
    });
    expect(download.hasAttribute("disabled")).toBe(true);
    expect(screen.getByText("Downloads are paused")).toBeTruthy();
  });
});
