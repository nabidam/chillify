"""The managed media root: path resolution, task workspaces, and publication.

Every path that reaches the filesystem passes through here. A stored relative
path is data, and data is never trusted to stay inside its root: absolute
paths, traversal segments, and symlinks that leave the root are all refused
before an open is attempted.

Publication is the one moment a downloaded file becomes part of the library. It
moves within a single filesystem so the rename is atomic, and it never
overwrites: a collision either is an exact duplicate, which is refused, or gets
a deterministic suffix.
"""

from __future__ import annotations

import hashlib
import shutil
import unicodedata
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from pathvalidate import sanitize_filename

from chillify.domain.errors import (
    StorageUnwritableError,
    UnsafeMediaPathError,
)

# The managed layout. `Music` and `Artwork` hold the library a person browses
# over SMB; everything Chillify needs but nobody should open lives under the
# single dotted directory.
MUSIC_DIRECTORY = "Music"
ARTWORK_DIRECTORY = "Artwork"
INTERNAL_DIRECTORY = ".chillify"
WORK_DIRECTORY = "work"

AUDIO_SUFFIX = ".mp3"
ARTWORK_SUFFIX = ".jpg"

# Filesystems commonly cap one name at 255 bytes. Components are capped well
# below that so the two-digit prefix, separator, and suffix always fit.
_COMPONENT_BYTE_LIMIT = 96

UNKNOWN_ARTIST_DIRECTORY = "Unknown Artist"
UNKNOWN_ALBUM_DIRECTORY = "Unknown Album"
UNKNOWN_TITLE_COMPONENT = "Unknown Title"

# Windows reserved device names. The mounted volume can be shared over SMB, so
# a relative path carrying one would resolve to a device rather than a file.
_RESERVED_STEMS = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{digit}" for digit in range(1, 10)}
    | {f"lpt{digit}" for digit in range(1, 10)}
)


def resolve_managed_path(music_root: Path, relative_path: str) -> Path:
    """Return the absolute path of a managed file inside `music_root`.

    Raises `UnsafeMediaPathError` when the stored value does not name a location
    beneath the root. The error carries no path: what escaped is exactly what
    must not be echoed back.
    """
    if not relative_path or relative_path != relative_path.strip():
        raise UnsafeMediaPathError("A stored media path is not usable.")

    candidate = PurePosixPath(relative_path)
    if candidate.is_absolute() or candidate.drive or candidate.root:
        raise UnsafeMediaPathError("A stored media path is not usable.")

    # The raw segments are inspected rather than `PurePosixPath.parts`, which
    # silently drops `.` and would let a noncanonical stored value through.
    for segment in relative_path.split("/"):
        if segment in ("", "..", "."):
            raise UnsafeMediaPathError("A stored media path is not usable.")
        if "\x00" in segment or segment.split(".")[0].casefold() in _RESERVED_STEMS:
            raise UnsafeMediaPathError("A stored media path is not usable.")

    root = music_root.resolve(strict=False)
    resolved = (root / Path(*candidate.parts)).resolve(strict=False)
    # `resolve` follows symlinks, so this single check also refuses a symlink
    # inside the root that points outside it.
    if resolved != root and root not in resolved.parents:
        raise UnsafeMediaPathError("A stored media path is not usable.")
    return resolved


# -- task workspaces --------------------------------------------------------


def job_workspace(music_root: Path, job_id: str) -> Path:
    """Create and return the task-local workspace for one job.

    It lives under the music root rather than a temporary directory so the
    final move into the library is a rename on one filesystem, not a copy that
    could half-succeed.
    """
    workspace = music_root / INTERNAL_DIRECTORY / WORK_DIRECTORY / _safe_component(job_id)
    try:
        workspace.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise StorageUnwritableError(
            "The music folder is not writable, so the download cannot start."
        ) from exc
    return workspace


def remove_workspace(workspace: Path) -> None:
    """Discard a workspace and everything in it.

    Called on cancellation, failure, and after publication. A workspace that
    cannot be removed is leaked disk, not a failed job, so it never raises.
    """
    shutil.rmtree(workspace, ignore_errors=True)


