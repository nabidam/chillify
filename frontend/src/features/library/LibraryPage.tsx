import { useQuery } from "@tanstack/react-query";
import { MusicIcon } from "lucide-react";
import { useState } from "react";
import { ApiRequestError, api, type LibrarySort, unwrap } from "@/api/client";
import { queryKeys } from "@/api/queryKeys";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ContextGrid } from "@/features/library/ContextGrid";
import { TrackTable, TrackTablePlaceholder } from "@/features/library/TrackTable";
import { usePlayerStore } from "@/features/player/playerStore";

const SORT_LABELS: Record<LibrarySort, string> = {
  recent: "Recently added",
  title: "Title",
  artist: "Artist",
};

/**
 * S2 — Your Library.
 *
 * The landing view for locally playable tracks. The same tracks are browsable
 * four ways — a flat list or grouped by artist, album, or year — so the tabs
 * switch the grouping without leaving the page or touching the player. Chillify
 * shows only what it downloaded and manages, so an empty view says exactly that
 * rather than implying a scan is missing.
 */
export function LibraryPage() {
  return (
    <div className="flex flex-col gap-5">
      <header>
        <h1 className="type-title text-foreground">Your Library</h1>
        <p className="type-meta text-foreground-muted">
          Everything Chillify has downloaded and manages for this household.
        </p>
      </header>

      <Tabs defaultValue="tracks" className="gap-4">
        <TabsList>
          <TabsTrigger value="tracks">Tracks</TabsTrigger>
          <TabsTrigger value="artists">Artists</TabsTrigger>
          <TabsTrigger value="albums">Albums</TabsTrigger>
          <TabsTrigger value="years">Years</TabsTrigger>
        </TabsList>

        <TabsContent value="tracks">
          <TracksTab />
        </TabsContent>
        <TabsContent value="artists">
          <ContextGrid kind="artist" />
        </TabsContent>
        <TabsContent value="albums">
          <ContextGrid kind="album" />
        </TabsContent>
        <TabsContent value="years">
          <ContextGrid kind="year" />
        </TabsContent>
      </Tabs>
    </div>
  );
}

/** The flat, sortable track list — the library's default grouping. */
function TracksTab() {
  const [sort, setSort] = useState<LibrarySort>("recent");
  const playQueue = usePlayerStore((state) => state.playQueue);

  const tracks = useQuery({
    queryKey: queryKeys.libraryTracks({ sort }),
    queryFn: async () =>
      unwrap(await api.GET("/api/v1/library/tracks", { params: { query: { sort } } })),
  });

  const items = tracks.data?.items ?? [];

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-4">
        <p className="type-meta text-foreground-muted">
          {tracks.isSuccess
            ? `${items.length} ${items.length === 1 ? "track" : "tracks"}`
            : "Loading your tracks…"}
        </p>

        <Select value={sort} onValueChange={(value) => setSort(value as LibrarySort)}>
          <SelectTrigger className="w-48" aria-label="Sort tracks">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {Object.entries(SORT_LABELS).map(([value, label]) => (
              <SelectItem key={value} value={value}>
                {label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {tracks.isPending ? <TrackTablePlaceholder /> : null}

      {tracks.isError ? (
        <Alert variant="destructive">
          <AlertTitle>Your library could not be loaded</AlertTitle>
          <AlertDescription>
            <span className="type-meta">
              {tracks.error instanceof ApiRequestError
                ? tracks.error.message
                : "The server did not respond."}
            </span>
            <Button
              variant="outline"
              size="sm"
              className="mt-2 w-fit"
              onClick={() => void tracks.refetch()}
            >
              Retry
            </Button>
          </AlertDescription>
        </Alert>
      ) : null}

      {tracks.isSuccess && items.length === 0 ? (
        <Empty>
          <EmptyHeader>
            <EmptyMedia variant="icon">
              <MusicIcon />
            </EmptyMedia>
            <EmptyTitle>No tracks yet</EmptyTitle>
            <EmptyDescription>
              Chillify shows only the tracks it downloaded and manages for this household. Add
              one to fill your library.
            </EmptyDescription>
          </EmptyHeader>
          <EmptyContent />
        </Empty>
      ) : null}

      {tracks.isSuccess && items.length > 0 ? (
        <TrackTable
          tracks={items}
          onPlay={(index) => {
            // Playing one row starts there and queues the rest in view order.
            playQueue(
              items.map((item) => item.id),
              index,
            );
          }}
        />
      ) : null}
    </div>
  );
}
