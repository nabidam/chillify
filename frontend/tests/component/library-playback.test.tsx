import { QueryClient } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import { AppProviders } from "@/app/AppProviders";
import { ACTIVE_PROFILE_STORAGE_KEY } from "@/app/activeProfile";
import { usePlayerStore } from "@/features/player/playerStore";
import { profileFixture, trackSummaryFixture } from "../msw/handlers";
import { server } from "../msw/server";

function renderShell() {
  window.localStorage.setItem(ACTIVE_PROFILE_STORAGE_KEY, profileFixture().id);
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  });
  return render(<AppProviders queryClient={queryClient} />);
}

beforeEach(() => {
  usePlayerStore.getState().clearSession();
  usePlayerStore.setState({ unplayableTrackIds: [] });
});

describe("S2 library listing", () => {
  it("lists a local track with its metadata", async () => {
    renderShell();

    expect(await screen.findByText("Hoppipolla")).toBeTruthy();
    expect(screen.getByText("Sigur Rós")).toBeTruthy();
    expect(screen.getByText("Takk...")).toBeTruthy();
    expect(screen.getByText("4:28")).toBeTruthy();
  });

  it("explains the managed-download model when the library is empty", async () => {
    server.use(
      http.get("/api/v1/library/tracks", () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
    );
    renderShell();

    expect(await screen.findByText("No tracks yet")).toBeTruthy();
    expect(screen.getByText(/only the tracks it downloaded and manages/i)).toBeTruthy();
  });

  it("offers a retry on a failed library read without hiding the player", async () => {
    server.use(
      http.get("/api/v1/library/tracks", () => HttpResponse.json({}, { status: 503 })),
    );
    renderShell();

    expect(await screen.findByText("Your library could not be loaded")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Retry" })).toBeTruthy();
    expect(screen.getByLabelText("Player")).toBeTruthy();
  });

  it("keeps an unavailable row readable and disables only its Play action", async () => {
    server.use(
      http.get("/api/v1/library/tracks", () =>
        HttpResponse.json({
          items: [
            trackSummaryFixture({
              title: "Glósóli",
              availability: "missing",
              is_playable: false,
            }),
          ],
          next_cursor: null,
        }),
      ),
    );
    renderShell();

    expect(await screen.findByText("Glósóli")).toBeTruthy();
    expect(screen.getByText("File missing")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Play Glósóli" }).hasAttribute("disabled")).toBe(
      true,
    );
  });
});

describe("persistent playback", () => {
  it("plays a row, loads its stream, and shows it in the player", async () => {
    const user = userEvent.setup();
    renderShell();

    await user.click(await screen.findByRole("button", { name: "Play Hoppipolla" }));

    const audio = document.querySelector("audio");
    await waitFor(() => {
      expect(audio?.getAttribute("src")).toBe(
        `/api/v1/tracks/${trackSummaryFixture().id}/stream`,
      );
    });
    const player = screen.getByLabelText("Player");
    expect(player.textContent).toContain("Hoppipolla");
    expect(screen.getByRole("button", { name: "Pause" })).toBeTruthy();
  });

  it("queues the rest of the view in order, starting at the clicked row", async () => {
    const user = userEvent.setup();
    const second = trackSummaryFixture({ id: "second-track", title: "Sæglópur" });
    server.use(
      http.get("/api/v1/library/tracks", () =>
        HttpResponse.json({
          items: [trackSummaryFixture(), second],
          next_cursor: null,
        }),
      ),
    );
    renderShell();

    await user.click(await screen.findByRole("button", { name: "Play Sæglópur" }));

    const state = usePlayerStore.getState();
    expect(state.queue).toEqual([trackSummaryFixture().id, "second-track"]);
    expect(state.currentIndex).toBe(1);
  });

  it("keeps the audio element mounted across a route change", async () => {
    const user = userEvent.setup();
    renderShell();

    await user.click(await screen.findByRole("button", { name: "Play Hoppipolla" }));
    const audio = document.querySelector("audio");

    await user.click(screen.getByRole("link", { name: "Downloads" }));
    await screen.findByRole("heading", { name: "Downloads" });

    expect(document.querySelector("audio")).toBe(audio);
    expect(usePlayerStore.getState().isPlaying).toBe(true);
  });

  it("pauses and resumes without changing the loaded track", async () => {
    const user = userEvent.setup();
    renderShell();

    await user.click(await screen.findByRole("button", { name: "Play Hoppipolla" }));
    await user.click(await screen.findByRole("button", { name: "Pause" }));

    expect(usePlayerStore.getState().isPlaying).toBe(false);
    expect(screen.getByRole("button", { name: "Play" })).toBeTruthy();
    expect(usePlayerStore.getState().queue).toHaveLength(1);
  });

  it("says nothing is playing and disables transport before a track is chosen", async () => {
    renderShell();

    const player = await screen.findByLabelText("Player");
    expect(player.textContent).toContain("Nothing is playing");
    expect(screen.getByRole("button", { name: "Play" }).hasAttribute("disabled")).toBe(true);
    expect(screen.getByRole("button", { name: "Next track" }).hasAttribute("disabled")).toBe(
      true,
    );
  });

  it("skips a track whose audio fails and marks it unplayable for the session", async () => {
    const user = userEvent.setup();
    const second = trackSummaryFixture({ id: "second-track", title: "Sæglópur" });
    server.use(
      http.get("/api/v1/library/tracks", () =>
        HttpResponse.json({ items: [trackSummaryFixture(), second], next_cursor: null }),
      ),
    );
    renderShell();

    await user.click(await screen.findByRole("button", { name: "Play Hoppipolla" }));
    document.querySelector("audio")?.dispatchEvent(new Event("error"));

    await waitFor(() => {
      expect(usePlayerStore.getState().currentIndex).toBe(1);
    });
    expect(usePlayerStore.getState().unplayableTrackIds).toContain(trackSummaryFixture().id);
  });
});
