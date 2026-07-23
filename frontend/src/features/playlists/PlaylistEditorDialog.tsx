import { useEffect, useState } from "react";
import { ApiRequestError } from "@/api/client";
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
import { useCreatePlaylist, useRenamePlaylist } from "@/features/playlists/playlistQueries";
import { useRestoreFocusOnClose } from "@/features/shared/restoreFocusOnClose";

/**
 * S16 — Playlist editor dialog.
 *
 * Only the name is editable. There is no artwork, sharing, collaboration, or
 * profile management here, and the same dialog serves creating and renaming so
 * the two never drift apart.
 */
export function PlaylistEditorDialog({
  open,
  onOpenChange,
  profileId,
  playlist,
  onSaved,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  profileId: string | null;
  /** Present when renaming; absent when creating. */
  playlist?: { id: string; name: string; revision: number };
  onSaved?: (playlistId: string) => void;
}) {
  const isRename = playlist !== undefined;
  const [name, setName] = useState(playlist?.name ?? "");
  const create = useCreatePlaylist(profileId);
  const rename = useRenamePlaylist();
  const mutation = isRename ? rename : create;

  // Reopening the dialog must show the current name, not whatever was typed
  // and abandoned last time.
  useEffect(() => {
    if (open) {
      setName(playlist?.name ?? "");
      create.reset();
      rename.reset();
    }
    // The reset helpers are stable for a given mutation instance; re-running
    // this on every render would clear an in-flight error the person is reading.
  }, [open, playlist?.name, create.reset, rename.reset]);

  const trimmed = name.trim();
  const isBlank = trimmed.length === 0;
  const failure = mutation.error;
  const message =
    failure instanceof ApiRequestError
      ? failure.message
      : failure
        ? "The playlist could not be saved."
        : null;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (isBlank || mutation.isPending) {
      return;
    }
    try {
      if (isRename) {
        await rename.mutateAsync({
          playlistId: playlist.id,
          name: trimmed,
          revision: playlist.revision,
        });
        onSaved?.(playlist.id);
      } else {
        const created = await create.mutateAsync(trimmed);
        onSaved?.(created.id);
      }
      onOpenChange(false);
    } catch {
      // The field keeps its value so the person can correct the name and retry;
      // the message is rendered from the mutation's own error state below.
    }
  }

  const onCloseAutoFocus = useRestoreFocusOnClose(open);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent onCloseAutoFocus={onCloseAutoFocus}>
        <form onSubmit={submit} noValidate>
          <DialogHeader>
            <DialogTitle>{isRename ? "Rename playlist" : "New playlist"}</DialogTitle>
            <DialogDescription>
              Playlists belong to the profile that is currently active.
            </DialogDescription>
          </DialogHeader>

          <Field data-invalid={isBlank && name !== "" ? true : undefined} className="py-4">
            <FieldLabel htmlFor="playlist-name">Name</FieldLabel>
            <Input
              id="playlist-name"
              value={name}
              autoComplete="off"
              maxLength={100}
              disabled={mutation.isPending}
              aria-invalid={message !== null || (isBlank && name !== "")}
              aria-describedby={message !== null ? "playlist-name-error" : undefined}
              onChange={(event) => setName(event.target.value)}
            />
            {message !== null ? (
              <FieldError id="playlist-name-error">{message}</FieldError>
            ) : null}
          </Field>

          <DialogFooter>
            <DialogClose asChild>
              <Button type="button" variant="ghost" disabled={mutation.isPending}>
                Cancel
              </Button>
            </DialogClose>
            <Button type="submit" disabled={isBlank || mutation.isPending}>
              {mutation.isPending ? "Saving…" : isRename ? "Save" : "Create"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
