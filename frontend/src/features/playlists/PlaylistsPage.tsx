import { ListMusic, Plus } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";
import { ApiRequestError } from "@/api/client";
import { useActiveProfile } from "@/app/activeProfile";
import { routes } from "@/app/routes";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty";
import { Skeleton } from "@/components/ui/skeleton";
import { PlaylistEditorDialog } from "@/features/playlists/PlaylistEditorDialog";
import { usePlaylists } from "@/features/playlists/playlistQueries";
import { formatRelativeTime } from "@/lib/format";

/**
 * S9 — Playlists.
 *
 * The current profile's playlists, nothing else. Profiles and the shared
 * library are managed elsewhere, so this screen says plainly whose lists these
 * are rather than implying the household has one set.
 */
export function PlaylistsPage() {
  const { activeProfileId } = useActiveProfile();
  const [isEditorOpen, setEditorOpen] = useState(false);
  const playlists = usePlaylists(activeProfileId);
  const items = playlists.data ?? [];

  return (
    <div className="flex flex-col gap-5">
      {/* The heading and the create action survive every state below, so a
          loading or failed list never removes the way out of it. */}
      <header className="flex items-center justify-between gap-4">
        <div>
          <h1 className="type-title text-foreground">Playlists</h1>
          <p className="type-meta text-foreground-muted">
            {playlists.isSuccess
              ? `${items.length} ${items.length === 1 ? "playlist" : "playlists"}`
              : "Loading your playlists…"}
          </p>
        </div>
        <Button className="gap-2" onClick={() => setEditorOpen(true)}>
          <Plus className="size-4" aria-hidden="true" />
          Create Playlist
        </Button>
      </header>

      {playlists.isPending ? (
        <div className="flex flex-col gap-2" aria-hidden="true">
          {Array.from({ length: 4 }, (_, index) => (
            // biome-ignore lint/suspicious/noArrayIndexKey: fixed-length placeholder geometry.
            <Skeleton key={index} className="h-row w-full" />
          ))}
        </div>
      ) : null}

      {playlists.isError ? (
        <Alert variant="destructive">
          <AlertTitle>Your playlists could not be loaded</AlertTitle>
          <AlertDescription>
            <span className="type-meta">
              {playlists.error instanceof ApiRequestError
                ? playlists.error.message
                : "The server did not respond."}
            </span>
            <Button
              variant="outline"
              size="sm"
              className="mt-2 w-fit"
              onClick={() => void playlists.refetch()}
            >
              Retry
            </Button>
          </AlertDescription>
        </Alert>
      ) : null}

      {playlists.isSuccess && items.length === 0 ? (
        <Empty>
          <EmptyHeader>
            <EmptyMedia variant="icon">
              <ListMusic />
            </EmptyMedia>
            <EmptyTitle>No playlists yet</EmptyTitle>
            <EmptyDescription>
              Playlists belong to the profile that is currently active. Everyone in the
              household shares the library, but not these.
            </EmptyDescription>
          </EmptyHeader>
          <EmptyContent>
            <Button className="gap-2" onClick={() => setEditorOpen(true)}>
              <Plus className="size-4" aria-hidden="true" />
              Create Playlist
            </Button>
          </EmptyContent>
        </Empty>
      ) : null}

      {items.length > 0 ? (
        <ul className="flex flex-col gap-2">
          {items.map((playlist) => (
            <li key={playlist.id}>
              <Card className="p-0 transition-colors hover:bg-surface-hover">
                <CardContent className="p-0">
                  <Link
                    to={`${routes.playlists}/${playlist.id}`}
                    className="flex items-center justify-between gap-4 rounded-md p-4 focus-visible:outline-2 focus-visible:outline-focus focus-visible:outline-offset-2"
                  >
                    <span className="flex items-center gap-3">
                      <ListMusic className="size-4 text-foreground-subtle" aria-hidden="true" />
                      <span className="type-label text-foreground">{playlist.name}</span>
                    </span>
                    <span className="type-meta text-foreground-subtle">
                      {playlist.track_count} {playlist.track_count === 1 ? "track" : "tracks"} ·
                      updated {formatRelativeTime(playlist.updated_at)}
                    </span>
                  </Link>
                </CardContent>
              </Card>
            </li>
          ))}
        </ul>
      ) : null}

      <PlaylistEditorDialog
        open={isEditorOpen}
        onOpenChange={setEditorOpen}
        profileId={activeProfileId}
      />
    </div>
  );
}
