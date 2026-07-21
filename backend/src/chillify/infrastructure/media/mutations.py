"""Crash-consistent media mutation mechanics.

A metadata edit changes four things that must agree: the MP3's tags, its
location under `Music/`, its cover under `Artwork/`, and the database row. This
module owns the filesystem half of that, in the order ARCHITECTURE section 8
fixes:

    stage a copy → hard-link recovery of the live files → atomically place the
    staged files → (the caller commits the database) → drop the old paths

No published file is ever edited in place, and no old path is removed until the
new record can already play. If the caller's commit fails, `restore_recovery`
puts the previous files back from links that were never unlinked, so the old
record stays authoritative.

Locks are advisory `filelock` locks on the shared mounted filesystem so a
second API process, the worker, and a household member's second browser tab all
serialize against the same files. The order is always `library.lock` then the
track lock; nothing here may invert it.
"""

from __future__ import annotations

import hashlib
import os
import shutil
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from filelock import FileLock, Timeout

from chillify.domain.errors import MutationLockedError, StorageUnwritableError
from chillify.infrastructure.media.storage import (
    AUDIO_SUFFIX,
    INTERNAL_DIRECTORY,
    resolve_managed_path,
)

LOCKS_DIRECTORY: Final = "locks"
RECOVERY_DIRECTORY: Final = "recovery"
STAGING_DIRECTORY: Final = "staging"

LIBRARY_LOCK_NAME: Final = "library.lock"
TRACK_LOCKS_DIRECTORY: Final = "tracks"

# Bounded, not indefinite: a save that waits longer than this reports
# `423 mutation_locked`, which the browser can retry, rather than holding a
# request open behind whatever else the household started.
LOCK_TIMEOUT_SECONDS: Final = 10.0


@contextmanager
def media_locks(
    music_root: Path, *, track_id: str, timeout: float = LOCK_TIMEOUT_SECONDS
) -> Iterator[None]:
    """Hold `library.lock` and then the track's lock for the whole mutation.

    Both are taken before any path is calculated and released only after the
    database commit and its cleanup, because the duplicate recheck and the
    commit have to see the same filesystem.
    """
    locks_root = music_root / INTERNAL_DIRECTORY / LOCKS_DIRECTORY
    track_locks_root = locks_root / TRACK_LOCKS_DIRECTORY
    try:
        track_locks_root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise StorageUnwritableError("The music folder is not writable.") from exc

    library_lock = FileLock(str(locks_root / LIBRARY_LOCK_NAME), timeout=timeout)
    track_lock = FileLock(str(track_locks_root / f"{_safe_id(track_id)}.lock"), timeout=timeout)
    try:
        library_lock.acquire()
    except Timeout as exc:
        raise MutationLockedError(
            "The library is busy with another change. Try saving again in a moment."
        ) from exc
    try:
        try:
            track_lock.acquire()
        except Timeout as exc:
            raise MutationLockedError(
                "This track is busy with another change. Try saving again in a moment."
            ) from exc
        try:
            yield
        finally:
            track_lock.release()
    finally:
        library_lock.release()


@dataclass(frozen=True, slots=True)
class StagedFile:
    """One file prepared outside the library, ready to be placed."""

    staged_path: Path
    intended_relpath: str


def staging_directory(music_root: Path, mutation_id: str) -> Path:
    """Create and return one mutation's staging directory.

    It sits under the music root so the final placement is a rename on one
    filesystem — an atomic operation that cannot leave a half-written file
    visible where a player would try to open it.
    """
    return _make_directory(
        music_root / INTERNAL_DIRECTORY / STAGING_DIRECTORY / _safe_id(mutation_id)
    )


def recovery_directory(music_root: Path, mutation_id: str) -> Path:
    """Create and return one mutation's recovery directory."""
    return _make_directory(
        music_root / INTERNAL_DIRECTORY / RECOVERY_DIRECTORY / _safe_id(mutation_id)
    )


def unused_relpath(music_root: Path, desired: str, *, keeping: str | None = None) -> str:
    """The first free managed path at or beside `desired`.

    `keeping` is the track's own current path, which does not count as an
    occupied location: renaming a track's title back to what it already is must
    not push it onto a suffixed path.
    """
    if desired == keeping:
        return desired
    if not resolve_managed_path(music_root, desired).exists():
        return desired

    head, _, name = desired.rpartition("/")
    stem = name.removesuffix(AUDIO_SUFFIX)
    suffix = AUDIO_SUFFIX if name.endswith(AUDIO_SUFFIX) else Path(name).suffix
    base = stem if name.endswith(AUDIO_SUFFIX) else name.removesuffix(suffix)
    for attempt in range(2, 1000):
        candidate = f"{head}/{base} ({attempt}){suffix}"
        if candidate == keeping or not resolve_managed_path(music_root, candidate).exists():
            return candidate
    raise StorageUnwritableError("That location already holds too many similarly named files.")


def stage_copy(music_root: Path, *, mutation_id: str, source_relpath: str, name: str) -> Path:
    """Copy one live managed file into this mutation's staging directory.

    A copy rather than a move: the live file has to stay playable for as long
    as the edit could still fail.
    """
    source = resolve_managed_path(music_root, source_relpath)
    target = staging_directory(music_root, mutation_id) / name
    try:
        shutil.copy2(source, target)
    except OSError as exc:
        raise StorageUnwritableError("The track's file could not be prepared for editing.") from exc
    return target


