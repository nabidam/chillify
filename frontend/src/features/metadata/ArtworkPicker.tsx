import { ImageIcon, Link2, Upload } from "lucide-react";
import { useId, useRef, useState } from "react";
import {
  ApiRequestError,
  type ArtworkStage,
  api,
  artworkStageUrl,
  type LastfmArtworkStage,
  trackArtworkUrl,
  unwrap,
} from "@/api/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

/**
 * The cover preview and its three replacement actions.
 *
 * Picking a cover never changes the track: it stages an image and hands the
 * stage ID up, so the one Save in S13 is what finally applies it. An artwork
 * failure is therefore always recoverable — the metadata can still be saved
 * without it, which is exactly what the warning below says.
 */
export function ArtworkPicker({
  trackId,
  revision,
  hasArtwork,
  stage,
  onStaged,
  onLastfmMetadata,
  disabled,
  identity,
}: {
  trackId: string;
  revision: number;
  hasArtwork: boolean;
  /** The stage this editor has chosen but not yet saved. */
  stage: ArtworkStage | null;
  onStaged: (stage: ArtworkStage | null) => void;
  onLastfmMetadata: (metadata: LastfmArtworkStage["metadata"]) => void;
  disabled: boolean;
  /** Current field values, so a Last.fm lookup follows the edits on screen. */
  identity: { artist: string; title: string; album: string | null };
}) {
  const fileInputId = useId();
  const fileInput = useRef<HTMLInputElement>(null);
  const [url, setUrl] = useState("");
  const [isBusy, setBusy] = useState(false);
  const [warning, setWarning] = useState<string | null>(null);

  async function stageWith(request: () => Promise<ArtworkStage>) {
    setBusy(true);
    setWarning(null);
    try {
      onStaged(await request());
    } catch (failure) {
      // Artwork is optional by design: the warning explains that the metadata
      // can still be saved, rather than blocking the whole editor.
      setWarning(
        failure instanceof ApiRequestError
          ? failure.message
          : "That cover image could not be prepared.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function lookupLastfm() {
    setBusy(true);
    setWarning(null);
    try {
      const result = unwrap(
        await api.POST("/api/v1/artwork/stages/lastfm", {
          body: {
            artist: identity.artist,
            title: identity.title,
            album: identity.album,
          },
        }),
      );
      onStaged(result.stage);
      onLastfmMetadata(result.metadata);
    } catch (failure) {
      setWarning(
        failure instanceof ApiRequestError
          ? failure.message
          : "That Last.fm lookup could not be completed.",
      );
    } finally {
      setBusy(false);
    }
  }

  const previewSource = stage !== null ? artworkStageUrl(stage.id) : null;
  const publishedSource = hasArtwork ? trackArtworkUrl(trackId, revision) : null;
  const source = previewSource ?? publishedSource;

  return (
    <div className="flex gap-4">
      <div className="size-cover-md shrink-0 overflow-hidden rounded-md bg-cover-placeholder">
        {source !== null ? (
          <img
            src={source}
            alt={stage !== null ? "Selected cover, not yet saved" : "Current cover"}
            className="size-full object-cover"
          />
        ) : (
          <div className="flex size-full items-center justify-center">
            <ImageIcon className="size-6 text-foreground-subtle" aria-hidden="true" />
          </div>
        )}
      </div>

      <div className="flex min-w-0 flex-1 flex-col gap-2">
        <div className="flex flex-wrap gap-2">
          <input
            id={fileInputId}
            ref={fileInput}
            type="file"
            accept="image/*"
            // Visually replaced by the Upload button, but it stays a labelled
            // control so keyboard and screen-reader users reach the real input.
            aria-label="Upload a cover image"
            className="sr-only"
            disabled={disabled || isBusy}
            onChange={(event) => {
              const file = event.target.files?.[0];
              event.target.value = "";
              if (file === undefined) {
                return;
              }
              void stageWith(async () => {
                const body = new FormData();
                body.append("file", file);
                return unwrap(
                  await api.POST("/api/v1/artwork/stages/upload", {
                    body: body as unknown as { file: string },
                  }),
                );
              });
            }}
          />
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="gap-2"
            disabled={disabled || isBusy}
            onClick={() => fileInput.current?.click()}
          >
            <Upload className="size-4" aria-hidden="true" />
            Upload
          </Button>

          <Button
            type="button"
            variant="outline"
            size="sm"
            className="gap-2"
            disabled={disabled || isBusy || identity.artist === "" || identity.title === ""}
            onClick={() => void lookupLastfm()}
          >
            Last.fm
          </Button>

          {stage !== null ? (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              disabled={disabled || isBusy}
              onClick={() => {
                onStaged(null);
                setWarning(null);
              }}
            >
              Undo
            </Button>
          ) : null}
        </div>

        <div className="flex gap-2">
          <Input
            value={url}
            placeholder="Paste an image link"
            aria-label="Cover image link"
            disabled={disabled || isBusy}
            onChange={(event) => setUrl(event.target.value)}
          />
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="gap-2"
            disabled={disabled || isBusy || url.trim() === ""}
            onClick={() =>
              void stageWith(async () =>
                unwrap(
                  await api.POST("/api/v1/artwork/stages/url", { body: { url: url.trim() } }),
                ),
              )
            }
          >
            <Link2 className="size-4" aria-hidden="true" />
            Fetch
          </Button>
        </div>

        {warning !== null ? (
          <p role="status" className="type-meta text-warning">
            {warning} You can still save the rest of this track's details.
          </p>
        ) : null}
        {stage !== null ? (
          <p className="type-meta text-foreground-subtle">
            This cover is applied when you save.
          </p>
        ) : null}
      </div>
    </div>
  );
}
