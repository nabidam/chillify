import { ListMusic, Pencil, Play } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router";
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
import { TrackTable, TrackTablePlaceholder } from "@/features/library/TrackTable";
import { usePlayerStore } from "@/features/player/playerStore";
import { PlaylistEditorDialog } from "@/features/playlists/PlaylistEditorDialog";
import { usePlaylist } from "@/features/playlists/playlistQueries";

/**
 * S10 — Playlist detail.
 *
 * Play, in the saved order, is the primary action. Reorder and remove arrive
 * with the row actions in a later chunk; metadata corrections stay in S13, so
 * nothing here edits a track.
 */
export function PlaylistPage() {
  const { playlistId } = useParams<{ playlistId: string }>();
  const [isRenameOpen, setRenameOpen] = useState(false);
  const detail = usePlaylist(playlistId);
  const playQueue = usePlayerStore((state) => state.playQueue);

  const playlist = detail.data?.playlist;
  const tracks = detail.data?.tracks ?? [];
  const playableCount = tracks.filter((track) => track.is_playable).length;

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

      {tracks.length > 0 ? (
        <TrackTable
          tracks={tracks}
          onPlay={(index) =>
            playQueue(
              tracks.map((track) => track.id),
              index,
            )
          }
        />
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
    </div>
  );
}
