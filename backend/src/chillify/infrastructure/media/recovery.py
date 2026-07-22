"""Finishing or reversing a media mutation a crash left half-applied.

An edit or a deletion moves files and rewrites rows in a fixed, journaled order.
If the process dies between two of those steps, the `media_mutations` row that
was open says exactly what was in flight and which recovery links can undo it.
This module reads every such row on startup and drives it to one authoritative
state — the same rollback or finalization the request would have performed had
it lived.

The rule ARCHITECTURE section 8 fixes is conservative: a mutation that had not
yet committed its database transaction is rolled back to the old record, and one
that had committed is finished by dropping the superseded files. No old file is
ever removed while the new record cannot already play, and no new file is left
beside an old one.

Recovery is idempotent: it only ever restores from links that were never
unlinked and discards paths that may already be gone, so running it twice — a
crash during recovery itself — costs a repeated pass and changes nothing.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from chillify.domain.models import MediaMutationJournal, TrackId
from chillify.infrastructure.db.repositories import MediaMutationRepository, TrackRepository
from chillify.infrastructure.media import mutations

logger = logging.getLogger(__name__)

# The one state that means the database transaction committed. Everything before
# it is rolled back to the old record; it and nothing else is finalized.
_COMMITTED = "db_committed"


@dataclass(frozen=True, slots=True)
class MediaRecoveryOutcome:
    """What one recovery pass resolved, for the log and the tests."""

    rolled_back: tuple[str, ...] = ()
    finalized: tuple[str, ...] = ()
    failed: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class MediaRecoveryService:
    """Startup recovery of interrupted edit and deletion mutations."""

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

    def recover(self) -> MediaRecoveryOutcome:
        """Resolve every unfinished journal row once.

        Each row is handled independently: one that cannot be resolved is marked
        `recovery_required` and left for the next pass rather than aborting the
        others, because an unrelated stuck mutation must not keep a recoverable
        one open.
        """
        with self._transaction() as session:
            journal = tuple(MediaMutationRepository(session).list_recoverable())

        rolled_back: list[str] = []
        finalized: list[str] = []
        failed: list[str] = []
        for record in journal:
            try:
                if record.state == _COMMITTED:
                    self._finalize(record)
                    finalized.append(record.id)
                else:
                    self._roll_back(record)
                    rolled_back.append(record.id)
            except Exception:
                logger.exception(
                    "media mutation could not be recovered; left for the next pass",
                    extra={"mutation_id": record.id, "operation": record.operation},
                )
                self._mark_recovery_required(record.id)
                failed.append(record.id)

        if rolled_back or finalized or failed:
            logger.info(
                "media recovery pass complete",
                extra={
                    "rolled_back": len(rolled_back),
                    "finalized": len(finalized),
                    "failed": len(failed),
                },
            )
        return MediaRecoveryOutcome(
            rolled_back=tuple(rolled_back),
            finalized=tuple(finalized),
            failed=tuple(failed),
        )

    # -- rollback: the transaction never committed -----------------------------

    def _roll_back(self, record: MediaMutationJournal) -> None:
        """Restore the old files and record, then close the journal row."""
        now = datetime.now(UTC)
        if record.operation == "edit":
            # A rename that landed before the crash must not leave a second copy
            # behind; only paths the old record did not own are discarded.
            superseded = [path for path in _new_paths(record) if path not in record.recovery]
            mutations.discard_paths(self.music_root, superseded)
        mutations.restore_recovery(self.music_root, record.recovery)

        with self._transaction() as session:
            if record.track_id is not None:
                TrackRepository(session).end_mutation(TrackId(record.track_id))
            journal = MediaMutationRepository(session)
            journal.advance(
                record.id,
                state="rolled_back",
                now=now,
                error_detail="recovered after interruption before commit",
            )
        mutations.discard_mutation_workspace(self.music_root, record.id)

    # -- finalize: the transaction committed -----------------------------------

    def _finalize(self, record: MediaMutationJournal) -> None:
        """Drop the superseded files and close the journal row."""
        now = datetime.now(UTC)
        if record.operation == "edit":
            keep = set(_new_paths(record))
            obsolete = [path for path in record.recovery if path not in keep]
        else:
            # A deletion's committed state means the row and its references are
            # already gone; the old files are all superseded.
            obsolete = list(record.recovery)
        mutations.discard_paths(self.music_root, obsolete)

        with self._transaction() as session:
            if record.operation == "edit" and record.track_id is not None:
                TrackRepository(session).end_mutation(TrackId(record.track_id))
            journal = MediaMutationRepository(session)
            journal.advance(record.id, state="finalized", now=now)
            journal.close(record.id)
        mutations.discard_mutation_workspace(self.music_root, record.id)
        mutations.prune_empty_parents(self.music_root, obsolete)

    def _mark_recovery_required(self, mutation_id: str) -> None:
        """Flag a row that could not be resolved so the next pass retries it."""
        try:
            with self._transaction() as session:
                MediaMutationRepository(session).advance(
                    mutation_id,
                    state="recovery_required",
                    now=datetime.now(UTC),
                    error_detail="recovery pass could not resolve this mutation",
                )
        except Exception:
            logger.exception(
                "media mutation could not even be marked for recovery",
                extra={"mutation_id": mutation_id},
            )


def _new_paths(record: MediaMutationJournal) -> list[str]:
    """The managed paths an edit's committed record references."""
    if record.new_record is None:
        return []
    paths: list[str] = []
    audio = record.new_record.get("file_relpath")
    if isinstance(audio, str):
        paths.append(audio)
    artwork = record.new_record.get("artwork_relpath")
    if isinstance(artwork, str):
        paths.append(artwork)
    return paths
