import { Loader2Icon } from "lucide-react";
import { ApiRequestError } from "@/api/client";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import {
  DISPLAY_STATE_LABELS,
  type DownloadJob,
  isActive,
  phaseLabel,
  useCancelDownload,
  useRetryDownload,
} from "@/features/downloads/downloadJobs";

/**
 * S11 — one download row with its truthful state and the actions it allows.
 *
 * The row renders exactly what the server durably recorded: a determinate bar
 * only when a real percentage exists, Cancel only while work is still ahead,
 * and Retry only on a finished failure or cancellation. Nothing here invents
 * progress or offers an action the state machine would refuse.
 */
export function DownloadRow({ job }: { job: DownloadJob }) {
  return (
    <div className="flex flex-col gap-2 rounded-md bg-surface-raised px-4 py-3">
      <div className="flex w-full min-w-0 items-center gap-3">
        <StateBadge job={job} />
        <div className="min-w-0 flex-1 text-left">
          <p className="type-label truncate text-foreground">{phaseLabel(job)}</p>
          <p className="type-meta truncate text-foreground-muted">
            {job.provider} · {job.source_type.replaceAll("_", " ")}
          </p>
        </div>
        <RowActions job={job} />
      </div>

      {isActive(job) ? <ProgressReadout job={job} /> : null}
      {job.error_message !== null ? (
        <p className="type-meta text-destructive">{job.error_message}</p>
      ) : null}
    </div>
  );
}

function ProgressReadout({ job }: { job: DownloadJob }) {
  if (job.progress_percent === null) {
    return (
      <p className="type-meta text-foreground-subtle">
        This step reports no percentage; the phase above is the real progress.
      </p>
    );
  }
  return (
    <Progress
      value={job.progress_percent}
      className="bg-progress-track"
      aria-label={`${phaseLabel(job)} progress`}
      // The registry component styles the bar but does not forward the value to
      // the primitive, so the announced value is supplied here rather than by
      // hand-editing generated source.
      aria-valuenow={job.progress_percent}
      aria-valuetext={`${Math.round(job.progress_percent)} percent`}
    />
  );
}

function RowActions({ job }: { job: DownloadJob }) {
  const cancel = useCancelDownload();
  const retry = useRetryDownload();

  if (isActive(job)) {
    const message = cancel.error instanceof ApiRequestError ? cancel.error.message : null;
    return (
      <div className="flex shrink-0 flex-col items-end gap-1">
        <Button
          variant="outline"
          size="sm"
          disabled={cancel.isPending}
          onClick={() => cancel.mutate({ jobId: job.id, version: job.version })}
        >
          {cancel.isPending ? (
            <Loader2Icon className="animate-spin" aria-hidden="true" />
          ) : null}
          Cancel
        </Button>
        {message !== null ? (
          <span className="type-meta text-destructive" role="alert">
            {message}
          </span>
        ) : null}
      </div>
    );
  }

  if (job.state === "failed" || job.state === "cancelled") {
    const message = retry.error instanceof ApiRequestError ? retry.error.message : null;
    return (
      <div className="flex shrink-0 flex-col items-end gap-1">
        <Button
          variant="outline"
          size="sm"
          disabled={retry.isPending}
          onClick={() => retry.mutate({ jobId: job.id })}
        >
          {retry.isPending ? <Loader2Icon className="animate-spin" aria-hidden="true" /> : null}
          Retry
        </Button>
        {message !== null ? (
          <span className="type-meta text-destructive" role="alert">
            {message}
          </span>
        ) : null}
      </div>
    );
  }

  return (
    <span className="type-meta shrink-0 text-foreground-subtle tabular-nums">
      {new Date(job.created_at).toLocaleTimeString()}
    </span>
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
