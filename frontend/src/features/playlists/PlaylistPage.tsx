import type { DragEndEvent } from "@dnd-kit/react";
import { DragDropProvider } from "@dnd-kit/react";
import { ListMusic, Pencil, Play } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router";
import { toast } from "sonner";
import type { PlaylistDetail, TrackSummary } from "@/api/client";
import { ApiRequestError } from "@/api/client";
import { routes } from "@/app/routes";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty";
import { Table, TableBody, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { TrackTablePlaceholder } from "@/features/library/TrackTable";
import { TrackEditorDialog } from "@/features/metadata/TrackEditorDialog";
import { selectCurrentTrackId, usePlayerStore } from "@/features/player/playerStore";
import { PlaylistEditorDialog } from "@/features/playlists/PlaylistEditorDialog";
import {
  usePlaylist,
  useRemoveTrackFromPlaylist,
  useReorderPlaylist,
} from "@/features/playlists/playlistQueries";
import { SortablePlaylistRow } from "@/features/playlists/SortablePlaylistRow";

/** Move one item to a new index, returning a new array. */
function moveTrack(tracks: TrackSummary[], from: number, to: number): TrackSummary[] {
  const next = tracks.slice();
  const [moved] = next.splice(from, 1);
  if (moved === undefined) {
    return tracks;
  }
  next.splice(to, 0, moved);
  return next;
}

/**
 * S10 — Playlist detail.
 *
 * Play, in the saved order, is the primary action. Reorder and remove are the
 * direct row actions: a drag writes the whole order back under the playlist's
 * revision, and a failed write restores the last confirmed order rather than
 * leaving the browser showing an order the server never accepted.
 */
export function PlaylistPage() {
  const { playlistId } = useParams<{ playlistId: string }>();
  const [isRenameOpen, setRenameOpen] = useState(false);
  const [editingTrackId, setEditingTrackId] = useState<string | null>(null);
  const detail = usePlaylist(playlistId);
  const playQueue = usePlayerStore((state) => state.playQueue);
  const currentTrackId = usePlayerStore(selectCurrentTrackId);
  const reorder = useReorderPlaylist();
  const removeTrack = useRemoveTrackFromPlaylist();

  const playlist = detail.data?.playlist;
  const confirmedTracks = detail.data?.tracks ?? [];

  // The saved order the server has confirmed is the source of truth; the
  // optimistic arrangement is kept only while a reorder is in flight and is
  // tagged with the detail it was derived from, so a fresh detail from the
  // server drops it automatically without an effect.
  const [optimistic, setOptimistic] = useState<{
    source: PlaylistDetail;
    tracks: TrackSummary[];
  } | null>(null);
  const tracks =
    optimistic !== null && optimistic.source === detail.data
      ? optimistic.tracks
      : confirmedTracks;

  const playableCount = tracks.filter((track) => track.is_playable).length;
  const reorderDisabled = !detail.isSuccess || tracks.length < 2 || reorder.isPending;

  function handleDragEnd(event: DragEndEvent) {
    const { source, target } = event.operation;
    const confirmed = detail.data;
    if (
      event.canceled ||
      playlist === undefined ||
      confirmed === undefined ||
      source === null ||
      target == null
    ) {
      return;
    }
    const from = tracks.findIndex((track) => track.id === source.id);
    const to = tracks.findIndex((track) => track.id === target.id);
    if (from === -1 || to === -1 || from === to) {
      return;
    }

    const next = moveTrack(tracks, from, to);
    setOptimistic({ source: confirmed, tracks: next });
    reorder.mutate(
      {
        playlistId: playlist.id,
        trackIds: next.map((track) => track.id),
        revision: playlist.revision,
      },
      {
        onError: (error) => {
          // Restore the last confirmed order: the drag never happened as far
          // as the server is concerned, so the browser must not keep showing it.
          setOptimistic(null);
          toast.error("That new order could not be saved", {
            description:
              error instanceof ApiRequestError
                ? error.message
                : "The playlist was left in its last saved order.",
          });
        },
      },
    );
  }

  return (
    <div className="flex flex-col gap-5">
      {/* The header survives loading and error alike: a person who navigated
          here knows which playlist they opened even while it is still arriving. */}
      <header className="flex items-center justify-between gap-4">
        <div>
          <h1 className="type-title text-foreground">{playlist?.name ?? "Playlist"}</h1>
          <p className="type-meta text-foreground-muted">
            {detail.isSuccess
              ? `${tracks.length} ${tracks.length === 1 ? "track" : "tracks"}`
              : "Loading this playlist…"}
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Button
            className="gap-2"
            disabled={playableCount === 0}
            onClick={() => {
              // The saved order is what plays, minus tracks whose files are
              // gone: the queue never contains something that cannot start.
              playQueue(
                tracks.filter((track) => track.is_playable).map((track) => track.id),
                0,
              );
            }}
          >
            <Play className="size-4" aria-hidden="true" />
            Play Playlist
          </Button>
          <Button
            variant="outline"
            className="gap-2"
            disabled={playlist === undefined}
            onClick={() => setRenameOpen(true)}
          >
            <Pencil className="size-4" aria-hidden="true" />
            Rename
          </Button>
        </div>
      </header>

      {detail.isPending ? <TrackTablePlaceholder /> : null}

      {detail.isError ? (
        <Alert variant="destructive">
          <AlertTitle>This playlist could not be loaded</AlertTitle>
          <AlertDescription>
            <span className="type-meta">
              {detail.error instanceof ApiRequestError
                ? detail.error.message
                : "The server did not respond."}
            </span>
            <Button
              variant="outline"
              size="sm"
              className="mt-2 w-fit"
              onClick={() => void detail.refetch()}
            >
              Retry
            </Button>
          </AlertDescription>
        </Alert>
      ) : null}

      {detail.isSuccess && tracks.length === 0 ? (
        <Empty>
          <EmptyHeader>
            <EmptyMedia variant="icon">
              <ListMusic />
            </EmptyMedia>
            <EmptyTitle>Nothing in this playlist yet</EmptyTitle>
            <EmptyDescription>
              Add tracks from the row actions in your library or in search results.
            </EmptyDescription>
          </EmptyHeader>
          <EmptyContent>
            <Button asChild variant="outline">
              <Link to={routes.library}>Go to your library</Link>
            </Button>
          </EmptyContent>
        </Empty>
      ) : null}

      {detail.isSuccess && tracks.length > 0 && playlist !== undefined ? (
        <DragDropProvider onDragEnd={handleDragEnd}>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-control-lg">
                  <span className="sr-only">Reorder</span>
                </TableHead>
                <TableHead className="w-control-lg">
                  <span className="sr-only">Play</span>
                </TableHead>
                <TableHead>Title</TableHead>
                <TableHead>Artist</TableHead>
                <TableHead>Album</TableHead>
                <TableHead className="w-16 text-right">Year</TableHead>
                <TableHead className="w-20 text-right">Length</TableHead>
                <TableHead className="w-control-lg">
                  <span className="sr-only">Track actions</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {tracks.map((track, index) => (
                <SortablePlaylistRow
                  key={track.id}
                  track={track}
                  index={index}
                  isCurrent={track.id === currentTrackId}
                  reorderDisabled={reorderDisabled}
                  onPlay={() =>
                    playQueue(
                      tracks.map((item) => item.id),
                      index,
                    )
                  }
                  onEdit={() => setEditingTrackId(track.id)}
                  onRemove={() =>
                    removeTrack.mutate(
                      {
                        playlistId: playlist.id,
                        trackId: track.id,
                        revision: playlist.revision,
                      },
                      {
                        onError: (error) => {
                          toast.error("That track could not be removed", {
                            description:
                              error instanceof ApiRequestError
                                ? error.message
                                : "The playlist was left unchanged.",
                          });
                        },
                      },
                    )
                  }
                />
              ))}
            </TableBody>
          </Table>
        </DragDropProvider>
      ) : null}

      {playlist !== undefined ? (
        <PlaylistEditorDialog
          open={isRenameOpen}
          onOpenChange={setRenameOpen}
          profileId={playlist.profile_id}
          playlist={{
            id: playlist.id,
            name: playlist.name,
            revision: playlist.revision,
          }}
        />
      ) : null}

      <TrackEditorDialog
        trackId={editingTrackId}
        open={editingTrackId !== null}
        onOpenChange={(open) => {
          if (!open) {
            setEditingTrackId(null);
          }
        }}
      />
    </div>
  );
}
