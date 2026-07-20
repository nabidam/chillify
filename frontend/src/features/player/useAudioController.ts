import { useQueryClient } from "@tanstack/react-query";
import { type RefObject, useEffect, useRef } from "react";
import { trackStreamUrl } from "@/api/client";
import { queryKeys } from "@/api/queryKeys";
import { selectCurrentTrackId, usePlayerStore } from "@/features/player/playerStore";

/**
 * Binds the one `<audio>` element to the player store.
 *
 * The element is created by the persistent player above the route outlet and
 * never remounted, so navigation cannot interrupt audio. Every effect here is
 * one-directional: the store is the intent, the element is the mechanism.
 */
export function useAudioController(): RefObject<HTMLAudioElement | null> {
  const audioRef = useRef<HTMLAudioElement>(null);
  const queryClient = useQueryClient();

  const trackId = usePlayerStore(selectCurrentTrackId);
  const isPlaying = usePlayerStore((state) => state.isPlaying);
  const volume = usePlayerStore((state) => state.volume);

  // Load the current track. Changing the source is what a "new track" means to
  // the element; everything else is transport.
  useEffect(() => {
    const audio = audioRef.current;
    if (audio === null) {
      return;
    }
    if (trackId === null) {
      audio.removeAttribute("src");
      audio.load();
      return;
    }
    audio.src = trackStreamUrl(trackId);
    audio.load();
  }, [trackId]);

  useEffect(() => {
    const audio = audioRef.current;
    if (audio === null || trackId === null) {
      return;
    }
    if (isPlaying) {
      // A rejected play() is a real failure to surface, not a warning to
      // swallow: the transport must not keep claiming it is playing.
      void audio.play().catch(() => {
        usePlayerStore.setState({ isPlaying: false });
      });
    } else {
      audio.pause();
    }
  }, [isPlaying, trackId]);

  useEffect(() => {
    const audio = audioRef.current;
    if (audio !== null) {
      audio.volume = volume;
    }
  }, [volume]);

  useEffect(() => {
    const audio = audioRef.current;
    if (audio === null) {
      return;
    }

    const onTimeUpdate = () => {
      usePlayerStore
        .getState()
        .reportProgress(
          audio.currentTime,
          Number.isFinite(audio.duration) ? audio.duration : 0,
        );
    };
    const onEnded = () => usePlayerStore.getState().playNext();
    const onError = () => {
      // The file is gone or unplayable. Mark it, invalidate the row so the
      // library stops offering Play, and move on rather than stalling.
      const current = selectCurrentTrackId(usePlayerStore.getState());
      if (current !== null) {
        usePlayerStore.getState().markUnplayable(current);
        void queryClient.invalidateQueries({ queryKey: queryKeys.track(current) });
        void queryClient.invalidateQueries({ queryKey: ["library", "tracks"] });
      }
      usePlayerStore.getState().playNext();
    };

    audio.addEventListener("timeupdate", onTimeUpdate);
    audio.addEventListener("durationchange", onTimeUpdate);
    audio.addEventListener("ended", onEnded);
    audio.addEventListener("error", onError);
    return () => {
      audio.removeEventListener("timeupdate", onTimeUpdate);
      audio.removeEventListener("durationchange", onTimeUpdate);
      audio.removeEventListener("ended", onEnded);
      audio.removeEventListener("error", onError);
    };
  }, [queryClient]);

  return audioRef;
}
