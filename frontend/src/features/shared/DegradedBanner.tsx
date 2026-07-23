import { useSystemStatus } from "@/app/useSystemStatus";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";

/**
 * The shell-wide degradation notice.
 *
 * Degradation is surfaced, never inferred: the banner appears only on a
 * confirmed status that reports it, so an in-flight or failed status request
 * stays silent rather than claiming a problem it has not observed. Readiness
 * and degradation are separate — the library always plays, so the message
 * says which capability is reduced without implying the app is down.
 *
 * The persistent notice lives here, above every route, so it does not vanish
 * on navigation. Per-view detail (the exact failing queue row, a retry) stays
 * with the view that owns it.
 */
export function DegradedBanner() {
  const { data, isSuccess } = useSystemStatus();

  if (!isSuccess || !data.degraded) {
    return null;
  }

  const isQueueUnreachable = data.redis.health !== "ok";
  const title = isQueueUnreachable
    ? "Downloads are paused while the queue is unreachable"
    : "New downloads may fail right now";
  const detail = isQueueUnreachable
    ? "Everything already in your library still plays. New downloads resume on their own when the queue returns."
    : "A required tool is unavailable, so starting new downloads may fail. Everything already in your library still plays.";

  return (
    <Alert className="rounded-none border-x-0 border-t-0 border-warning text-warning">
      <AlertTitle>{title}</AlertTitle>
      <AlertDescription>
        <span className="type-meta text-warning">{detail}</span>
      </AlertDescription>
    </Alert>
  );
}
