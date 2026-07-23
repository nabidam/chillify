import { DownloadIcon, LibraryIcon } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router";
import { toast } from "sonner";
import { ApiRequestError } from "@/api/client";
import { routes } from "@/app/routes";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Field, FieldError, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  type LinkInspection,
  useInspectLink,
  useQueueReviewedDownload,
} from "@/features/acquisition/acquisitionQueries";
import { YouTubeReviewDialog } from "@/features/acquisition/YouTubeReviewDialog";
import { useRestoreFocusOnClose } from "@/features/shared/restoreFocusOnClose";

/**
 * S4 — Add Track by Link.
 *
 * Only URL acquisition happens here, and only for one Spotify track or one
 * YouTube video. Inspection is explicit and separate from queueing: a Spotify
 * track can be downloaded straight from its inspected candidate, while a YouTube
 * video continues to the S5 review dialog instead of queueing immediately.
 */
export function AddLinkDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [url, setUrl] = useState("");
  // The inspected Spotify candidate awaiting a Download press. YouTube results
  // never live here — they transition straight to review.
  const [detected, setDetected] = useState<LinkInspection | null>(null);
  const [reviewing, setReviewing] = useState<LinkInspection | null>(null);
  const inspect = useInspectLink();
  const queue = useQueueReviewedDownload();

  // Reopening the dialog starts a clean submission rather than showing the last
  // link's result or a stale error.
  useEffect(() => {
    if (open) {
      setUrl("");
      setDetected(null);
      inspect.reset();
      queue.reset();
    }
    // The reset helpers are stable per mutation instance; re-running on every
    // render would clear an error or result the person is still reading.
  }, [open, inspect.reset, queue.reset]);

  const trimmed = url.trim();
  const inspectFailure = inspect.error;
  const inspectMessage =
    inspectFailure instanceof ApiRequestError
      ? inspectFailure.message
      : inspectFailure
        ? "That link could not be inspected."
        : null;

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (trimmed.length === 0 || inspect.isPending) {
      return;
    }
    setDetected(null);
    inspect.mutate(trimmed, {
      onSuccess: (result) => {
        if (result.review_required) {
          // Transition S4 → S5: close this dialog and open the review.
          onOpenChange(false);
          setReviewing(result);
        } else {
          setDetected(result);
        }
      },
    });
  }

  function downloadDetected() {
    if (detected === null) {
      return;
    }
    queue.mutate(
      { source_type: detected.source_type, candidate: detected.candidate },
      {
        onSuccess: () => {
          toast.success("Queued for download", {
            description: `${detected.candidate.title} joins the download queue.`,
          });
          onOpenChange(false);
        },
        onError: (error) =>
          toast.error("That download could not be queued", {
            description:
              error instanceof ApiRequestError ? error.message : "The server did not respond.",
          }),
      },
    );
  }

  const onCloseAutoFocus = useRestoreFocusOnClose(open);

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent onCloseAutoFocus={onCloseAutoFocus}>
          <form onSubmit={submit} noValidate>
            <DialogHeader>
              <DialogTitle>Add music by link</DialogTitle>
              <DialogDescription>
                Paste a link to one Spotify track or one YouTube video. Albums and playlists are
                not supported.
              </DialogDescription>
            </DialogHeader>

            <div className="flex flex-col gap-4 py-4">
              <Field data-invalid={inspectMessage !== null ? true : undefined}>
                <FieldLabel htmlFor="add-link-url">Link</FieldLabel>
                <Input
                  id="add-link-url"
                  value={url}
                  autoComplete="off"
                  inputMode="url"
                  placeholder="https://open.spotify.com/track/… or https://youtu.be/…"
                  disabled={inspect.isPending}
                  aria-invalid={inspectMessage !== null}
                  aria-describedby={inspectMessage !== null ? "add-link-error" : undefined}
                  onChange={(event) => {
                    setUrl(event.target.value);
                    setDetected(null);
                  }}
                />
                {inspectMessage !== null ? (
                  <FieldError id="add-link-error">{inspectMessage}</FieldError>
                ) : (
                  <p className="type-meta text-foreground-subtle">
                    For example a single track or video URL — not an album, playlist, or
                    channel.
                  </p>
                )}
              </Field>

              {inspect.isPending ? <Skeleton className="h-row w-full" /> : null}

              {detected !== null && !inspect.isPending ? (
                <DetectedResult
                  inspection={detected}
                  isQueueing={queue.isPending}
                  onDownload={downloadDetected}
                />
              ) : null}
            </div>

            <DialogFooter>
              <DialogClose asChild>
                <Button type="button" variant="ghost" disabled={inspect.isPending}>
                  Cancel
                </Button>
              </DialogClose>
              <Button type="submit" disabled={trimmed.length === 0 || inspect.isPending}>
                {inspect.isPending ? "Inspecting…" : "Continue"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <YouTubeReviewDialog
        open={reviewing !== null}
        inspection={reviewing}
        onOpenChange={(next) => {
          if (!next) {
            setReviewing(null);
          }
        }}
      />
    </>
  );
}

/** The inspected Spotify track, ready to download or already in the library. */
function DetectedResult({
  inspection,
  isQueueing,
  onDownload,
}: {
  inspection: LinkInspection;
  isQueueing: boolean;
  onDownload: () => void;
}) {
  const { candidate } = inspection;
  const isDuplicate = inspection.existing_track_id != null;

  return (
    <Card className="bg-surface-raised">
      <CardContent className="flex items-center gap-4 py-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="type-label truncate text-foreground">{candidate.title}</span>
            <Badge variant="outline" className="border-info text-info">
              {candidate.provider}
            </Badge>
          </div>
          <p className="type-meta truncate text-foreground-muted">
            {candidate.artist}
            {candidate.album ? ` — ${candidate.album}` : ""}
          </p>
        </div>

        {isDuplicate ? (
          <Button variant="outline" size="sm" className="shrink-0" asChild>
            <Link to={routes.library}>
              <LibraryIcon className="size-4" aria-hidden="true" />
              Already in your library
            </Link>
          </Button>
        ) : (
          <Button size="sm" className="shrink-0" disabled={isQueueing} onClick={onDownload}>
            {isQueueing ? (
              "Queueing…"
            ) : (
              <>
                <DownloadIcon className="size-4" aria-hidden="true" />
                Download
              </>
            )}
          </Button>
        )}
      </CardContent>
    </Card>
  );
}
