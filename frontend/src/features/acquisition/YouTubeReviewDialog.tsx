import { ImageOff } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router";
import { toast } from "sonner";
import { ApiRequestError } from "@/api/client";
import { routes } from "@/app/routes";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
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
import {
  type LinkInspection,
  type TrackCandidate,
  useQueueReviewedDownload,
} from "@/features/acquisition/acquisitionQueries";
import { useRestoreFocusOnClose } from "@/features/shared/restoreFocusOnClose";

interface ReviewFields {
  title: string;
  artist: string;
  album: string;
  release_year: string;
  disc_number: string;
  track_number: string;
}

function reviewFieldsOf(candidate: TrackCandidate): ReviewFields {
  return {
    title: candidate.title,
    artist: candidate.artist,
    album: candidate.album ?? "",
    release_year: candidate.release_year?.toString() ?? "",
    disc_number: candidate.disc_number?.toString() ?? "",
    track_number: candidate.track_number?.toString() ?? "",
  };
}

/** An empty numeric field means absence; anything else must parse as a number. */
function numberOrNull(raw: string): number | null {
  const trimmed = raw.trim();
  return trimmed === "" ? null : Number(trimmed);
}

/**
 * S5 — YouTube Metadata Review.
 *
 * YouTube metadata is unreliable, so a video is never queued from what the
 * extractor returned: the person corrects the common tags first. Only title and
 * artist are required; the reviewed values become the immutable download
 * request, and artwork is optional after a warning.
 */
