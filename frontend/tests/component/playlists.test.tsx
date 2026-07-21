import { QueryClient } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import { AppProviders } from "@/app/AppProviders";
import { ACTIVE_PROFILE_STORAGE_KEY } from "@/app/activeProfile";
import { usePlayerStore } from "@/features/player/playerStore";
import { playlistFixture, profileFixture, trackSummaryFixture } from "../msw/handlers";
import { server } from "../msw/server";

function renderAt(path: string) {
  window.localStorage.setItem(ACTIVE_PROFILE_STORAGE_KEY, profileFixture().id);
  window.history.replaceState(null, "", path);
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  });
  return render(<AppProviders queryClient={queryClient} />);
}

beforeEach(() => {
  usePlayerStore.getState().clearSession();
});

/** The first match, asserted to exist so strict indexing stays honest. */
function first<Item>(items: Item[]): Item {
  const item = items[0];
  if (item === undefined) {
    throw new Error("expected at least one match");
  }
  return item;
}

describe("S9 playlists", () => {
  it("states that playlists belong to the active profile when there are none", async () => {
    renderAt("/playlists");

    expect(await screen.findByText("No playlists yet")).toBeTruthy();
    expect(screen.getByText(/belong to the profile that is currently active/i)).toBeTruthy();
    expect(screen.getAllByRole("button", { name: /create playlist/i }).length).toBeGreaterThan(
      0,
    );
  });

  it("lists a playlist with its track count", async () => {
    server.use(
      http.get("/api/v1/profiles/:profileId/playlists", () =>
        HttpResponse.json({
          items: [playlistFixture({ track_count: 3 })],
          next_cursor: null,
        }),
      ),
    );
    renderAt("/playlists");

    expect(await screen.findByText(/3 tracks/)).toBeTruthy();
    // Once in the list and once as a sidebar shortcut: both are real entry
    // points to the same playlist.
    expect(screen.getAllByText("Sunday Morning").length).toBe(2);
  });

  it("keeps the heading and the create action on a failed read", async () => {
    server.use(
      http.get("/api/v1/profiles/:profileId/playlists", () =>
        HttpResponse.json({}, { status: 503 }),
      ),
    );
    renderAt("/playlists");

    expect(await screen.findByText("Your playlists could not be loaded")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Playlists" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Retry" })).toBeTruthy();
  });
});

describe("S16 playlist editor", () => {
  it("creates a playlist from the entered name", async () => {
    const submitted: Array<{ name: string }> = [];
    server.use(
      http.post("/api/v1/profiles/:profileId/playlists", async ({ request }) => {
        submitted.push((await request.json()) as { name: string });
        return HttpResponse.json(playlistFixture({ name: "Road Trip" }), { status: 201 });
      }),
    );
    const user = userEvent.setup();
    renderAt("/playlists");

    await user.click(first(await screen.findAllByRole("button", { name: /create playlist/i })));
    await user.type(await screen.findByLabelText("Name"), "Road Trip");
    await user.click(screen.getByRole("button", { name: "Create" }));

    await waitFor(() => expect(submitted).toEqual([{ name: "Road Trip" }]));
  });

  it("keeps Create disabled while the name is blank", async () => {
    const user = userEvent.setup();
    renderAt("/playlists");

    await user.click(first(await screen.findAllByRole("button", { name: /create playlist/i })));
    const create = await screen.findByRole("button", { name: "Create" });

    expect(create.hasAttribute("disabled")).toBe(true);
  });

  it("preserves the typed name and shows the conflict when the name is taken", async () => {
    server.use(
      http.post("/api/v1/profiles/:profileId/playlists", () =>
        HttpResponse.json(
          {
            error: {
              code: "duplicate_record",
              message: "This profile already has a playlist with that name.",
              field: "name",
              retryable: false,
              request_id: "test",
              detail: {},
            },
          },
          { status: 409 },
        ),
      ),
    );
    const user = userEvent.setup();
    renderAt("/playlists");

    await user.click(first(await screen.findAllByRole("button", { name: /create playlist/i })));
    const nameField = await screen.findByLabelText("Name");
    await user.type(nameField, "Sunday Morning");
    await user.click(screen.getByRole("button", { name: "Create" }));

    expect(
      await screen.findByText("This profile already has a playlist with that name."),
    ).toBeTruthy();
    expect((nameField as HTMLInputElement).value).toBe("Sunday Morning");
  });
});

