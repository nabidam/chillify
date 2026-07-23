import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiRequestError, api, type DeleteImpact, unwrap } from "@/api/client";
import { LIBRARY_QUERY_PREFIX, PLAYLISTS_QUERY_PREFIX, queryKeys } from "@/api/queryKeys";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { selectCurrentTrackId, usePlayerStore } from "@/features/player/playerStore";
import { useRestoreFocusOnClose } from "@/features/shared/restoreFocusOnClose";

/** How many times this track sits in the browser's current session queue. */
function sessionOccurrences(queue: string[], trackId: string): number {
  return queue.reduce((count, id) => (id === trackId ? count + 1 : count), 0);
}

/** One human sentence combining the server's playlist references and the session. */
function impactSentences(
  impact: DeleteImpact,
  queueCount: number,
  isCurrent: boolean,
): string[] {
  const lines: string[] = [];
  if (impact.playlist_count > 0) {
    lines.push(
      impact.playlist_count === 1
        ? "It is in 1 playlist, which will lose it."
        : `It is in ${impact.playlist_count} playlists, which will lose it.`,
    );
  }
  if (isCurrent) {
    lines.push("It is playing right now; playback will move on.");
  } else if (queueCount > 0) {
    lines.push(
      queueCount === 1
        ? "It is queued once in this session and will be removed."
        : `It is queued ${queueCount} times in this session and will be removed.`,
    );
  }
  return lines;
}

/**
 * S15 — Delete-track confirmation.
 *
 * Deleting a shared track is permanent for the whole household, so the primary
 * action is Cancel and the destructive one is only enabled once the impact has
 * resolved. The server owns the playlist count; the current-track and queue
 * occurrences come from this browser's own session store, which the server
 * never sees.
 */
export function DeleteTrackDialog({
  trackId,
  trackTitle,
  trackArtist,
  revision,
  open,
  onOpenChange,
  onDeleted,
}: {
  trackId: string | null;
  trackTitle: string;
  trackArtist: string;
  revision: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onDeleted?: () => void;
}) {
  const queryClient = useQueryClient();
  const queue = usePlayerStore((state) => state.queue);
  const currentTrackId = usePlayerStore(selectCurrentTrackId);

  const impact = useQuery({
    queryKey: queryKeys.deleteImpact(trackId ?? ""),
    enabled: open && trackId !== null,
    queryFn: async (): Promise<DeleteImpact> =>
      unwrap(
        await api.GET("/api/v1/tracks/{track_id}/delete-impact", {
          params: { path: { track_id: trackId as string } },
        }),
      ),
  });

  const remove = useMutation({
    mutationFn: async (): Promise<void> => {
      const result = await api.DELETE("/api/v1/tracks/{track_id}", {
        params: {
          path: { track_id: trackId as string },
          header: { "If-Match": String(revision) },
        },
      });
      if (result.error !== undefined) {
        unwrap(result);
      }
    },
    onSuccess: () => {
      // The track leaves every library, artist, album, and year context, and any
      // playlist that held it, so both prefixes are invalidated.
      void queryClient.invalidateQueries({ queryKey: LIBRARY_QUERY_PREFIX });
      void queryClient.invalidateQueries({ queryKey: PLAYLISTS_QUERY_PREFIX });
    },
  });

  const isResolved = impact.isSuccess;
  const isDeleting = remove.isPending;
  const failure = remove.error instanceof ApiRequestError ? remove.error : null;
  const queueCount = trackId === null ? 0 : sessionOccurrences(queue, trackId);
  const isCurrent = trackId !== null && currentTrackId === trackId;
  const details =
    impact.data !== undefined ? impactSentences(impact.data, queueCount, isCurrent) : [];

  function handleOpenChange(next: boolean) {
    if (isDeleting) {
      return;
    }
    if (!next) {
      remove.reset();
    }
    onOpenChange(next);
  }

  async function confirmDelete(event: React.MouseEvent) {
    // The alert dialog would close on click; the deletion owns the close so a
    // failure can keep the dialog open with its message.
    event.preventDefault();
    if (!isResolved || isDeleting) {
      return;
    }
    try {
      await remove.mutateAsync();
      onDeleted?.();
      onOpenChange(false);
    } catch {
      // The track remains authoritative; the alert below says the deletion did
      // not complete and Delete Permanently stays available for a retry.
    }
  }

  const onCloseAutoFocus = useRestoreFocusOnClose(open);

  return (
    <AlertDialog open={open} onOpenChange={handleOpenChange}>
      <AlertDialogContent onCloseAutoFocus={onCloseAutoFocus}>
        <AlertDialogHeader>
          <AlertDialogTitle>Delete this track for everyone?</AlertDialogTitle>
          <AlertDialogDescription>
            {trackTitle} — {trackArtist} will be permanently removed from the shared library.
            This cannot be undone.
          </AlertDialogDescription>
        </AlertDialogHeader>

        {impact.isPending ? (
          <div className="flex flex-col gap-2 py-2" aria-hidden="true">
            <Skeleton className="h-row w-full" />
            <Skeleton className="h-row w-3/4" />
          </div>
        ) : null}

        {impact.isError ? (
          <Alert variant="destructive">
            <AlertTitle>The impact could not be checked</AlertTitle>
            <AlertDescription>
              <span className="type-meta">
                {impact.error instanceof ApiRequestError
                  ? impact.error.message
                  : "The server did not respond."}{" "}
                Deletion is disabled until it can be confirmed.
              </span>
            </AlertDescription>
          </Alert>
        ) : null}

        {isResolved && details.length > 0 ? (
          <ul className="type-meta flex list-disc flex-col gap-1 pl-5 text-foreground-subtle">
            {details.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        ) : null}

        {failure !== null ? (
          <Alert variant="destructive">
            <AlertTitle>This track was not deleted</AlertTitle>
            <AlertDescription>
              <span className="type-meta">{failure.message} It is still in the library.</span>
            </AlertDescription>
          </Alert>
        ) : null}

        <AlertDialogFooter>
          <AlertDialogCancel disabled={isDeleting}>Cancel</AlertDialogCancel>
          <AlertDialogAction
            variant="destructive"
            disabled={!isResolved || isDeleting}
            onClick={confirmDelete}
          >
            {isDeleting ? "Deleting…" : "Delete Permanently"}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
