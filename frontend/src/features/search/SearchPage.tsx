import { useQuery } from "@tanstack/react-query";
import { GlobeIcon, SearchIcon } from "lucide-react";
import { type FormEvent, useState } from "react";
import { toast } from "sonner";
import { ApiRequestError, api, unwrap } from "@/api/client";
import { queryKeys } from "@/api/queryKeys";
import { useSystemStatus } from "@/app/useSystemStatus";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty";
import { Field, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import { TrackTable, TrackTablePlaceholder } from "@/features/library/TrackTable";
import { usePlayerStore } from "@/features/player/playerStore";
import { ResultCards, ResultCardsPlaceholder } from "@/features/search/ResultCards";
import {
  type RemoteResult,
  useDeezerSearch,
  useQueueDownload,
} from "@/features/search/remoteSearch";

/**
 * S3 — Search.
 *
 * Local first, and structurally so: typing queries the library, and only the
 * Search Deezer button reaches the internet. Local and internet content never
 * intermix — they are separate regions with a separator between them.
 */
export function SearchPage() {
  const [query, setQuery] = useState("");
  const [submission, setSubmission] = useState("");
  const playQueue = usePlayerStore((state) => state.playQueue);

  const status = useSystemStatus();
  const local = useLocalSearch(query);
  const remote = useDeezerSearch(submission);
  const queueDownload = useQueueDownload();

  const localItems = local.data?.items ?? [];
  const remoteItems = remote.data?.items ?? [];
  const isQueueUnavailable = status.data?.redis.health !== "ok" && status.isSuccess;

  function submitOnlineSearch(event: FormEvent) {
    event.preventDefault();
    setSubmission(query.trim());
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

  return (
    <div className="flex flex-col gap-5">
      <header>
        <h1 className="type-title text-foreground">Search</h1>
        <p className="type-meta text-foreground-muted">
          Chillify searches your library as you type. Searching the internet is a separate,
          deliberate step.
        </p>
      </header>

      <form onSubmit={submitOnlineSearch} className="flex items-end gap-3">
        <Field className="flex-1">
          <FieldLabel htmlFor="search-query">Track or artist</FieldLabel>
          <Input
            id="search-query"
            value={query}
            autoComplete="off"
            placeholder="Search your library"
            onChange={(event) => setQuery(event.target.value)}
          />
        </Field>
        <Button type="submit" variant="outline" disabled={query.trim().length === 0}>
          <GlobeIcon className="size-4" aria-hidden="true" />
          Search Deezer
        </Button>
      </form>

      <section aria-labelledby="local-results" className="flex flex-col gap-3">
        <h2 id="local-results" className="type-section text-foreground">
          In your library
        </h2>

        {local.isPending ? <TrackTablePlaceholder rows={3} /> : null}

        {local.isError ? (
          <Alert variant="destructive">
            <AlertTitle>Your library could not be searched</AlertTitle>
            <AlertDescription>
              <span className="type-meta">
                {local.error instanceof ApiRequestError
                  ? local.error.message
                  : "The server did not respond."}
              </span>
            </AlertDescription>
          </Alert>
        ) : null}

        {local.isSuccess && localItems.length === 0 ? (
          <Empty>
            <EmptyHeader>
              <EmptyMedia variant="icon">
                <SearchIcon />
              </EmptyMedia>
              <EmptyTitle>
                {query.trim().length === 0 ? "Search your library" : "No local matches"}
              </EmptyTitle>
              <EmptyDescription>
                {query.trim().length === 0
                  ? "Type to filter the tracks Chillify already manages. Searching Deezer is a separate button."
                  : "Nothing in your library matches that. Search Deezer to find it online."}
              </EmptyDescription>
            </EmptyHeader>
          </Empty>
        ) : null}

        {local.isSuccess && localItems.length > 0 ? (
          <TrackTable
            tracks={localItems}
            onPlay={(index) =>
              playQueue(
                localItems.map((item) => item.id),
                index,
              )
            }
          />
        ) : null}
      </section>

      <Separator />

      <section aria-labelledby="online-results" className="flex flex-col gap-3">
        <h2 id="online-results" className="type-section text-foreground">
          From the internet
        </h2>
        <p className="type-meta text-foreground-muted" role="status">
          <OnlineStatusLine
            submission={submission}
            isPending={remote.isFetching}
            resultCount={remoteItems.length}
            isSuccess={remote.isSuccess}
          />
        </p>

        {isQueueUnavailable ? (
          <Alert>
            <AlertTitle>Downloads are paused</AlertTitle>
            <AlertDescription>
              <span className="type-meta">
                The download queue is unreachable, so new downloads are disabled. Your library
                still plays.
              </span>
            </AlertDescription>
          </Alert>
        ) : null}

        {remote.isFetching ? <ResultCardsPlaceholder /> : null}

        {remote.isError ? (
          <Alert variant="destructive">
            <AlertTitle>Deezer could not be searched</AlertTitle>
            <AlertDescription>
              <span className="type-meta">
                {remote.error instanceof ApiRequestError
                  ? remote.error.message
                  : "The provider did not respond."}
              </span>
              <Button
                variant="outline"
                size="sm"
                className="mt-2 w-fit"
                onClick={() => void remote.refetch()}
              >
                Try again
              </Button>
            </AlertDescription>
          </Alert>
        ) : null}

        {remote.isSuccess && !remote.isFetching && remoteItems.length > 0 ? (
          <ResultCards
            results={remoteItems}
            onDownload={download}
            pendingSourceUrl={
              queueDownload.isPending ? (queueDownload.variables?.source_url ?? null) : null
            }
            isDownloadDisabled={isQueueUnavailable}
            disabledReason={
              isQueueUnavailable ? "The download queue is currently unreachable." : null
            }
          />
        ) : null}
      </section>
    </div>
  );
}

function OnlineStatusLine({
  submission,
  isPending,
  resultCount,
  isSuccess,
}: {
  submission: string;
  isPending: boolean;
  resultCount: number;
  isSuccess: boolean;
}) {
  if (submission.length === 0) {
    return <>Nothing has been sent to Deezer. Press Search Deezer to look online.</>;
  }
  if (isPending) {
    return <>Contacting Deezer…</>;
  }
  if (isSuccess) {
    return (
      <>
        {resultCount} {resultCount === 1 ? "result" : "results"} from Deezer for “{submission}”.
      </>
    );
  }
  return <>Deezer did not answer this search.</>;
}

/** The local half of S3: the library query, reacting to every keystroke. */
function useLocalSearch(query: string) {
  const trimmed = query.trim();
  return useQuery({
    queryKey: queryKeys.libraryTracks({ q: trimmed }),
    queryFn: async () =>
      unwrap(
        await api.GET("/api/v1/library/tracks", {
          params: { query: trimmed.length > 0 ? { q: trimmed } : {} },
        }),
      ),
  });
}
