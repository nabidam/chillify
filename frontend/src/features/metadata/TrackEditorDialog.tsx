import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import {
  ApiRequestError,
  type ArtworkStage,
  api,
  type TrackDetail,
  unwrap,
} from "@/api/client";
import { LIBRARY_QUERY_PREFIX, PLAYLISTS_QUERY_PREFIX, queryKeys } from "@/api/queryKeys";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
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
import { Skeleton } from "@/components/ui/skeleton";
import { ArtworkPicker } from "@/features/metadata/ArtworkPicker";
import { DeleteTrackDialog } from "@/features/metadata/DeleteTrackDialog";

interface EditorFields {
  title: string;
  artist: string;
  album: string;
  release_year: string;
  disc_number: string;
  track_number: string;
}

function fieldsOf(detail: TrackDetail): EditorFields {
  return {
    title: detail.track.title,
    artist: detail.track.artist,
    album: detail.track.album ?? "",
    release_year: detail.track.release_year?.toString() ?? "",
    disc_number: detail.track.disc_number?.toString() ?? "",
    track_number: detail.track.track_number?.toString() ?? "",
  };
}

/** An empty numeric field means absence; anything else must parse as a number. */
function numberOrNull(raw: string): number | null {
  const trimmed = raw.trim();
  return trimmed === "" ? null : Number(trimmed);
}

/**
 * S13 — Track details and editor.
 *
 * One Save covers metadata, embedded tags, cover art, the file's location, and
 * the database row. That is a deliberate property of the contract rather than a
 * convenience: partial saves are what leave a library disagreeing with itself.
 */