export function YouTubeReviewDialog({
  open,
  onOpenChange,
  inspection,
  onQueued,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The inspected YouTube candidate under review; absent until one is opened. */
  inspection: LinkInspection | null;
  onQueued?: () => void;
}) {
  const candidate = inspection?.candidate ?? null;
  const [fields, setFields] = useState<ReviewFields>(() =>
    candidate ? reviewFieldsOf(candidate) : blankFields(),
  );
  const queue = useQueueReviewedDownload();

  // Reopening on a different link must show that link's extracted values, not
  // whatever was typed and abandoned last time. `candidate` changes identity
  // with each inspection, so it alone captures "a different link".
  useEffect(() => {
    if (open && candidate) {
      setFields(reviewFieldsOf(candidate));
      queue.reset();
    }
    // `queue.reset` is stable for a given mutation instance; re-running this on
    // every render would clear an in-flight error the person is reading.
  }, [open, candidate, queue.reset]);

  const titleBlank = fields.title.trim().length === 0;
  const artistBlank = fields.artist.trim().length === 0;
  const isDuplicate = inspection?.existing_track_id != null;
  const failure = queue.error;
  const message =
    failure instanceof ApiRequestError
      ? failure.message
      : failure
        ? "That track could not be queued."
        : null;

  function update(key: keyof ReviewFields, value: string) {
    setFields((current) => ({ ...current, [key]: value }));
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!candidate || titleBlank || artistBlank || isDuplicate || queue.isPending) {
      return;
    }
    const reviewed: TrackCandidate = {
      ...candidate,
      title: fields.title.trim(),
      artist: fields.artist.trim(),
      album: fields.album.trim() === "" ? null : fields.album.trim(),
      release_year: numberOrNull(fields.release_year),
      disc_number: numberOrNull(fields.disc_number),
      track_number: numberOrNull(fields.track_number),
    };
    try {
      await queue.mutateAsync({ source_type: "youtube_video", candidate: reviewed });
      toast.success("Queued for download", {
        description: `${reviewed.title} joins the download queue.`,
      });
      onQueued?.();
      onOpenChange(false);
    } catch {
      // The fields keep their values so the person can correct and retry; the
      // message is rendered from the mutation's own error state below.
    }
  }

  const onCloseAutoFocus = useRestoreFocusOnClose(open);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="max-h-[85vh] overflow-y-auto"
        onCloseAutoFocus={onCloseAutoFocus}
      >
        <form onSubmit={submit} noValidate>
          <DialogHeader>
            <DialogTitle>Review before downloading</DialogTitle>
            <DialogDescription>
              YouTube titles are often messy. Correct the details before this track joins the
              queue.
            </DialogDescription>
          </DialogHeader>

          <div className="flex flex-col gap-4 py-4">
            <div className="flex items-center gap-4">
              <CoverPreview url={candidate?.artwork_url ?? null} title={fields.title} />
              <p className="type-meta min-w-0 truncate text-foreground-subtle">
                {candidate?.source_url}
              </p>
            </div>

            {isDuplicate ? (
              <Alert>
                <AlertTitle>Already in your library</AlertTitle>
                <AlertDescription className="flex flex-col items-start gap-2">
                  <span className="type-meta">
                    A matching track already exists, so this one will not be queued.
                  </span>
                  <Button variant="outline" size="sm" asChild>
                    <Link to={routes.library}>Open your library</Link>
                  </Button>
                </AlertDescription>
              </Alert>
            ) : null}

            <div className="grid grid-cols-2 gap-4">
              <Field
                className="col-span-2"
                data-invalid={titleBlank && fields.title !== "" ? true : undefined}
              >
                <FieldLabel htmlFor="review-title">Title</FieldLabel>
                <Input
                  id="review-title"
                  value={fields.title}
                  autoComplete="off"
                  disabled={queue.isPending}
                  aria-invalid={titleBlank && fields.title !== ""}
                  onChange={(event) => update("title", event.target.value)}
                />
                {titleBlank ? <FieldError>A title is required.</FieldError> : null}
              </Field>

              <Field
                className="col-span-2"
                data-invalid={artistBlank && fields.artist !== "" ? true : undefined}
              >
                <FieldLabel htmlFor="review-artist">Artist</FieldLabel>
                <Input
                  id="review-artist"
                  value={fields.artist}
                  autoComplete="off"
                  disabled={queue.isPending}
                  aria-invalid={artistBlank && fields.artist !== ""}
                  onChange={(event) => update("artist", event.target.value)}
                />
                {artistBlank ? <FieldError>An artist is required.</FieldError> : null}
              </Field>

              <Field className="col-span-2">
                <FieldLabel htmlFor="review-album">Album</FieldLabel>
                <Input
                  id="review-album"
                  value={fields.album}
                  autoComplete="off"
                  disabled={queue.isPending}
                  onChange={(event) => update("album", event.target.value)}
                />
              </Field>

              <Field>
                <FieldLabel htmlFor="review-year">Year</FieldLabel>
                <Input
                  id="review-year"
                  value={fields.release_year}
                  inputMode="numeric"
                  autoComplete="off"
                  disabled={queue.isPending}
                  onChange={(event) => update("release_year", event.target.value)}
                />
              </Field>

              <Field>
                <FieldLabel htmlFor="review-disc">Disc</FieldLabel>
                <Input
                  id="review-disc"
                  value={fields.disc_number}
                  inputMode="numeric"
                  autoComplete="off"
                  disabled={queue.isPending}
                  onChange={(event) => update("disc_number", event.target.value)}
                />
              </Field>

              <Field>
                <FieldLabel htmlFor="review-track">Track number</FieldLabel>
                <Input
                  id="review-track"
                  value={fields.track_number}
                  inputMode="numeric"
                  autoComplete="off"
                  disabled={queue.isPending}
                  onChange={(event) => update("track_number", event.target.value)}
                />
              </Field>
            </div>

            {message !== null ? (
              <Alert variant="destructive">
                <AlertTitle>That track could not be queued</AlertTitle>
                <AlertDescription>
                  <span className="type-meta">{message}</span>
                </AlertDescription>
              </Alert>
            ) : null}
          </div>

          <DialogFooter>
            <DialogClose asChild>
              <Button type="button" variant="ghost" disabled={queue.isPending}>
                Cancel
              </Button>
            </DialogClose>
            <Button
              type="submit"
              disabled={titleBlank || artistBlank || isDuplicate || queue.isPending}
            >
              {queue.isPending ? "Queueing…" : "Queue download"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function CoverPreview({ url, title }: { url: string | null; title: string }) {
  if (url === null) {
    return (
      <div
        className="flex size-16 shrink-0 items-center justify-center rounded-md bg-surface-raised text-foreground-subtle"
        aria-hidden="true"
      >
        <ImageOff className="size-5" />
      </div>
    );
  }
  return (
    <img
      src={url}
      alt={`Cover for ${title}`}
      className="size-16 shrink-0 rounded-md object-cover"
      referrerPolicy="no-referrer"
    />
  );
}

function blankFields(): ReviewFields {
  return {
    title: "",
    artist: "",
    album: "",
    release_year: "",
    disc_number: "",
    track_number: "",
  };
}
