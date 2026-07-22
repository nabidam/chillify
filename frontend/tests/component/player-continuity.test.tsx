import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { queryKeys } from "@/api/queryKeys";
import { usePlayerStore } from "@/features/player/playerStore";
import { QueueDrawer } from "@/features/player/QueueDrawer";
import { trackSummaryFixture } from "../msw/handlers";

const trackA = trackSummaryFixture({ id: "id-a", title: "Alpha", artist: "Ann" });
const trackB = trackSummaryFixture({ id: "id-b", title: "Bravo", artist: "Ben" });
const trackC = trackSummaryFixture({ id: "id-c", title: "Charlie", artist: "Cara" });

beforeEach(() => {
  usePlayerStore.getState().clearSession();
  usePlayerStore.setState({ unplayableTrackIds: [] });
});

describe("queue reducers", () => {
  it("moves an upcoming track and leaves the played and current tracks fixed", () => {
    usePlayerStore.getState().playQueue(["a", "b", "c", "d"], 1);

    usePlayerStore.getState().reorderUpcoming(2, 3);

    const state = usePlayerStore.getState();
    expect(state.queue).toEqual(["a", "b", "d", "c"]);
    expect(state.currentIndex).toBe(1);
  });

  it("refuses to reorder the current track or reach into the played region", () => {
    usePlayerStore.getState().playQueue(["a", "b", "c", "d"], 1);

    usePlayerStore.getState().reorderUpcoming(1, 3); // the current track
    usePlayerStore.getState().reorderUpcoming(0, 2); // a played track
    usePlayerStore.getState().reorderUpcoming(2, 0); // into the played region

    const state = usePlayerStore.getState();
    expect(state.queue).toEqual(["a", "b", "c", "d"]);
    expect(state.currentIndex).toBe(1);
  });

  it("drops an upcoming track without disturbing the current one", () => {
    usePlayerStore.getState().playQueue(["a", "b", "c", "d"], 1);

    usePlayerStore.getState().removeFromQueue(2);

    const state = usePlayerStore.getState();
    expect(state.queue).toEqual(["a", "b", "d"]);
    expect(state.currentIndex).toBe(1);
    expect(state.isPlaying).toBe(true);
  });

  it("shifts the current index down when an already-played track is removed", () => {
    usePlayerStore.getState().playQueue(["a", "b", "c", "d"], 2);

    usePlayerStore.getState().removeFromQueue(0);

    const state = usePlayerStore.getState();
    expect(state.queue).toEqual(["b", "c", "d"]);
    // Still pointing at "c": the played item left, the current track did not.
    expect(state.currentIndex).toBe(1);
  });

  it("advances to the next track when the current one is removed", () => {
    usePlayerStore.getState().playQueue(["a", "b", "c"], 0);

    usePlayerStore.getState().removeFromQueue(0);

    const state = usePlayerStore.getState();
    expect(state.queue).toEqual(["b", "c"]);
    expect(state.currentIndex).toBe(0);
    expect(state.isPlaying).toBe(true);
    expect(state.positionSeconds).toBe(0);
  });

  it("skips an unplayable successor when the current track is removed", () => {
    usePlayerStore.getState().markUnplayable("b");
    usePlayerStore.getState().playQueue(["a", "b", "c"], 0);

    usePlayerStore.getState().removeFromQueue(0);

    const state = usePlayerStore.getState();
    expect(state.queue).toEqual(["b", "c"]);
    expect(state.currentIndex).toBe(1); // "b" is unplayable, so "c" takes over
    expect(state.isPlaying).toBe(true);
  });

  it("stops and clears when the removed current track has no playable successor", () => {
    usePlayerStore.getState().markUnplayable("b");
    usePlayerStore.getState().playQueue(["a", "b"], 0);

    usePlayerStore.getState().removeFromQueue(0);

    const state = usePlayerStore.getState();
    expect(state.queue).toEqual(["b"]);
    expect(state.currentIndex).toBe(-1);
    expect(state.isPlaying).toBe(false);
  });
});

function renderDrawer() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  queryClient.setQueryData(queryKeys.libraryTracks(), {
    items: [trackA, trackB, trackC],
    next_cursor: null,
  });
  render(
    <QueryClientProvider client={queryClient}>
      <QueueDrawer />
    </QueryClientProvider>,
  );
}

describe("S14 queue drawer", () => {
  it("says nothing is queued before a track has played", async () => {
    const user = userEvent.setup();
    renderDrawer();

    await user.click(screen.getByRole("button", { name: "Queue" }));

    expect(await screen.findByText("Nothing queued yet")).toBeTruthy();
  });

  it("shows the current track and the upcoming rows", async () => {
    const user = userEvent.setup();
    usePlayerStore.getState().playQueue(["id-a", "id-b", "id-c"], 0);
    renderDrawer();

    await user.click(screen.getByRole("button", { name: "Queue" }));

    const nowPlaying = await screen.findByRole("region", { name: "Now playing" });
    expect(within(nowPlaying).getByText("Alpha")).toBeTruthy();

    const upNext = screen.getByRole("region", { name: "Up next" });
    expect(within(upNext).getByText("Bravo")).toBeTruthy();
    expect(within(upNext).getByText("Charlie")).toBeTruthy();
    // The current track is never offered a reorder handle.
    expect(within(upNext).getByRole("button", { name: "Reorder Bravo" })).toBeTruthy();
  });

  it("removes an upcoming track from the session queue", async () => {
    const user = userEvent.setup();
    usePlayerStore.getState().playQueue(["id-a", "id-b", "id-c"], 0);
    renderDrawer();

    await user.click(screen.getByRole("button", { name: "Queue" }));
    await user.click(
      await screen.findByRole("button", { name: "Remove Bravo from the queue" }),
    );

    expect(usePlayerStore.getState().queue).toEqual(["id-a", "id-c"]);
    expect(screen.queryByText("Bravo")).toBeNull();
  });

  it("labels a track that has been deleted from the library and keeps it removable", async () => {
    const user = userEvent.setup();
    usePlayerStore.getState().playQueue(["id-a", "ghost-id"], 0);
    renderDrawer();

    await user.click(screen.getByRole("button", { name: "Queue" }));

    expect(await screen.findByText("Unavailable track")).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "Remove Unavailable track from the queue" }),
    ).toBeTruthy();
  });

  it("clears the entire session queue", async () => {
    const user = userEvent.setup();
    usePlayerStore.getState().playQueue(["id-a", "id-b", "id-c"], 0);
    renderDrawer();

    await user.click(screen.getByRole("button", { name: "Queue" }));
    await user.click(await screen.findByRole("button", { name: "Clear queue" }));

    expect(usePlayerStore.getState().queue).toEqual([]);
    expect(await screen.findByText("Nothing queued yet")).toBeTruthy();
  });
});
