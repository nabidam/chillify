import { useSortable } from "@dnd-kit/react/sortable";
import { GripVertical, MoreHorizontal, Pencil, PlayIcon, Trash2 } from "lucide-react";
import type { TrackSummary } from "@/api/client";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { TableCell, TableRow } from "@/components/ui/table";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { AddToPlaylistMenu } from "@/features/library/AddToPlaylistMenu";
import { cn } from "@/lib/cn";
import { formatMilliseconds } from "@/lib/format";

/**
 * One draggable playlist row.
 *
 * Play, reorder, and remove are the three direct row actions of S10. The drag
 * handle is a dedicated control rather than the whole row so that clicking a
 * title or opening the row menu never starts a drag, and so the handle carries
 * its own accessible name. A track whose file is missing keeps its metadata,
 * is labelled, and has Play disabled — it can still be reordered or removed.
 */
export function SortablePlaylistRow({
  track,
  index,
  isCurrent,
  reorderDisabled,
  onPlay,
  onEdit,
  onRemove,
}: {
  track: TrackSummary;
  index: number;
  isCurrent: boolean;
  reorderDisabled: boolean;
  onPlay: () => void;
  onEdit: () => void;
  onRemove: () => void;
}) {
  const { ref, handleRef, isDragging } = useSortable({
    id: track.id,
    index,
    disabled: reorderDisabled,
  });

  return (
    <TableRow
      ref={ref}
      data-state={isCurrent ? "selected" : undefined}
      className={cn("h-row", isDragging && "opacity-60")}
    >
      <TableCell>
        <Button
          ref={handleRef}
          variant="ghost"
          size="icon"
          aria-label={`Reorder ${track.title}`}
          disabled={reorderDisabled}
          className="cursor-grab touch-none"
        >
          <GripVertical />
        </Button>
      </TableCell>
      <TableCell>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              aria-label={`Play ${track.title}`}
              disabled={!track.is_playable}
              onClick={onPlay}
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
        <span className={cn("type-label", isCurrent ? "text-signal" : "text-foreground")}>
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
      <TableCell>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon" aria-label={`Actions for ${track.title}`}>
              <MoreHorizontal />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onSelect={onEdit}>
              <Pencil aria-hidden="true" />
              Edit details
            </DropdownMenuItem>
            <DropdownMenuItem variant="destructive" onSelect={onRemove}>
              <Trash2 aria-hidden="true" />
              Remove from this playlist
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <AddToPlaylistMenu trackId={track.id} />
          </DropdownMenuContent>
        </DropdownMenu>
      </TableCell>
    </TableRow>
  );
}
