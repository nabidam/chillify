import type { ReactNode } from "react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";

/**
 * The four states every server-backed view moves through, named so a screen
 * declares which one it is in rather than reinventing the branch each time.
 *
 * `pending` and `error` map straight from a TanStack Query result; a view that
 * has loaded but has nothing to show is `success` with `isEmpty`, because an
 * empty library is a real, successful answer and not a failure.
 */
type DataStatus = "pending" | "error" | "success";

/**
 * A recoverable error surface, shared so the route boundary and any data view
 * fail the same way: a titled reason, an optional detail, and an optional
 * retry that never claims to have fixed anything on its own.
 */
export function ErrorState({
  title,
  description,
  onRetry,
  retryLabel = "Try again",
}: {
  title: string;
  description?: ReactNode;
  onRetry?: () => void;
  retryLabel?: string;
}) {
  return (
    <Alert variant="destructive">
      <AlertTitle>{title}</AlertTitle>
      <AlertDescription>
        {description === undefined ? null : <span className="type-meta">{description}</span>}
        {onRetry === undefined ? null : (
          <Button variant="outline" size="sm" className="mt-2 w-fit" onClick={onRetry}>
            {retryLabel}
          </Button>
        )}
      </AlertDescription>
    </Alert>
  );
}

/**
 * The state machine for a data view.
 *
 * Loading geometry is announced as busy so a screen reader hears that work is
 * in flight, while the skeleton itself is hidden from the accessibility tree —
 * the placeholder shapes are chrome, not content. Error and empty are terminal
 * branches; only `success` with content renders `children`.
 */
export function DataState({
  status,
  isEmpty = false,
  loading,
  empty,
  error,
  children,
}: {
  status: DataStatus;
  isEmpty?: boolean;
  loading: ReactNode;
  empty: ReactNode;
  error: { title: string; description?: ReactNode; onRetry?: () => void };
  children: ReactNode;
}) {
  if (status === "pending") {
    return (
      <div role="status" aria-live="polite">
        <span className="sr-only">Loading</span>
        <div aria-hidden="true">{loading}</div>
      </div>
    );
  }

  if (status === "error") {
    return (
      <ErrorState title={error.title} description={error.description} onRetry={error.onRetry} />
    );
  }

  if (isEmpty) {
    return <>{empty}</>;
  }

  return <>{children}</>;
}
