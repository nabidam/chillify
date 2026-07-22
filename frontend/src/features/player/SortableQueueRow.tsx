import { useSortable } from "@dnd-kit/react/sortable";
import { GripVertical, Music2Icon, X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";

/**
 * One draggable upcoming-queue row.
 *
 * The queue is browser-session state, so a reorder or remove is immediate and
 * local — there is no revision to reconcile. The drag handle is a dedicated
 * control so that pressing Remove never starts a drag and so the handle carries
 * its own accessible name. A track whose file is missing keeps its metadata and
 * is labelled; it can still be reordered or removed like any other.
 */
export function SortableQueueRow({
  id,
  index,
  title,
  artist,
  isMissing,
  onRemove,
}: {
  id: string;
  index: number;
  title: string;
  artist: string;
  isMissing: boolean;
  onRemove: () => void;
}) {
  const { ref, handleRef, isDragging } = useSortable({ id, index });

  return (
    <li
      ref={ref}
      className={cn(
        "flex h-row items-center gap-2 rounded-sm px-2 hover:bg-surface-hover",
        isDragging && "opacity-60",
      )}
    >
      <Button
        ref={handleRef}
        variant="ghost"
        size="icon"
        aria-label={`Reorder ${title}`}
        className="cursor-grab touch-none"
      >
        <GripVertical />
      </Button>

      <div
        aria-hidden="true"
        className="flex size-cover-sm shrink-0 items-center justify-center rounded-sm bg-cover-placeholder"
      >
        <Music2Icon className="size-4 text-foreground-subtle" />
      </div>

      <div className="min-w-0 flex-1">
        <p className="type-label truncate text-foreground">
          {title}
          {isMissing ? (
            <Badge variant="outline" className="ml-2 align-middle">
              File missing
            </Badge>
          ) : null}
        </p>
        <p className="type-meta truncate text-foreground-muted">{artist}</p>
      </div>

      <Button
        variant="ghost"
        size="icon"
        aria-label={`Remove ${title} from the queue`}
        onClick={onRemove}
      >
        <X />
      </Button>
    </li>
  );
}