def stage_bytes(music_root: Path, *, mutation_id: str, name: str, payload: bytes) -> Path:
    """Write one prepared file into this mutation's staging directory."""
    target = staging_directory(music_root, mutation_id) / name
    try:
        with target.open("wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        raise StorageUnwritableError("The cover image could not be prepared.") from exc
    return target


def file_digest(path: Path) -> tuple[str, int]:
    """The SHA-256 and byte size of one prepared file.

    Both are stored on the track row, so they are measured on the exact bytes
    that are about to be placed rather than on the copy they came from.
    """
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        size = path.stat().st_size
    except OSError as exc:
        raise StorageUnwritableError("A prepared file could not be read back.") from exc
    return digest.hexdigest(), size


def fsync_file(path: Path) -> None:
    """Force one staged file's contents to durable storage."""
    try:
        handle = os.open(path, os.O_RDONLY)
        try:
            os.fsync(handle)
        finally:
            os.close(handle)
    except OSError as exc:
        raise StorageUnwritableError("A prepared file could not be flushed to disk.") from exc


def preserve_recovery(
    music_root: Path, *, mutation_id: str, relpaths: Sequence[str]
) -> dict[str, str]:
    """Hard-link every live path into recovery and return active → recovery.

    Hard links rather than copies: the recovery snapshot costs no extra bytes
    and, more importantly, is instantaneous, so the window in which a crash
    finds a track with neither an old nor a new file does not exist.

    A path that is already absent is skipped. That is the documented
    missing-file case, not a failure: metadata cleanup still has to be possible
    for a track whose file somebody deleted over SMB.
    """
    directory = recovery_directory(music_root, mutation_id)
    links: dict[str, str] = {}
    for relative in relpaths:
        source = resolve_managed_path(music_root, relative)
        if not source.is_file():
            continue
        target = directory / _flatten(relative)
        try:
            target.unlink(missing_ok=True)
            os.link(source, target)
        except OSError as exc:
            raise StorageUnwritableError(
                "The track's current file could not be safeguarded before the change."
            ) from exc
        links[relative] = str(target)
    _fsync_directory(directory)
    return links


def place(music_root: Path, staged: StagedFile) -> None:
    """Atomically move one staged file to its intended managed path."""
    target = resolve_managed_path(music_root, staged.intended_relpath)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        staged.staged_path.replace(target)
    except OSError as exc:
        raise StorageUnwritableError("The music folder refused the edited file.") from exc
    _fsync_directory(target.parent)


def restore_recovery(music_root: Path, links: Mapping[str, str]) -> None:
    """Put the previous files back at their original managed paths.

    Called when the database commit failed after placement. It never raises:
    the caller is already handling a failure, and a rollback that raises would
    replace a recoverable state with an unreported one. What it cannot restore
    is left for startup recovery, which reads the same journal row.
    """
    for relative, recovery_path in links.items():
        try:
            target = resolve_managed_path(music_root, relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.unlink(missing_ok=True)
            os.link(recovery_path, target)
            _fsync_directory(target.parent)
        except OSError:
            continue


def discard_paths(music_root: Path, relpaths: Sequence[str]) -> None:
    """Remove managed paths that the committed record no longer references."""
    for relative in relpaths:
        try:
            target = resolve_managed_path(music_root, relative)
            target.unlink(missing_ok=True)
            _fsync_directory(target.parent)
        except OSError:
            continue


def discard_mutation_workspace(music_root: Path, mutation_id: str) -> None:
    """Remove one mutation's staging and recovery directories.

    Called after the journal row reaches `finalized`, and again by startup
    recovery. Leftover directories are disk to reclaim, never a failure.
    """
    safe = _safe_id(mutation_id)
    for parent in (STAGING_DIRECTORY, RECOVERY_DIRECTORY):
        shutil.rmtree(music_root / INTERNAL_DIRECTORY / parent / safe, ignore_errors=True)


def prune_empty_parents(music_root: Path, relpaths: Sequence[str]) -> None:
    """Remove artist/album directories a move left behind.

    Only empty directories are removed, and only beneath the managed root, so a
    directory a person put their own files in is never touched.
    """
    root = music_root.resolve(strict=False)
    for relative in relpaths:
        try:
            directory = resolve_managed_path(music_root, relative).parent
        except Exception:
            continue
        while directory != root and root in directory.parents:
            try:
                directory.rmdir()
            except OSError:
                break
            directory = directory.parent


def _make_directory(path: Path) -> Path:
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise StorageUnwritableError("The music folder is not writable.") from exc
    return path


def _fsync_directory(path: Path) -> None:
    """Flush a directory entry so a rename survives a power loss."""
    try:
        handle = os.open(path, os.O_RDONLY)
        try:
            os.fsync(handle)
        finally:
            os.close(handle)
    except OSError:
        # Some filesystems refuse to fsync a directory. The rename is already
        # atomic there; durability of the entry is the platform's business.
        pass


def _flatten(relative_path: str) -> str:
    """One recovery-directory filename standing for a full managed path."""
    return relative_path.replace("/", "__")


def _safe_id(value: str) -> str:
    """Reduce an application-generated ID to one safe path component."""
    cleaned = "".join(character for character in value if character.isalnum() or character in "-_")
    if not cleaned:
        raise StorageUnwritableError("An internal identifier is not usable as a path.")
    return cleaned