# -- publication ------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PublishedFile:
    """One acquired file after it has become part of the managed library."""

    relative_path: str
    size_bytes: int
    content_sha256: str
    reused_existing_file: bool = False


def organized_relpath(
    *,
    artist: str,
    album: str | None,
    title: str,
    track_number: int | None,
) -> str:
    """The managed location for one track, as `Music/{Artist}/{Album}/{NN - Title}.mp3`.

    Every component is sanitized independently: a value that sanitizes away
    entirely becomes its deterministic Unknown form rather than an empty path
    segment, which would silently move the file up a directory.
    """
    artist_directory = _safe_component(artist, fallback=UNKNOWN_ARTIST_DIRECTORY)
    album_directory = _safe_component(album or "", fallback=UNKNOWN_ALBUM_DIRECTORY)
    name = _safe_component(title, fallback=UNKNOWN_TITLE_COMPONENT)
    if track_number is not None:
        name = f"{_track_prefix(track_number)} - {name}"
    return f"{MUSIC_DIRECTORY}/{artist_directory}/{album_directory}/{name}{AUDIO_SUFFIX}"


def publish_audio(music_root: Path, source: Path, relative_path: str) -> PublishedFile:
    """Move one acquired file into the library at `relative_path`.

    A collision never overwrites. An identical file is reused so a previous
    interrupted publication can be indexed on a retry; a different file with
    the same sanitized name gets a short suffix derived from its own content,
    so the same input always lands in the same place.
    """
    digest = _sha256(source)
    size = source.stat().st_size
    target = resolve_managed_path(music_root, relative_path)

    if target.exists():
        if _sha256(target) == digest:
            return PublishedFile(
                relative_path=relative_path,
                size_bytes=size,
                content_sha256=digest,
                reused_existing_file=True,
            )
        relative_path = _suffixed(relative_path, digest[:8])
        target = resolve_managed_path(music_root, relative_path)

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        # Same filesystem by construction: the workspace lives under this root,
        # so the replace is atomic and never leaves a partial file visible.
        source.replace(target)
    except OSError as exc:
        raise StorageUnwritableError("The music folder refused the finished download.") from exc

    return PublishedFile(relative_path=relative_path, size_bytes=size, content_sha256=digest)


def publish_artwork(music_root: Path, source: Path, identifier: str) -> str:
    """Move one normalized cover into the managed Artwork directory."""
    relative_path = f"{ARTWORK_DIRECTORY}/{_safe_component(identifier)}{ARTWORK_SUFFIX}"
    target = resolve_managed_path(music_root, relative_path)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        source.replace(target)
    except OSError as exc:
        raise StorageUnwritableError("The music folder refused the downloaded cover art.") from exc
    return relative_path


def _track_prefix(track_number: int) -> str:
    """Two digits through 99, and the full number above that."""
    return f"{track_number:02d}" if track_number < 100 else str(track_number)


def _suffixed(relative_path: str, suffix: str) -> str:
    head, _, name = relative_path.rpartition("/")
    stem = name.removesuffix(AUDIO_SUFFIX)
    return f"{head}/{stem} [{suffix}]{AUDIO_SUFFIX}"


def _safe_component(value: str, *, fallback: str | None = None) -> str:
    """Reduce one metadata value to a single safe path component."""
    normalized = unicodedata.normalize("NFC", value)
    # Separators are removed before sanitizing so an artist named "AC/DC"
    # becomes one component rather than two directories.
    flattened = normalized.replace("/", " ").replace("\\", " ")
    cleaned = str(sanitize_filename(flattened, platform="universal", replacement_text=" "))
    collapsed = " ".join(cleaned.split()).strip(". ")
    bounded = _cap_bytes(collapsed, _COMPONENT_BYTE_LIMIT)
    if not bounded or bounded.split(".")[0].casefold() in _RESERVED_STEMS:
        if fallback is None:
            raise UnsafeMediaPathError("A media path component is not usable.")
        return fallback
    return bounded


def _cap_bytes(value: str, limit: int) -> str:
    """Truncate to `limit` UTF-8 bytes without splitting a character."""
    encoded = value.encode("utf-8")
    if len(encoded) <= limit:
        return value
    return encoded[:limit].decode("utf-8", errors="ignore").strip()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
