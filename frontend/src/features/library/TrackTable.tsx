import { PlayIcon } from "lucide-react";
import type { TrackSummary } from "@/api/client";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { selectCurrentTrackId, usePlayerStore } from "@/features/player/playerStore";
import { cn } from "@/lib/cn";
import { formatMilliseconds } from "@/lib/format";

/**
 * Dense local track rows.
 *
 * A local track always exposes Play. A track whose managed file is gone keeps
 * every readable piece of metadata, is labelled, and has Play disabled — the
 * row is a thing to correct, not a thing to hide.
 */
export function TrackTable({
  tracks,
  onPlay,
}: {
  tracks: TrackSummary[];
  onPlay: (index: number) => void;
}) {
  const currentTrackId = usePlayerStore(selectCurrentTrackId);

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="w-control-lg">
            <span className="sr-only">Play</span>
          </TableHead>
          <TableHead>Title</TableHead>
          <TableHead>Artist</TableHead>
          <TableHead>Album</TableHead>
          <TableHead className="w-16 text-right">Year</TableHead>
          <TableHead className="w-20 text-right">Length</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {tracks.map((track, index) => {
          const isCurrent = track.id === currentTrackId;
          return (
            <TableRow
              key={track.id}
              data-state={isCurrent ? "selected" : undefined}
              className="h-row"
            >
              <TableCell>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label={`Play ${track.title}`}
                      disabled={!track.is_playable}
                      onClick={() => onPlay(index)}
                    >
                      <PlayIcon />
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>
                    {track.is_playable
                      ? `Play ${track.title}`
                      : "This track's file is missing from the library folder."}
                  </TooltipContent>
                </Tooltip>
              </TableCell>
              <TableCell>
                <span
                  className={cn("type-label", isCurrent ? "text-signal" : "text-foreground")}
                >
                  {track.title}
                </span>
                {!track.is_playable ? (
                  <Badge variant="outline" className="ml-2 align-middle">
                    File missing
                  </Badge>
                ) : null}
              </TableCell>
              <TableCell className="type-meta text-foreground-muted">{track.artist}</TableCell>
              <TableCell className="type-meta text-foreground-muted">
                {track.album ?? "Unknown album"}
              </TableCell>
              <TableCell className="type-meta text-right text-foreground-subtle tabular-nums">
                {track.release_year ?? "—"}
              </TableCell>
              <TableCell className="type-meta text-right text-foreground-subtle tabular-nums">
                {formatMilliseconds(track.duration_ms)}
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}

/** Fixed row placeholders matching the final row geometry. */
export function TrackTablePlaceholder({ rows = 6 }: { rows?: number }) {
  return (
    <div className="flex flex-col gap-2" aria-hidden="true">
      {Array.from({ length: rows }, (_, index) => (
        // biome-ignore lint/suspicious/noArrayIndexKey: fixed-length placeholder geometry.
        <Skeleton key={index} className="h-row w-full" />
      ))}
    </div>
  );
}