export function TrackEditorDialog({
  trackId,
  open,
  onOpenChange,
}: {
  trackId: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const queryClient = useQueryClient();
  const [fields, setFields] = useState<EditorFields | null>(null);
  const [stage, setStage] = useState<ArtworkStage | null>(null);
  const [confirmingDelete, setConfirmingDelete] = useState(false);

  const detail = useQuery({
    queryKey: queryKeys.track(trackId ?? ""),
    enabled: open && trackId !== null,
    queryFn: async (): Promise<TrackDetail> =>
      unwrap(
        await api.GET("/api/v1/tracks/{track_id}", {
          params: { path: { track_id: trackId as string } },
        }),
      ),
  });

  const save = useMutation({
    mutationFn: async (input: {
      fields: EditorFields;
      revision: number;
    }): Promise<TrackDetail> =>
      unwrap(
        await api.PATCH("/api/v1/tracks/{track_id}", {
          params: {
            path: { track_id: trackId as string },
            header: { "If-Match": String(input.revision) },
          },
          body: {
            title: input.fields.title,
            artist: input.fields.artist,
            album: input.fields.album.trim() === "" ? null : input.fields.album,
            release_year: numberOrNull(input.fields.release_year),
            disc_number: numberOrNull(input.fields.disc_number),
            track_number: numberOrNull(input.fields.track_number),
            artwork_stage_id: stage?.id ?? null,
          },
        }),
      ),
    onSuccess: (saved) => {
      // A correction can move the track between artist, album, and year
      // contexts, so the whole library prefix is invalidated rather than one
      // row; playlists carry track summaries and follow for the same reason.
      queryClient.setQueryData(queryKeys.track(saved.track.id), saved);
      void queryClient.invalidateQueries({ queryKey: LIBRARY_QUERY_PREFIX });
      void queryClient.invalidateQueries({ queryKey: PLAYLISTS_QUERY_PREFIX });
    },
  });

  // The loaded record seeds the form once. Edits are preserved across a failed
  // save, so a rejected value can be corrected rather than retyped.
  useEffect(() => {
    if (!open) {
      setFields(null);
      setStage(null);
      setConfirmingDelete(false);
      save.reset();
      return;
    }
    if (detail.data !== undefined && fields === null) {
      setFields(fieldsOf(detail.data));
    }
  }, [open, detail.data, fields, save.reset]);

  const isLoaded = detail.isSuccess && fields !== null;
  const isMissingFile = detail.data?.track.availability === "missing";
  const isSaving = save.isPending;
  const failure = save.error instanceof ApiRequestError ? save.error : null;
  const blankField =
    fields !== null && fields.title.trim() === ""
      ? "title"
      : fields !== null && fields.artist.trim() === ""
        ? "artist"
        : null;

  function update(key: keyof EditorFields, value: string) {
    setFields((current) => (current === null ? current : { ...current, [key]: value }));
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!isLoaded || isSaving || blankField !== null || isMissingFile) {
      return;
    }
    try {
      await save.mutateAsync({ fields, revision: detail.data.track.revision });
      onOpenChange(false);
    } catch {
      // The previous version remains authoritative; the alert below says so and
      // every edit stays on screen for a retry.
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <form onSubmit={submit} noValidate>
          <DialogHeader>
            <DialogTitle>Track details</DialogTitle>
            <DialogDescription>
              Saving rewrites this track's tags, cover, and location together.
            </DialogDescription>
          </DialogHeader>

          {detail.isPending ? (
            <div className="flex flex-col gap-3 py-4" aria-hidden="true">
              <Skeleton className="h-cover-md w-full" />
              <Skeleton className="h-row w-full" />
              <Skeleton className="h-row w-full" />
            </div>
          ) : null}

          {detail.isError ? (
            <Alert variant="destructive" className="my-4">
              <AlertTitle>This track could not be loaded</AlertTitle>
              <AlertDescription>
                <span className="type-meta">
                  {detail.error instanceof ApiRequestError
                    ? detail.error.message
                    : "The server did not respond."}
                </span>
              </AlertDescription>
            </Alert>
          ) : null}

          {isLoaded ? (
            <div className="flex flex-col gap-4 py-4">
              {isMissingFile ? (
                <Alert>
                  <AlertTitle>This track's file is missing</AlertTitle>
                  <AlertDescription>
                    <span className="type-meta">
                      Its details are kept here, but its tags and location cannot be rewritten
                      until the file is back.
                    </span>
                  </AlertDescription>
                </Alert>
              ) : null}

              <ArtworkPicker
                trackId={detail.data.track.id}
                revision={detail.data.track.revision}
                hasArtwork={detail.data.has_artwork}
                stage={stage}
                onStaged={setStage}
                disabled={isSaving || isMissingFile}
                identity={{
                  artist: fields.artist.trim(),
                  title: fields.title.trim(),
                  album: fields.album.trim() === "" ? null : fields.album.trim(),
                }}
              />

              <div className="grid gap-4 sm:grid-cols-2">
                <Field data-invalid={blankField === "title" ? true : undefined}>
                  <FieldLabel htmlFor="track-title">Title</FieldLabel>
                  <Input
                    id="track-title"
                    value={fields.title}
                    disabled={isSaving || isMissingFile}
                    aria-invalid={blankField === "title" || failure?.field === "title"}
                    onChange={(event) => update("title", event.target.value)}
                  />
                  {blankField === "title" ? (
                    <FieldError>A title cannot be empty.</FieldError>
                  ) : null}
                </Field>

                <Field data-invalid={blankField === "artist" ? true : undefined}>
                  <FieldLabel htmlFor="track-artist">Artist</FieldLabel>
                  <Input
                    id="track-artist"
                    value={fields.artist}
                    disabled={isSaving || isMissingFile}
                    aria-invalid={blankField === "artist" || failure?.field === "artist"}
                    onChange={(event) => update("artist", event.target.value)}
                  />
                  {blankField === "artist" ? (
                    <FieldError>An artist cannot be empty.</FieldError>
                  ) : null}
                </Field>

                <Field className="sm:col-span-2">
                  <FieldLabel htmlFor="track-album">Album</FieldLabel>
                  <Input
                    id="track-album"
                    value={fields.album}
                    disabled={isSaving || isMissingFile}
                    aria-invalid={failure?.field === "album"}
                    onChange={(event) => update("album", event.target.value)}
                  />
                </Field>

                <Field>
                  <FieldLabel htmlFor="track-year">Year</FieldLabel>
                  <Input
                    id="track-year"
                    inputMode="numeric"
                    value={fields.release_year}
                    disabled={isSaving || isMissingFile}
                    aria-invalid={failure?.field === "release_year"}
                    onChange={(event) => update("release_year", event.target.value)}
                  />
                </Field>

                <div className="grid grid-cols-2 gap-4">
                  <Field>
                    <FieldLabel htmlFor="track-disc">Disc</FieldLabel>
                    <Input
                      id="track-disc"
                      inputMode="numeric"
                      value={fields.disc_number}
                      disabled={isSaving || isMissingFile}
                      aria-invalid={failure?.field === "disc_number"}
                      onChange={(event) => update("disc_number", event.target.value)}
                    />
                  </Field>
                  <Field>
                    <FieldLabel htmlFor="track-number">Track</FieldLabel>
                    <Input
                      id="track-number"
                      inputMode="numeric"
                      value={fields.track_number}
                      disabled={isSaving || isMissingFile}
                      aria-invalid={failure?.field === "track_number"}
                      onChange={(event) => update("track_number", event.target.value)}
                    />
                  </Field>
                </div>
              </div>

              {detail.data.sources.length > 0 ? (
                <div className="flex flex-wrap items-center gap-2">
                  <span className="type-meta text-foreground-subtle">Source</span>
                  {detail.data.sources.map((source) => (
                    <Badge key={`${source.provider}-${source.source_id}`} variant="outline">
                      {source.provider}
                      {source.source_id !== null ? ` · ${source.source_id}` : ""}
                    </Badge>
                  ))}
                </div>
              ) : null}

              {failure !== null ? (
                <Alert variant="destructive">
                  <AlertTitle>This track was not saved</AlertTitle>
                  <AlertDescription>
                    <span className="type-meta">
                      {failure.message} The previous version is still what plays.
                    </span>
                  </AlertDescription>
                </Alert>
              ) : null}
            </div>
          ) : null}

          <DialogFooter>
            {isLoaded ? (
              <Button
                type="button"
                variant="destructive"
                className="sm:mr-auto"
                disabled={isSaving}
                onClick={() => setConfirmingDelete(true)}
              >
                Delete track
              </Button>
            ) : null}
            <DialogClose asChild>
              <Button type="button" variant="ghost" disabled={isSaving}>
                Cancel
              </Button>
            </DialogClose>
            <Button
              type="submit"
              disabled={!isLoaded || isSaving || blankField !== null || isMissingFile}
            >
              {isSaving ? "Saving…" : "Save"}
            </Button>
          </DialogFooter>
        </form>

        {isLoaded ? (
          <DeleteTrackDialog
            trackId={detail.data.track.id}
            trackTitle={detail.data.track.title}
            trackArtist={detail.data.track.artist}
            revision={detail.data.track.revision}
            open={confirmingDelete}
            onOpenChange={setConfirmingDelete}
            onDeleted={() => onOpenChange(false)}
          />
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
