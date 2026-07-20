import { create } from "zustand";

/**
 * Browser-owned playback state.
 *
 * The store holds track IDs and ordered queue entries, never server records:
 * current metadata is selected from the Query cache by ID, so a metadata edit
 * is reflected without the player owning a second stale copy.
 *
 * The queue is deliberately session-only. A refresh or a profile switch starts
 * it empty; nothing here is durable, and nothing here pretends to be.
 */
export interface PlayerState {
  queue: string[];
  currentIndex: number;
  isPlaying: boolean;
  volume: number;
  positionSeconds: number;
  durationSeconds: number;
  /** Tracks whose audio failed this session; skipped rather than retried. */
  unplayableTrackIds: string[];

  playQueue: (trackIds: string[], startIndex: number) => void;
  togglePlayback: () => void;
  playNext: () => void;
  playPrevious: () => void;
  seekTo: (seconds: number) => void;
  setVolume: (volume: number) => void;
  reportProgress: (positionSeconds: number, durationSeconds: number) => void;
  markUnplayable: (trackId: string) => void;
  clearSession: () => void;
}

const EMPTY_SESSION = {
  queue: [] as string[],
  currentIndex: -1,
  isPlaying: false,
  positionSeconds: 0,
  durationSeconds: 0,
};

/** The first index at or after `from` whose track has not failed this session. */
function nextPlayableIndex(
  queue: string[],
  unplayable: string[],
  from: number,
  step: 1 | -1,
): number {
  for (let index = from; index >= 0 && index < queue.length; index += step) {
    const trackId = queue[index];
    if (trackId !== undefined && !unplayable.includes(trackId)) {
      return index;
    }
  }
  return -1;
}

export const usePlayerStore = create<PlayerState>()((set, get) => ({
  ...EMPTY_SESSION,
  volume: 1,
  unplayableTrackIds: [],

  playQueue: (trackIds, startIndex) => {
    const { unplayableTrackIds } = get();
    const index = nextPlayableIndex(trackIds, unplayableTrackIds, startIndex, 1);
    set({
      queue: trackIds,
      currentIndex: index,
      isPlaying: index >= 0,
      positionSeconds: 0,
      durationSeconds: 0,
    });
  },

  togglePlayback: () =>
    set((state) => (state.currentIndex < 0 ? state : { isPlaying: !state.isPlaying })),

  playNext: () =>
    set((state) => {
      const index = nextPlayableIndex(
        state.queue,
        state.unplayableTrackIds,
        state.currentIndex + 1,
        1,
      );
      // Running off the end stops playback and keeps the queue: the person can
      // still see what they were listening to.
      return index < 0
        ? { isPlaying: false, positionSeconds: 0 }
        : { currentIndex: index, isPlaying: true, positionSeconds: 0, durationSeconds: 0 };
    }),

  playPrevious: () =>
    set((state) => {
      const index = nextPlayableIndex(
        state.queue,
        state.unplayableTrackIds,
        state.currentIndex - 1,
        -1,
      );
      return index < 0
        ? { positionSeconds: 0 }
        : { currentIndex: index, isPlaying: true, positionSeconds: 0, durationSeconds: 0 };
    }),

  seekTo: (seconds) => set({ positionSeconds: Math.max(0, seconds) }),

  setVolume: (volume) => set({ volume: Math.min(1, Math.max(0, volume)) }),

  reportProgress: (positionSeconds, durationSeconds) =>
    set({ positionSeconds, durationSeconds }),

  markUnplayable: (trackId) =>
    set((state) =>
      state.unplayableTrackIds.includes(trackId)
        ? state
        : { unplayableTrackIds: [...state.unplayableTrackIds, trackId] },
    ),

  clearSession: () => set({ ...EMPTY_SESSION }),
}));

/** The current track's ID, or null when nothing is loaded. */
export function selectCurrentTrackId(state: PlayerState): string | null {
  return state.queue[state.currentIndex] ?? null;
}
