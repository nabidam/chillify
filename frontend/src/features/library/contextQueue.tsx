import type { TrackSummary } from "@/api/client";
import { usePlayerStore } from "@/features/player/playerStore";

/**
 * Playing a browse context.
 *
 * A context view is already ordered by the server, so playback copies that
 * exact ID order into the session queue and never reorders it. The store's
 * `playQueue` advances from the chosen index to the first playable track, so a
 * context whose first row is a missing file still starts on the next real one.
 */
export function useContextPlayback() {
  const playQueue = usePlayerStore((state) => state.playQueue);
  return (tracks: readonly TrackSummary[], startIndex = 0) => {
    playQueue(
      tracks.map((track) => track.id),
      startIndex,
    );
  };
}

/** Whether a context has any track whose managed file can be streamed now. */
export function hasPlayableTrack(tracks: readonly TrackSummary[]): boolean {
  return tracks.some((track) => track.is_playable);
}
