import { useQuery } from "@tanstack/react-query";
import { ArrowLeftIcon, MusicIcon, PlayIcon } from "lucide-react";
import { Link, useParams } from "react-router";
import type { TrackSummary } from "@/api/client";
import { ApiRequestError, api, unwrap } from "@/api/client";
import { queryKeys } from "@/api/queryKeys";
import { routes } from "@/app/routes";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty";
import { hasPlayableTrack, useContextPlayback } from "@/features/library/contextQueue";
import { TrackTable, TrackTablePlaceholder } from "@/features/library/TrackTable";

type ContextKind = "artist" | "album" | "year";

/** The three groupings collapse into one shape once their identity is resolved. */
interface ResolvedContext {
  eyebrow: string | null;
  heading: string;
  playLabel: string;
  tracks: TrackSummary[];
}

const ERROR_TITLE: Record<ContextKind, string> = {
  artist: "This artist could not be loaded",
  album: "This album could not be loaded",
  year: "This year could not be loaded",
};

function contextQueryKey(kind: ContextKind, key: string) {
  switch (kind) {
    case "artist":
      return queryKeys.artistContext(key);
    case "album":
      return queryKeys.albumContext(key);
    case "year":
      return queryKeys.yearContext(key);
  }
}

/**
 * Fetch one context and resolve it to the shared shape.
 *
 * Each branch names a concrete path, so the client's generated types give the
 * identity fields directly and the page needs no per-kind casting.
 */
async function fetchContext(kind: ContextKind, key: string): Promise<ResolvedContext> {
  switch (kind) {
    case "artist": {
      const data = unwrap(
        await api.GET("/api/v1/library/artists/{artist_key}", {
          params: { path: { artist_key: key } },
        }),
      );
      return {
        eyebrow: "Artist",
        heading: data.artist,
        playLabel: "Play artist",
        tracks: data.tracks,
      };
    }
    case "album": {
      const data = unwrap(
        await api.GET("/api/v1/library/albums/{album_key}", {
          params: { path: { album_key: key } },
        }),
      );
      return {
        eyebrow: data.artist,
        heading: data.album ?? "Unknown Album",
        playLabel: "Play album",
        tracks: data.tracks,
      };
    }
    case "year": {
      const data = unwrap(
        await api.GET("/api/v1/library/years/{year_key}", {
          params: { path: { year_key: key } },
        }),
      );
      return {
        eyebrow: "Year",
        heading: data.release_year === null ? "Unknown Year" : String(data.release_year),
        playLabel: "Play year",
        tracks: data.tracks,
      };
    }
  }
}

/**
 * S6/S7/S8 — one browse context.
 *
 * The three groupings share a page because they share a shape: an identity, a
 * single Play action that replaces the session queue with the server's exact
 * order, and that same ordered list of rows. Only the heading and labels differ.
 */
export function ContextPage({ kind }: { kind: ContextKind }) {
  const { contextKey = "" } = useParams();
  const play = useContextPlayback();

  const query = useQuery({
    queryKey: contextQueryKey(kind, contextKey),
    queryFn: () => fetchContext(kind, contextKey),
  });

  if (query.isPending) {
    return (
      <div className="flex flex-col gap-5">
        <ContextHeaderPlaceholder />
        <TrackTablePlaceholder />
      </div>
    );
  }

  if (query.isError) {
    const invalidKey = query.error instanceof ApiRequestError && query.error.status === 422;
    return (
      <div className="flex flex-col gap-4">
        <BackToLibrary />
        <Alert variant="destructive">
          <AlertTitle>
            {invalidKey ? "That page no longer exists" : ERROR_TITLE[kind]}
          </AlertTitle>
          <AlertDescription>
            <span className="type-meta">
              {invalidKey
                ? "This link points to a grouping that has changed. Return to your library to find it."
                : query.error instanceof ApiRequestError
                  ? query.error.message
                  : "The server did not respond."}
            </span>
            {invalidKey ? null : (
              <Button
                variant="outline"
                size="sm"
                className="mt-2 w-fit"
                onClick={() => void query.refetch()}
              >
                Retry
              </Button>
            )}
          </AlertDescription>
        </Alert>
      </div>
    );
  }

  const resolved = query.data;
  const canPlay = hasPlayableTrack(resolved.tracks);

  return (
    <div className="flex flex-col gap-5">
      <BackToLibrary />

      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          {resolved.eyebrow ? (
            <p className="type-meta text-foreground-muted">{resolved.eyebrow}</p>
          ) : null}
          <h1 className="type-title truncate text-foreground">{resolved.heading}</h1>
          <p className="type-meta text-foreground-muted">
            {resolved.tracks.length} {resolved.tracks.length === 1 ? "track" : "tracks"}
          </p>
        </div>

        <Button onClick={() => play(resolved.tracks, 0)} disabled={!canPlay}>
          <PlayIcon aria-hidden="true" />
          {resolved.playLabel}
        </Button>
      </header>

      {resolved.tracks.length === 0 ? (
        <Empty>
          <EmptyHeader>
            <EmptyMedia variant="icon">
              <MusicIcon />
            </EmptyMedia>
            <EmptyTitle>No playable tracks here</EmptyTitle>
            <EmptyDescription>
              This grouping has no tracks in your library right now. It may have been reached
              from metadata that has since changed — you can correct any track's details from
              your library.
            </EmptyDescription>
          </EmptyHeader>
        </Empty>
      ) : (
        <TrackTable tracks={resolved.tracks} onPlay={(index) => play(resolved.tracks, index)} />
      )}
    </div>
  );
}

function BackToLibrary() {
  return (
    <Link
      to={routes.library}
      className="type-meta inline-flex w-fit items-center gap-1 text-foreground-muted outline-none hover:text-foreground focus-visible:underline"
    >
      <ArrowLeftIcon className="size-4" aria-hidden="true" />
      Your Library
    </Link>
  );
}

function ContextHeaderPlaceholder() {
  return (
    <div className="flex flex-col gap-2" aria-hidden="true">
      <div className="h-4 w-24 rounded bg-surface-muted" />
      <div className="h-7 w-64 rounded bg-surface-muted" />
    </div>
  );
}
