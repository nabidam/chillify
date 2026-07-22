"""Permanent track deletion: remove the media first, then all its metadata.

This is the use case ARCHITECTURE section 8's two-stage deletion contract
describes. Deleting a shared track is destructive and irreversible for the
household, so the one thing it must never do is leave the library in a state
where the file is gone but the record still points at it, or the record is gone
but a second copy of the file survives. Every step is journaled and ordered so
that a process killed at any point recovers to one authoritative state.

The fixed order, each step recorded in `media_mutations`:

1. Under the library and track locks, hard-link recovery snapshots of the MP3
   and its cover; record `prepared`.
2. Unlink the active files and record `active_files_removed`. The media is now
   gone from its managed location, but the recovery links still hold it.
3. In one transaction anonymize every completed job that produced the track,
   delete the track row (cascading its sources and playlist entries), and record
   `db_committed`.
4. Drop the recovery links and close the journal.

A failure before step 3 restores the recovery links and returns the track to
`available`, so the old record stays authoritative. A missing active file is not
a failure: its snapshot is skipped, and the metadata cleanup still proceeds.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from chillify.domain.errors import RecordNotFoundError
from chillify.domain.models import Track, TrackId
from chillify.infrastructure.db.repositories import (
    DownloadJobRepository,
    MediaMutationRepository,
    TrackRepository,
)
from chillify.infrastructure.media import mutations

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class DeleteImpact:
    """What deleting one track would reach that the server owns.

    Only the playlist references are server-owned; S15 combines this count with
    the current-track and session-queue occurrences it reads from the browser's
    own store, which the server never sees.
    """

    playlist_count: int


@dataclass(frozen=True, slots=True)
class _DeletePlan:
    """Everything one deletion decided before it touched the filesystem."""

    track_id: TrackId
    live_paths: tuple[str, ...]
    mutation_id: str


@dataclass(frozen=True, slots=True)
class DeletionService:
    """Reading a deletion's impact and performing one recoverable deletion."""

    session_factory: sessionmaker[Session]
    music_root: Path

    @contextmanager
    def _transaction(self) -> Iterator[Session]:
        session = self.session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def delete_impact(self, track_id: TrackId) -> DeleteImpact:
        """The server-owned playlist references a deletion would remove."""
        with self._transaction() as session:
            tracks = TrackRepository(session)
            if tracks.get(track_id) is None:
                raise RecordNotFoundError("That track is not in this library.")
            return DeleteImpact(playlist_count=tracks.playlist_reference_count(track_id))

    def delete_track(self, track_id: TrackId, *, expected_revision: int) -> None:
        """Delete one track's media and metadata atomically, or change nothing."""
        now = datetime.now(UTC)
        # Both locks are held across the whole deletion: the file removal and the
        # database delete must see one filesystem, in the fixed library-then-track
        # order every mutation obeys.
        with mutations.media_locks(self.music_root, track_id=str(track_id)):
            plan = self._prepare(track_id, expected_revision=expected_revision)
            self._perform(plan, now=now)

    # -- step 1: validate against live state, open the journal, claim the file --

    def _prepare(self, track_id: TrackId, *, expected_revision: int) -> _DeletePlan:
        now = datetime.now(UTC)
        with self._transaction() as session:
            tracks = TrackRepository(session)
            current = tracks.get(track_id)
            if current is None:
                raise RecordNotFoundError("That track is not in this library.")
            live_paths = [current.file_relpath]
            if current.artwork_relpath is not None:
                live_paths.append(current.artwork_relpath)
            # The revision is matched before anything is journaled or unlinked, so
            # a deletion that has already lost a race leaves no recovery record.
            mutation_id = MediaMutationRepository(session).open_delete(
                track_id=track_id,
                old_record=_record_snapshot(current),
                now=now,
            )
            tracks.begin_deletion(track_id, expected_revision=expected_revision)
        return _DeletePlan(
            track_id=track_id,
            live_paths=tuple(live_paths),
            mutation_id=mutation_id,
        )

    # -- steps 2 to 4: snapshot, remove, commit, clean up ----------------------

    def _perform(self, plan: _DeletePlan, *, now: datetime) -> None:
        recovery = mutations.preserve_recovery(
            self.music_root, mutation_id=plan.mutation_id, relpaths=plan.live_paths
        )
        self._advance(plan.mutation_id, "prepared", now=now, recovery=recovery)

        # The active files come out before the row is deleted, so at no point does
        # a live record point at a file that is gone without a recovery link
        # holding it.
        mutations.discard_paths(self.music_root, plan.live_paths)
        self._advance(plan.mutation_id, "active_files_removed", now=now)

        try:
            with self._transaction() as session:
                DownloadJobRepository(session).anonymize_for_deleted_track(plan.track_id, now=now)
                TrackRepository(session).delete(plan.track_id)
                MediaMutationRepository(session).advance(
                    plan.mutation_id, state="db_committed", now=now
                )
        except Exception:
            self._roll_back(plan, recovery=recovery, now=now)
            raise

        self._finalize(plan, now=now)
        logger.info("track deleted", extra={"track_id": str(plan.track_id)})

    def _roll_back(self, plan: _DeletePlan, *, recovery: dict[str, str], now: datetime) -> None:
        """Put the removed files back and return the track to `available`.

        Reached only when the delete transaction failed after the files were
        unlinked. The recovery links still hold the exact bytes, so relinking
        them restores the track the person was about to delete, and the record
        was never changed.
        """
        mutations.restore_recovery(self.music_root, recovery)
        try:
            with self._transaction() as session:
                TrackRepository(session).end_mutation(plan.track_id)
                MediaMutationRepository(session).advance(
                    plan.mutation_id,
                    state="rolled_back",
                    now=now,
                    error_detail="database delete failed after files were removed",
                )
        except Exception:
            # The journal row is the recovery record; failing to update it is
            # logged once and left for startup recovery to finish.
            logger.exception(
                "deletion rollback could not update its journal",
                extra={"track_id": str(plan.track_id)},
            )
            return
        mutations.discard_mutation_workspace(self.music_root, plan.mutation_id)
        logger.warning(
            "track deletion rolled back; the track remains authoritative",
            extra={"track_id": str(plan.track_id)},
        )

    def _finalize(self, plan: _DeletePlan, *, now: datetime) -> None:
        """Drop the recovery links and close the journal; the track is gone."""
        mutations.discard_mutation_workspace(self.music_root, plan.mutation_id)
        with self._transaction() as session:
            journal = MediaMutationRepository(session)
            journal.advance(plan.mutation_id, state="finalized", now=now)
            journal.close(plan.mutation_id)
        mutations.prune_empty_parents(self.music_root, plan.live_paths)

    def _advance(
        self,
        mutation_id: str,
        state: str,
        *,
        now: datetime,
        recovery: dict[str, str] | None = None,
    ) -> None:
        with self._transaction() as session:
            MediaMutationRepository(session).advance(
                mutation_id, state=state, now=now, recovery=recovery
            )


def _record_snapshot(track: Track) -> dict[str, object]:
    """The deleted track as the journal stores it, for conservative recovery."""
    return {
        "title": track.title,
        "artist": track.artist,
        "album": track.album,
        "file_relpath": track.file_relpath,
        "artwork_relpath": track.artwork_relpath,
        "revision": track.revision,
    }
