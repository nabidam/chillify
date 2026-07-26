import { useQueryClient } from "@tanstack/react-query";
import { Music2Icon, PauseIcon, PlayIcon, SkipBackIcon, SkipForwardIcon } from "lucide-react";
import type { TrackSummary } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Slider } from "@/components/ui/slider";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { selectCurrentTrackId, usePlayerStore } from "@/features/player/playerStore";
import { QueueDrawer } from "@/features/player/QueueDrawer";
import { useAudioController } from "@/features/player/useAudioController";
import { formatDuration } from "@/lib/format";

/**
 * The persistent bottom player.
 *
 * Mounted above the route outlet: identity on the left, transport in the
 * visual centre, volume on the right. The `<audio>` element lives here and is
 * never remounted, so navigating cannot interrupt playback.
 */
export function PersistentPlayer() {
  const audioRef = useAudioController();
  const track = useCurrentTrack();

  const isPlaying = usePlayerStore((state) => state.isPlaying);
  const positionSeconds = usePlayerStore((state) => state.positionSeconds);
  const durationSeconds = usePlayerStore((state) => state.durationSeconds);
  const volume = usePlayerStore((state) => state.volume);
  const queueLength = usePlayerStore((state) => state.queue.length);
  const currentIndex = usePlayerStore((state) => state.currentIndex);
  const togglePlayback = usePlayerStore((state) => state.togglePlayback);
  const playNext = usePlayerStore((state) => state.playNext);
  const playPrevious = usePlayerStore((state) => state.playPrevious);
  const setVolume = usePlayerStore((state) => state.setVolume);

  const hasTrack = currentIndex >= 0;
  const reportedDuration =
    durationSeconds > 0 ? durationSeconds : (track?.duration_ms ?? 0) / 1000;
  const remaining = reportedDuration > 0 ? reportedDuration - positionSeconds : null;

  return (
    <section
      aria-label="Player"
      className="flex h-player shrink-0 items-center gap-5 border-t bg-canvas px-5"
    >
      {/* biome-ignore lint/a11y/useMediaCaption: household music has no caption track. */}
      <audio ref={audioRef} preload="metadata" />

      <div className="flex min-w-0 flex-1 items-center gap-3">
        <div
          aria-hidden="true"
          className="flex size-cover-sm shrink-0 items-center justify-center rounded-sm bg-cover-placeholder"
        >
          <Music2Icon className="size-4 text-foreground-subtle" />
        </div>
        <div className="min-w-0">
          {hasTrack && track ? (
            <>
              <p className="type-label truncate text-foreground">{track.title}</p>
              <p className="type-meta truncate text-foreground-muted">{track.artist}</p>
            </>
          ) : (
            <p className="type-meta text-foreground-subtle">
              Nothing is playing. Choose a track from your library to start.
            </p>
          )}
        </div>
      </div>

      <div className="flex flex-[2] flex-col items-center gap-1">
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="icon"
            aria-label="Previous track"
            disabled={!hasTrack || currentIndex <= 0}
            onClick={playPrevious}
          >
            <SkipBackIcon />
          </Button>

          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                size="icon"
                aria-label={isPlaying ? "Pause" : "Play"}
                disabled={!hasTrack}
                onClick={togglePlayback}
              >
                {isPlaying ? <PauseIcon /> : <PlayIcon />}
              </Button>
            </TooltipTrigger>
            <TooltipContent>
              {hasTrack ? (isPlaying ? "Pause" : "Play") : "Choose a track to play"}
            </TooltipContent>
          </Tooltip>

          <Button
            variant="ghost"
            size="icon"
            aria-label="Next track"
            disabled={!hasTrack || currentIndex >= queueLength - 1}
            onClick={playNext}
          >
            <SkipForwardIcon />
          </Button>
        </div>

        <div className="flex w-full max-w-[32rem] items-center gap-3">
          <span className="type-micro w-10 text-right text-foreground-subtle tabular-nums">
            {formatDuration(hasTrack ? positionSeconds : null)}
          </span>
          <Slider
            aria-label="Seek"
            thumbLabels={["Seek"]}
            className="flex-1"
            min={0}
            max={reportedDuration > 0 ? reportedDuration : 1}
            step={1}
            value={[Math.min(positionSeconds, reportedDuration)]}
            disabled={!hasTrack || reportedDuration <= 0}
            onValueChange={([next]) => {
              if (next !== undefined) {
                usePlayerStore.getState().seekTo(next);
                const audio = audioRef.current;
                if (audio !== null) {
                  audio.currentTime = next;
                }
              }
            }}
          />
          <span className="type-micro w-10 text-foreground-subtle tabular-nums">
            {hasTrack && remaining !== null ? `-${formatDuration(remaining)}` : "--:--"}
          </span>
        </div>
      </div>

      <div className="flex flex-1 items-center justify-end gap-3">
        <div className="flex items-center gap-2">
          <span className="type-micro text-foreground-subtle">Volume</span>
          <Slider
            aria-label="Volume"
            thumbLabels={["Volume"]}
            className="w-24"
            min={0}
            max={1}
            step={0.05}
            value={[volume]}
            onValueChange={([next]) => {
              if (next !== undefined) {
                setVolume(next);
              }
            }}
          />
        </div>
        <QueueDrawer />
      </div>
    </section>
  );
}

/**
 * The current track's metadata, selected from the Query cache by ID.
 *
 * The player store holds IDs only, so this reads whatever the library queries
 * already fetched rather than keeping a second copy that could go stale.
 */
function useCurrentTrack(): TrackSummary | null {
  const queryClient = useQueryClient();
  const trackId = usePlayerStore(selectCurrentTrackId);
  if (trackId === null) {
    return null;
  }

  const pages = queryClient.getQueriesData<{ items: TrackSummary[] }>({
    queryKey: ["library", "tracks"],
  });
  for (const [, page] of pages) {
    const found = page?.items.find((item) => item.id === trackId);
    if (found !== undefined) {
      return found;
    }
  }
  return null;
}
