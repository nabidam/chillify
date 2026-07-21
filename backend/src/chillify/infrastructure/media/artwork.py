"""Cover-image validation, normalization, and staging.

Every image that reaches Chillify — uploaded, fetched from a URL, or returned
by an enricher — passes through `normalize_cover`. What comes out is always one
baseline JPEG of bounded size, so the tag writer and the managed `Artwork`
directory only ever see one format and the browser cannot decide otherwise.

Staged images live under `.chillify/staging/artwork/` and belong to nobody
until a save consumes them. They are deliberately outside `Artwork/`: a person
browsing the share over SMB should see covers for tracks, not for edits that
were never finished.
"""

from __future__ import annotations

import hashlib
import io
import os
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from PIL import Image, UnidentifiedImageError

from chillify.domain.errors import (
    ArtworkTooLargeError,
    ArtworkUnreadableError,
    StorageUnwritableError,
)
from chillify.infrastructure.media.storage import (
    ARTWORK_DIRECTORY,
    INTERNAL_DIRECTORY,
    resolve_managed_path,
)

STAGING_DIRECTORY: Final = "staging"
ARTWORK_STAGING_DIRECTORY: Final = "artwork"

ARTWORK_MIME_TYPE: Final = "image/jpeg"
ARTWORK_SUFFIX: Final = ".jpg"

# Matches the `size_bytes BETWEEN 1 AND 10485760` guard on `artwork_stages`.
# Enforced on the submitted bytes, before decoding, so an oversized upload is
# refused without ever being expanded in memory.
ARTWORK_MAX_BYTES: Final = 10 * 1024 * 1024

# Covers are square-ish album art displayed at a few hundred pixels at most.
# Downscaling here bounds both the embedded ID3 frame and the managed file; a
# 6000px scan would otherwise triple the size of every MP3 it is written into.
ARTWORK_MAX_EDGE: Final = 1000
ARTWORK_JPEG_QUALITY: Final = 88

# Pillow will happily allocate gigabytes for a crafted image header. The library
# guard raises `DecompressionBombError`, a subclass of `Image.DecompressionBombWarning`'s
# error form, which is caught with the other decode failures below.
Image.MAX_IMAGE_PIXELS = 64_000_000


@dataclass(frozen=True, slots=True)
class NormalizedCover:
    """One decoded, re-encoded cover image held in memory."""

    payload: bytes
    content_sha256: str

    @property
    def size_bytes(self) -> int:
        return len(self.payload)


def normalize_cover(data: bytes) -> NormalizedCover:
    """Decode arbitrary submitted bytes into one bounded baseline JPEG.

    Re-encoding rather than passing the original through is the point: it
    strips every embedded profile, comment, and appended payload, so what the
    tag writer embeds is image data and nothing else.
    """
    if not data:
        raise ArtworkUnreadableError("That cover image is empty.")
    if len(data) > ARTWORK_MAX_BYTES:
        raise ArtworkTooLargeError(
            "That cover image is larger than 10 MB.",
            context={"max_bytes": ARTWORK_MAX_BYTES},
        )

    try:
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            # `RGB` because JPEG has no alpha channel; a transparent PNG would
            # otherwise fail to encode rather than flatten.
            converted = image.convert("RGB")
            converted.thumbnail((ARTWORK_MAX_EDGE, ARTWORK_MAX_EDGE))
            buffer = io.BytesIO()
            converted.save(buffer, format="JPEG", quality=ARTWORK_JPEG_QUALITY, optimize=True)
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ArtworkUnreadableError("That file is not an image Chillify can use.") from exc

    payload = buffer.getvalue()
    return NormalizedCover(payload=payload, content_sha256=hashlib.sha256(payload).hexdigest())


def stage_relpath(stage_id: str) -> str:
    """The managed location of one staged cover, relative to the music root."""
    return (
        f"{INTERNAL_DIRECTORY}/{STAGING_DIRECTORY}/"
        f"{ARTWORK_STAGING_DIRECTORY}/{stage_id}{ARTWORK_SUFFIX}"
    )


def artwork_relpath(track_id: str) -> str:
    """The managed location of one track's published cover."""
    return f"{ARTWORK_DIRECTORY}/{track_id}{ARTWORK_SUFFIX}"


def write_stage(music_root: Path, stage_id: str, cover: NormalizedCover) -> str:
    """Persist one normalized cover as a staged file and return its relative path.

    The bytes are fsynced before the row that references them is written, so a
    crash can leave an unreferenced file — which cleanup removes — but never a
    row pointing at a file that was never durable.
    """
    relative = stage_relpath(stage_id)
    target = resolve_managed_path(music_root, relative)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("wb") as handle:
            handle.write(cover.payload)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        raise StorageUnwritableError("The cover image could not be stored.") from exc
    return relative


def remove_stage(music_root: Path, relative_path: str) -> None:
    """Discard one staged cover. A stage that is already gone is not an error."""
    # A staged file that cannot be removed is leaked disk that cleanup will find
    # again, never a reason to fail the save that consumed it.
    with suppress(OSError):
        resolve_managed_path(music_root, relative_path).unlink(missing_ok=True)
