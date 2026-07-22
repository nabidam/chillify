import type { DragEndEvent } from "@dnd-kit/react";
import { DragDropProvider } from "@dnd-kit/react";
import { type QueryClient, useQueryClient } from "@tanstack/react-query";
import { ListMusic, Music2Icon, Trash2 } from "lucide-react";
import type { TrackSummary } from "@/api/client";
import { queryKeys } from "@/api/queryKeys";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { usePlayerStore } from "@/features/player/playerStore";
import { SortableQueueRow } from "@/features/player/SortableQueueRow";
import { cn } from "@/lib/cn";

/** What the row needs, resolved from cache with a safe fallback for deletions. */
interface QueueRow {
  index: number;
  trackId: string;
  title: string;
  artist: string;
  isMissing: boolean;
}

/**
 * S14 — Queue drawer.
 *
 * The bottom-player Queue action opens the browser-session queue: the current
 * track, then the upcoming rows a person can reorder and remove directly, plus
 * a Clear control. Reorder and remove touch only what has not played yet, so
 * history stays truthful. Editing is browser-local — there is no server call to
 * fail — and nothing here survives a refresh, a profile switch, or Clear.
 *
 * Metadata is read from the Query cache by ID rather than copied into the store,
 * so an edit elsewhere is reflected and a deleted track degrades to a labelled,
 * removable row instead of a crash.
 */
export function QueueDrawer() {
  const queryClient = useQueryClient();
  const queue = usePlayerStore((state) => state.queue);
  const currentIndex = usePlayerStore((state) => state.currentIndex);
  const reorderUpcoming = usePlayerStore((state) => state.reorderUpcoming);
  const removeFromQueue = usePlayerStore((state) => state.removeFromQueue);
  const clearSession = usePlayerStore((state) => state.clearSession);

  const rows = queue.map((trackId, index): QueueRow => {
    const track = resolveTrack(queryClient, trackId);
    return {
      index,
      trackId,
      title: track?.title ?? "Unavailable track",
      artist: track?.artist ?? "This track is no longer in your library",
      isMissing: track !== null && !track.is_playable,
    };
  });

  const current = currentIndex >= 0 ? rows[currentIndex] : undefined;
  const upcoming = rows.slice(currentIndex + 1);
  const isEmpty = queue.length === 0;

  function handleDragEnd(event: DragEndEvent) {
    const { source, target } = event.operation;
    if (event.canceled || source === null || target == null) {
      return;
    }
    const from = Number(source.id);
    const to = Number(target.id);
    if (Number.isNaN(from) || Number.isNaN(to)) {
      return;
    }
    reorderUpcoming(from, to);
  }

  return (
    <Sheet>
      <SheetTrigger asChild>
        <Button variant="outline" size="sm" className="gap-2">
          <ListMusic className="size-4" aria-hidden="true" />
          Queue
        </Button>
      </SheetTrigger>
      <SheetContent side="right" className="w-full gap-0 sm:max-w-md">
        <SheetHeader>
          <SheetTitle>Play queue</SheetTitle>
          <SheetDescription>
            What plays next in this session. Reorder or remove upcoming tracks; nothing here
            survives a refresh or a profile switch.
          </SheetDescription>
        </SheetHeader>

        {isEmpty ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-2 px-6 text-center">
            <ListMusic className="size-8 text-foreground-subtle" aria-hidden="true" />
            <p className="type-label text-foreground">Nothing queued yet</p>
            <p className="type-meta text-foreground-muted">
              Play a track, artist, album, year, or playlist to build a queue.
            </p>
          </div>
        ) : (
          <ScrollArea className="min-h-0 flex-1">
            <div className="flex flex-col gap-4 px-4 pb-4">
              {current !== undefined ? (
                <section aria-label="Now playing" className="flex flex-col gap-1">
                  <h3 className="type-micro px-2 text-foreground-subtle uppercase tracking-wide">
                    Now playing
                  </h3>
                  <div className="flex h-row items-center gap-2 rounded-sm bg-surface-hover px-2">
                    <div
                      aria-hidden="true"
                      className="flex size-cover-sm shrink-0 items-center justify-center rounded-sm bg-cover-placeholder"
                    >
                      <Music2Icon className="size-4 text-signal" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="type-label truncate text-signal">
                        {current.title}
                        {current.isMissing ? (
                          <Badge variant="outline" className="ml-2 align-middle">
                            File missing
                          </Badge>
                        ) : null}
                      </p>
                      <p className="type-meta truncate text-foreground-muted">
                        {current.artist}
                      </p>
                    </div>
                  </div>
                </section>
              ) : null}

              <section aria-label="Up next" className="flex flex-col gap-1">
                <h3 className="type-micro px-2 text-foreground-subtle uppercase tracking-wide">
                  Up next
                </h3>
                {upcoming.length === 0 ? (
                  <p className="px-2 type-meta text-foreground-muted">
                    Nothing is queued after the current track.
                  </p>
                ) : (
                  <DragDropProvider onDragEnd={handleDragEnd}>
                    <ul className={cn("flex flex-col")}>
                      {upcoming.map((row) => (
                        <SortableQueueRow
                          key={row.index}
                          id={String(row.index)}
                          index={row.index}
                          title={row.title}
                          artist={row.artist}
                          isMissing={row.isMissing}
                          onRemove={() => removeFromQueue(row.index)}
                        />
                      ))}
                    </ul>
                  </DragDropProvider>
                )}
              </section>
            </div>
          </ScrollArea>
        )}

        <SheetFooter>
          <Button
            variant="outline"
            className="gap-2"
            disabled={isEmpty}
            onClick={() => clearSession()}
          >
            <Trash2 className="size-4" aria-hidden="true" />
            Clear queue
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}

/**
 * Find a track's metadata anywhere in the Query cache by ID.
 *
 * The store holds IDs only, and a queue can be built from a library view, a
 * context, or a playlist, so this scans the shapes those queries cache rather
 * than assuming one source. A miss means the track was deleted; the caller
 * shows a labelled, removable row.
 */
function resolveTrack(queryClient: QueryClient, id: string): TrackSummary | null {
  const single = queryClient.getQueryData<TrackSummary>(queryKeys.track(id));
  if (single?.id === id) {
    return single;
  }
  for (const prefix of [["library"], ["playlists"]] as const) {
    const caches = queryClient.getQueriesData<unknown>({ queryKey: prefix });
    for (const [, data] of caches) {
      const found = findTrackById(data, id);
      if (found !== null) {
        return found;
      }
    }
  }
  return null;
}

/** Pull a track out of the `items`, `tracks`, or paginated shapes we cache. */
function findTrackById(data: unknown, id: string): TrackSummary | null {
  if (data === null || typeof data !== "object") {
    return null;
  }
  const record = data as {
    pages?: { items?: TrackSummary[] }[];
    items?: TrackSummary[];
    tracks?: TrackSummary[];
  };
  const buckets: TrackSummary[] = [];
  if (Array.isArray(record.pages)) {
    for (const page of record.pages) {
      if (Array.isArray(page.items)) {
        buckets.push(...page.items);
      }
    }
  }
  if (Array.isArray(record.items)) {
    buckets.push(...record.items);
  }
  if (Array.isArray(record.tracks)) {
    buckets.push(...record.tracks);
  }
  return buckets.find((track) => track?.id === id) ?? null;
}
