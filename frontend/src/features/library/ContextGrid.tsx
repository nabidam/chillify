import { useQuery } from "@tanstack/react-query";
import { CalendarIcon, DiscIcon, type LucideIcon, MicVocalIcon } from "lucide-react";
import { Link } from "react-router";
import { ApiRequestError, api, unwrap } from "@/api/client";
import { queryKeys } from "@/api/queryKeys";
import { contextRoutes } from "@/app/routes";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty";
import { Skeleton } from "@/components/ui/skeleton";

type ContextKind = "artist" | "album" | "year";

/** The shape every collection card renders, regardless of grouping kind. */
interface ContextCard {
  to: string;
  title: string;
  subtitle: string | null;
  trackCount: number;
}

interface KindCopy {
  icon: LucideIcon;
  errorTitle: string;
  emptyTitle: string;
  emptyDescription: string;
}

const COPY: Record<ContextKind, KindCopy> = {
  artist: {
    icon: MicVocalIcon,
    errorTitle: "Artists could not be loaded",
    emptyTitle: "No artists yet",
    emptyDescription: "Artists appear here once your library has tracks to group.",
  },
  album: {
    icon: DiscIcon,
    errorTitle: "Albums could not be loaded",
    emptyTitle: "No albums yet",
    emptyDescription: "Albums appear here once your library has tracks to group.",
  },
  year: {
    icon: CalendarIcon,
    errorTitle: "Years could not be loaded",
    emptyTitle: "No years yet",
    emptyDescription: "Release years appear here once your library has tracks to group.",
  },
};

function collectionQueryKey(kind: ContextKind) {
  switch (kind) {
    case "artist":
      return queryKeys.libraryArtists();
    case "album":
      return queryKeys.libraryAlbums();
    case "year":
      return queryKeys.libraryYears();
  }
}

/**
 * Fetch one grouping collection and map it to display cards.
 *
 * Each branch names a concrete path so the client's generated types carry the
 * grouping fields directly. An absent album or year renders as its first-class
 * Unknown grouping rather than being hidden.
 */
async function fetchCards(kind: ContextKind): Promise<ContextCard[]> {
  switch (kind) {
    case "artist": {
      const data = unwrap(await api.GET("/api/v1/library/artists"));
      return data.items.map((item) => ({
        to: contextRoutes.artist(item.artist_key),
        title: item.artist,
        subtitle: null,
        trackCount: item.track_count,
      }));
    }
    case "album": {
      const data = unwrap(await api.GET("/api/v1/library/albums"));
      return data.items.map((item) => ({
        to: contextRoutes.album(item.album_key),
        title: item.album ?? "Unknown Album",
        subtitle: item.artist,
        trackCount: item.track_count,
      }));
    }
    case "year": {
      const data = unwrap(await api.GET("/api/v1/library/years"));
      return data.items.map((item) => ({
        to: contextRoutes.year(item.year_key),
        title: item.release_year === null ? "Unknown Year" : String(item.release_year),
        subtitle: null,
        trackCount: item.track_count,
      }));
    }
  }
}

/**
 * A tab of the library browsed by a grouping rather than a flat track list.
 *
 * Artists, albums, and years each collapse the same tracks into a different set
 * of contexts; a card opens S6/S7/S8, where the exact play order lives. The card
 * never invents a count — it renders only what the server grouped.
 */
export function ContextGrid({ kind }: { kind: ContextKind }) {
  const copy = COPY[kind];
  const query = useQuery({
    queryKey: collectionQueryKey(kind),
    queryFn: () => fetchCards(kind),
  });

  if (query.isPending) {
    return <ContextGridSkeleton />;
  }

  if (query.isError) {
    return (
      <Alert variant="destructive">
        <AlertTitle>{copy.errorTitle}</AlertTitle>
        <AlertDescription>
          <span className="type-meta">
            {query.error instanceof ApiRequestError
              ? query.error.message
              : "The server did not respond."}
          </span>
          <Button
            variant="outline"
            size="sm"
            className="mt-2 w-fit"
            onClick={() => void query.refetch()}
          >
            Retry
          </Button>
        </AlertDescription>
      </Alert>
    );
  }

  const cards = query.data;

  if (cards.length === 0) {
    const Icon = copy.icon;
    return (
      <Empty>
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <Icon />
          </EmptyMedia>
          <EmptyTitle>{copy.emptyTitle}</EmptyTitle>
          <EmptyDescription>{copy.emptyDescription}</EmptyDescription>
        </EmptyHeader>
      </Empty>
    );
  }

  return (
    <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {cards.map((card) => (
        <li key={card.to}>
          <ContextCardLink card={card} icon={copy.icon} />
        </li>
      ))}
    </ul>
  );
}

function ContextCardLink({ card, icon: Icon }: { card: ContextCard; icon: LucideIcon }) {
  return (
    <Card className="relative transition-colors hover:border-signal focus-within:border-signal">
      <CardContent className="flex items-center gap-3 py-4">
        <span
          className="grid size-10 shrink-0 place-items-center rounded-md bg-surface-muted text-foreground-muted"
          aria-hidden="true"
        >
          <Icon className="size-5" />
        </span>
        <span className="min-w-0 flex-1">
          <Link
            to={card.to}
            className="type-label block truncate text-foreground outline-none after:absolute after:inset-0 after:content-[''] focus-visible:underline"
          >
            {card.title}
          </Link>
          <span className="type-meta block truncate text-foreground-muted">
            {card.subtitle ??
              `${card.trackCount} ${card.trackCount === 1 ? "track" : "tracks"}`}
          </span>
        </span>
      </CardContent>
    </Card>
  );
}

function ContextGridSkeleton() {
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3" aria-hidden="true">
      {Array.from({ length: 6 }, (_, index) => (
        // biome-ignore lint/suspicious/noArrayIndexKey: fixed-length placeholder geometry.
        <Skeleton key={index} className="h-[4.5rem] w-full" />
      ))}
    </div>
  );
}
