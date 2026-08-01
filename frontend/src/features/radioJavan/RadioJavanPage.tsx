import { useQuery } from "@tanstack/react-query";
import { Download, Library, Music2, Search } from "lucide-react";
import { type FormEvent, useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router";
import { toast } from "sonner";
import { ApiRequestError, api, unwrap } from "@/api/client";
import { queryKeys } from "@/api/queryKeys";
import { routes } from "@/app/routes";
import { useSystemStatus } from "@/app/useSystemStatus";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { AspectRatio } from "@/components/ui/aspect-ratio";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty";
import { Field, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { type RemoteResult, useQueueDownload } from "@/features/search/remoteSearch";

type RadioJavanSection = "featured" | "trending";

/** Dedicated Radio Javan search and first-page exploration. */
export function RadioJavanPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const queryFromUrl = new URLSearchParams(location.search).get("q")?.trim() ?? "";
  const [query, setQuery] = useState(queryFromUrl);
  const [section, setSection] = useState<RadioJavanSection>("featured");
  const searchResults = useRadioJavanSearch(queryFromUrl);
  const browseResults = useRadioJavanBrowse(section, queryFromUrl.length === 0);
  const results = queryFromUrl.length > 0 ? searchResults : browseResults;
  const queueDownload = useQueueDownload("radiojavan_track");
  const status = useSystemStatus();
  const isQueueUnavailable = status.data?.redis.health !== "ok" && status.isSuccess;

  useEffect(() => {
    setQuery(queryFromUrl);
  }, [queryFromUrl]);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const submitted = query.trim();
    if (submitted.length === 0) {
      navigate(routes.radioJavan);
      return;
    }
    navigate(`${routes.radioJavan}/search?q=${encodeURIComponent(submitted)}`);
  }

  function download(result: RemoteResult) {
    queueDownload.mutate(result.candidate, {
      onSuccess: () =>
        toast.success("Queued for download", {
          description: `${result.candidate.title} joins the download queue.`,
        }),
      onError: (error) =>
        toast.error("That download could not be queued", {
          description:
            error instanceof ApiRequestError ? error.message : "The server did not respond.",
        }),
    });
  }

  const items = results.data?.items ?? [];

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-2">
        <div className="flex items-center gap-2">
          <Badge variant="outline">Dedicated source</Badge>
          <span className="type-meta text-foreground-subtle">Anonymous discovery</span>
        </div>
        <h1 className="type-title text-foreground">Radio Javan</h1>
        <p className="max-w-copy type-meta text-foreground-muted">
          Find a track on Radio Javan, bring the original MP3 into Chillify, and listen locally.
        </p>
      </header>

      <form
        onSubmit={submit}
        className="flex flex-col items-stretch gap-3 sm:flex-row sm:items-end"
      >
        <Field className="min-w-0 flex-1">
          <FieldLabel htmlFor="radio-javan-query">Search Radio Javan</FieldLabel>
          <Input
            id="radio-javan-query"
            value={query}
            autoComplete="off"
            placeholder="Track or artist"
            onChange={(event) => setQuery(event.target.value)}
          />
        </Field>
        <Button type="submit" disabled={query.trim().length === 0}>
          <Search data-icon="inline-start" aria-hidden="true" />
          Search
        </Button>
      </form>

      {isQueueUnavailable ? (
        <Alert>
          <AlertTitle>Downloads are paused</AlertTitle>
          <AlertDescription>
            The queue is unreachable. Your local library still plays.
          </AlertDescription>
        </Alert>
      ) : null}

      {queryFromUrl.length === 0 ? (
        <Tabs value={section} onValueChange={(value) => setSection(value as RadioJavanSection)}>
          <TabsList aria-label="Radio Javan sections">
            <TabsTrigger value="featured">Featured</TabsTrigger>
            <TabsTrigger value="trending">Trending</TabsTrigger>
          </TabsList>
        </Tabs>
      ) : null}
      {results.isPending ? <RadioJavanLoading /> : null}
      {results.isError ? (
        <Alert variant="destructive">
          <AlertTitle>
            Radio Javan could not be {queryFromUrl.length > 0 ? "searched" : "loaded"}
          </AlertTitle>
          <AlertDescription className="flex flex-col items-start gap-2">
            <span>
              {results.error instanceof ApiRequestError
                ? results.error.message
                : "The provider did not respond."}
            </span>
            <Button variant="outline" size="sm" onClick={() => void results.refetch()}>
              Retry
            </Button>
          </AlertDescription>
        </Alert>
      ) : null}
      {results.isSuccess && items.length === 0 ? (
        <Empty>
          <EmptyHeader>
            <EmptyMedia variant="icon">
              <Music2 />
            </EmptyMedia>
            <EmptyTitle>
              No {queryFromUrl.length > 0 ? "Radio Javan tracks" : `${section} tracks`} found
            </EmptyTitle>
            <EmptyDescription>
              {queryFromUrl.length > 0
                ? `0 tracks for “${queryFromUrl}”. Try a different title or artist.`
                : "Try the other Radio Javan section."}
            </EmptyDescription>
          </EmptyHeader>
        </Empty>
      ) : null}
      {results.isSuccess && items.length > 0 ? (
        <section aria-labelledby="radio-javan-results" className="flex flex-col gap-3">
          <div className="flex items-baseline justify-between gap-4">
            <div>
              <h2 id="radio-javan-results" className="type-section text-foreground">
                {queryFromUrl.length > 0
                  ? "Search results"
                  : section === "featured"
                    ? "Featured"
                    : "Trending"}
              </h2>
              <p className="type-meta text-foreground-muted">
                {queryFromUrl.length > 0
                  ? `${items.length} ${items.length === 1 ? "track" : "tracks"} for “${queryFromUrl}”`
                  : `First page · ${items.length} ${items.length === 1 ? "track" : "tracks"}`}
              </p>
            </div>
            <Badge variant="secondary">Radio Javan</Badge>
          </div>
          <ul className="grid gap-3 lg:grid-cols-2">
            {items.map((result) => (
              <RadioJavanResultCard
                key={result.candidate.source_url}
                result={result}
                isPending={
                  queueDownload.isPending &&
                  queueDownload.variables?.source_url === result.candidate.source_url
                }
                isDisabled={isQueueUnavailable}
                onDownload={download}
              />
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}

function useRadioJavanSearch(query: string) {
  return useQuery({
    queryKey: queryKeys.radioJavanSearch(query),
    enabled: query.length > 0,
    // The server resolves duplicate ownership. Re-entering a deep link after
    // acquisition must therefore fetch that fresh local state rather than
    // reuse an immutable discovery snapshot.
    refetchOnMount: "always",
    staleTime: Number.POSITIVE_INFINITY,
    retry: false,
    queryFn: async () =>
      unwrap(
        await api.GET("/api/v1/radio-javan/search", {
          params: { query: { q: query, limit: 15 } },
        }),
      ),
  });
}

function useRadioJavanBrowse(section: RadioJavanSection, enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.radioJavanBrowse(section),
    enabled,
    staleTime: Number.POSITIVE_INFINITY,
    retry: false,
    queryFn: async () =>
      unwrap(
        await api.GET("/api/v1/radio-javan/tracks", {
          params: { query: { section } },
        }),
      ),
  });
}

function RadioJavanLoading() {
  return (
    <div className="flex flex-col gap-3" role="status">
      <span className="type-meta text-foreground-muted">Searching Radio Javan…</span>
      <ul className="grid gap-3 lg:grid-cols-2" aria-label="Loading Radio Javan results">
        {[0, 1].map((item) => (
          <li key={item}>
            <Skeleton className="h-44 w-full" />
          </li>
        ))}
      </ul>
    </div>
  );
}

function RadioJavanResultCard({
  result,
  isPending,
  isDisabled,
  onDownload,
}: {
  result: RemoteResult;
  isPending: boolean;
  isDisabled: boolean;
  onDownload: (result: RemoteResult) => void;
}) {
  const { candidate } = result;
  return (
    <li>
      <Card className="h-full overflow-hidden bg-surface-raised">
        <CardHeader className="gap-4 pb-0">
          <div className="flex gap-4">
            <AspectRatio
              ratio={1}
              className="w-24 shrink-0 overflow-hidden rounded-lg bg-muted"
            >
              {candidate.artwork_url ? (
                <img
                  src={candidate.artwork_url}
                  alt={`${candidate.title} by ${candidate.artist}`}
                  className="size-full object-cover"
                />
              ) : (
                <div className="flex size-full items-center justify-center text-2xl font-semibold text-muted-foreground">
                  RJ
                </div>
              )}
            </AspectRatio>
            <div className="min-w-0 flex-1">
              <CardTitle className="truncate text-base">{candidate.title}</CardTitle>
              <p className="mt-2 truncate type-meta text-foreground-muted">
                {candidate.artist}
              </p>
              {candidate.album ? (
                <p className="truncate type-meta text-foreground-subtle">{candidate.album}</p>
              ) : null}
            </div>
          </div>
        </CardHeader>
        <CardContent className="flex flex-1 items-end pt-5">
          <p className="type-meta text-foreground-subtle">
            Radio Javan source · {formatDuration(candidate.duration_ms)}
          </p>
        </CardContent>
        <CardFooter className="justify-between gap-3">
          <span className="type-meta text-foreground-muted" role="status">
            {isPending ? "Adding to Downloads…" : "MP3 · not playable remotely"}
          </span>
          {result.existing_track_id === null ? (
            <Button
              disabled={isDisabled || isPending}
              aria-label={`Download ${candidate.title}`}
              onClick={() => onDownload(result)}
            >
              <Download data-icon="inline-start" aria-hidden="true" />
              {isPending ? "Queueing…" : "Download"}
            </Button>
          ) : (
            <Button variant="outline" asChild>
              <Link
                to={routes.library}
                aria-label={`Already in your library: ${candidate.title}`}
              >
                <Library data-icon="inline-start" aria-hidden="true" />
                Already in your library
              </Link>
            </Button>
          )}
        </CardFooter>
      </Card>
    </li>
  );
}

function formatDuration(durationMs: number | null) {
  if (durationMs === null) return "—";
  const seconds = Math.round(durationMs / 1000);
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}