describe("S10 playlist detail", () => {
  const playlist = playlistFixture({ track_count: 1 });

  function servePlaylistDetail(tracks = [trackSummaryFixture()]) {
    server.use(
      http.get("/api/v1/playlists/:playlistId", () =>
        HttpResponse.json({ playlist: { ...playlist, track_count: tracks.length }, tracks }),
      ),
    );
  }

  it("plays the saved order from the first track", async () => {
    const second = trackSummaryFixture({ id: "track-2", title: "Glosoli" });
    servePlaylistDetail([trackSummaryFixture(), second]);
    const user = userEvent.setup();
    renderAt(`/playlists/${playlist.id}`);

    await user.click(await screen.findByRole("button", { name: /play playlist/i }));

    await waitFor(() => {
      const state = usePlayerStore.getState();
      expect(state.queue).toEqual([trackSummaryFixture().id, "track-2"]);
      expect(state.currentIndex).toBe(0);
    });
  });

  it("never queues a track whose file is missing", async () => {
    servePlaylistDetail([
      trackSummaryFixture({ id: "gone", is_playable: false, availability: "missing" }),
      trackSummaryFixture({ id: "playable" }),
    ]);
    const user = userEvent.setup();
    renderAt(`/playlists/${playlist.id}`);

    await user.click(await screen.findByRole("button", { name: /play playlist/i }));

    await waitFor(() => expect(usePlayerStore.getState().queue).toEqual(["playable"]));
  });

  it("disables Play Playlist when nothing in it can start", async () => {
    servePlaylistDetail([
      trackSummaryFixture({ id: "gone", is_playable: false, availability: "missing" }),
    ]);
    renderAt(`/playlists/${playlist.id}`);

    const play = await screen.findByRole("button", { name: /play playlist/i });
    await waitFor(() => expect(play.hasAttribute("disabled")).toBe(true));
  });

  it("explains how to fill an empty playlist", async () => {
    servePlaylistDetail([]);
    renderAt(`/playlists/${playlist.id}`);

    expect(await screen.findByText("Nothing in this playlist yet")).toBeTruthy();
    expect(screen.getByText(/row actions/i)).toBeTruthy();
  });

  it("restores the last confirmed view and offers Retry on a failed read", async () => {
    server.use(
      http.get("/api/v1/playlists/:playlistId", () => HttpResponse.json({}, { status: 503 })),
    );
    renderAt(`/playlists/${playlist.id}`);

    expect(await screen.findByText("This playlist could not be loaded")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Retry" })).toBeTruthy();
  });
});

describe("library row actions", () => {
  it("adds a track to a playlist under the playlist's current revision", async () => {
    const submitted: Array<{ track_id: string; revision: number }> = [];
    server.use(
      http.get("/api/v1/profiles/:profileId/playlists", () =>
        HttpResponse.json({ items: [playlistFixture({ revision: 4 })], next_cursor: null }),
      ),
      http.post("/api/v1/playlists/:playlistId/tracks", async ({ request }) => {
        submitted.push((await request.json()) as { track_id: string; revision: number });
        return HttpResponse.json({ playlist: playlistFixture({ revision: 5 }), tracks: [] });
      }),
    );
    const user = userEvent.setup();
    renderAt("/library");

    await user.click(await screen.findByRole("button", { name: /actions for hoppipolla/i }));
    await user.click(await screen.findByRole("menuitem", { name: "Sunday Morning" }));

    await waitFor(() =>
      expect(submitted).toEqual([{ track_id: trackSummaryFixture().id, revision: 4 }]),
    );
  });

  it("says so when the active profile has no playlists to add to", async () => {
    const user = userEvent.setup();
    renderAt("/library");

    await user.click(await screen.findByRole("button", { name: /actions for hoppipolla/i }));

    expect(await screen.findByText("No playlists on this profile yet")).toBeTruthy();
  });
});
