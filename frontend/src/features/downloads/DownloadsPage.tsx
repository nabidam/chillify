import { DownloadIcon } from "lucide-react";
import { Link } from "react-router";
import { ApiRequestError } from "@/api/client";
import { useEventBridgeState } from "@/app/EventBridge";
import { routes } from "@/app/routes";
import { useSystemStatus } from "@/app/useSystemStatus";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import {
  DISPLAY_STATE_LABELS,
  type DownloadJob,
  historyOrder,
  phaseLabel,
  queueOrder,
  useDownloads,
} from "@/features/downloads/downloadJobs";

/**
 * S11 — Downloads.
 *
 * Server-owned state, rendered exactly as durably recorded. Progress is
 * determinate only when the provider reported a real percentage; otherwise the
 * row shows the phase and no bar, because an invented bar is a lie about work.
 */
export function DownloadsPage() {
  const bridge = useEventBridgeState();
  const status = useSystemStatus();
  const downloads = useDownloads();

  const jobs = downloads.data?.items ?? [];
  const active = queueOrder(jobs);
  const history = historyOrder(jobs);
  const isQueueUnavailable = status.isSuccess && status.data.redis.health !== "ok";

  return (
    <div className="flex flex-col gap-5">
      <header className="flex items-baseline justify-between gap-4">
        <div>
          <h1 className="type-title text-foreground">Downloads</h1>
          <p className="type-meta text-foreground-muted">
            Downloads continue whether or not this page is open.
          </p>
        </div>
        {bridge === "reconnecting" ? (
          <Badge variant="outline" className="border-warning text-warning">
            Reconnecting — states may be stale
          </Badge>
        ) : null}
      </header>

      {isQueueUnavailable ? (
        <Alert>
          <AlertTitle>The download queue is unreachable</AlertTitle>
          <AlertDescription>
            <span className="type-meta">
              New downloads are disabled until the queue returns. Your library still plays.
            </span>
          </AlertDescription>
        </Alert>
      ) : null}

      {downloads.isPending ? (
        <div className="flex flex-col gap-2" aria-hidden="true">
          {[0, 1, 2].map((row) => (
            <Skeleton key={row} className="h-row w-full" />
          ))}
        </div>
      ) : null}

      {downloads.isError ? (
        <Alert variant="destructive">
          <AlertTitle>The download queue could not be read</AlertTitle>
          <AlertDescription>
            <span className="type-meta">
              {downloads.error instanceof ApiRequestError
                ? downloads.error.message
                : "The server did not respond."}
            </span>
            <Button
              variant="outline"
              size="sm"
              className="mt-2 w-fit"
              onClick={() => void downloads.refetch()}
            >
              Retry
            </Button>
          </AlertDescription>
        </Alert>
      ) : null}

      {downloads.isSuccess && jobs.length === 0 ? (
        <Empty>
          <EmptyHeader>
            <EmptyMedia variant="icon">
              <DownloadIcon />
            </EmptyMedia>
            <EmptyTitle>No downloads yet</EmptyTitle>
            <EmptyDescription>
              Downloads keep running without this page open. Start one from Search.
            </EmptyDescription>
          </EmptyHeader>
          <EmptyContent>
            <Button variant="outline" asChild>
              <Link to={routes.search}>Go to Search</Link>
            </Button>
          </EmptyContent>
        </Empty>
      ) : null}

      {active.length > 0 ? (
        <section aria-labelledby="download-queue" className="flex flex-col gap-3">
          <h2 id="download-queue" className="type-section text-foreground">
            In the queue
          </h2>
          <ul className="flex flex-col gap-2">
            {active.map((job) => (
              <li key={job.id}>
                <JobRow job={job} />
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {history.length > 0 ? (
        <section aria-labelledby="download-history" className="flex flex-col gap-3">
          <h2 id="download-history" className="type-section text-foreground">
            Finished
          </h2>
          <Accordion type="multiple" className="flex flex-col gap-2">
            {history.map((job) => (
              <AccordionItem
                key={job.id}
                value={job.id}
                className="rounded-md bg-surface-raised"
              >
                <AccordionTrigger className="px-4">
                  <JobSummary job={job} />
                </AccordionTrigger>
                <AccordionContent className="px-4">
                  <JobDiagnostics job={job} />
                </AccordionContent>
              </AccordionItem>
            ))}
          </Accordion>
        </section>
      ) : null}
    </div>
  );
}

function JobRow({ job }: { job: DownloadJob }) {
  return (
    <div className="flex flex-col gap-2 rounded-md bg-surface-raised px-4 py-3">
      <JobSummary job={job} />
      {job.progress_percent === null ? (
        <p className="type-meta text-foreground-subtle">
          This step reports no percentage; the phase above is the real progress.
        </p>
      ) : (
        <Progress
          value={job.progress_percent}
          className="bg-progress-track"
          aria-label={`${phaseLabel(job)} progress`}
          // The registry component styles the bar but does not forward the
          // value to the primitive, so the announced value is supplied here
          // rather than by hand-editing generated source.
          aria-valuenow={job.progress_percent}
          aria-valuetext={`${Math.round(job.progress_percent)} percent`}
        />
      )}
    </div>
  );
}

function JobSummary({ job }: { job: DownloadJob }) {
  return (
    <div className="flex w-full min-w-0 items-center gap-3">
      <StateBadge job={job} />
      <div className="min-w-0 flex-1 text-left">
        <p className="type-label truncate text-foreground">{phaseLabel(job)}</p>
        <p className="type-meta truncate text-foreground-muted">
          {job.provider} · {job.source_type.replaceAll("_", " ")}
        </p>
      </div>
      <span className="type-meta shrink-0 text-foreground-subtle tabular-nums">
        {new Date(job.created_at).toLocaleTimeString()}
      </span>
    </div>
  );
}

function StateBadge({ job }: { job: DownloadJob }) {
  const label = DISPLAY_STATE_LABELS[job.display_state];
  if (job.state === "failed") {
    return (
      <Badge variant="outline" className="border-destructive text-destructive">
        {label}
      </Badge>
    );
  }
  if (job.state === "completed") {
    return <Badge variant="outline">{label}</Badge>;
  }
  return (
    <Badge variant="outline" className="border-info text-info">
      {label}
    </Badge>
  );
}

/**
 * Disclosed detail: the plain-language summary is above, and the technical
 * record stays behind this expansion rather than shouting at everyone.
 */
function JobDiagnostics({ job }: { job: DownloadJob }) {
  return (
    <dl className="type-meta grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-foreground-muted">
      <dt>State</dt>
      <dd>{DISPLAY_STATE_LABELS[job.display_state]}</dd>
      <dt>Phase</dt>
      <dd>{phaseLabel(job)}</dd>
      <dt>Started</dt>
      <dd>{job.started_at === null ? "—" : new Date(job.started_at).toLocaleString()}</dd>
      <dt>Finished</dt>
      <dd>{job.finished_at === null ? "—" : new Date(job.finished_at).toLocaleString()}</dd>
      {job.restart_count > 0 ? (
        <>
          <dt>Restarts</dt>
          <dd>{job.restart_count}</dd>
        </>
      ) : null}
      {job.error_message !== null ? (
        <>
          <dt>Reason</dt>
          <dd className="text-destructive">{job.error_message}</dd>
        </>
      ) : null}
    </dl>
  );
}
