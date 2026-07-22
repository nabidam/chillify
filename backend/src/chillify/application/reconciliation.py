"""Bringing the durable queue back to a truthful state after an interruption.

A worker can die between committed transitions, a broker can drop a message, and
a browser can be told about a run that never resumed. Reconciliation is the one
use case that repairs this: it reads the authoritative rows, restarts jobs whose
worker vanished, republishes work the broker never carried, and discards the
scratch directories those failures left behind.

It commits nothing the state machine forbids. Every transition it performs is
one the DDL already allows — running back to queued, queued forward to
cancelled — so a restart never has to reconstruct a state that was never a legal
place to be.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from chillify.domain.jobs import JobId
from chillify.infrastructure.db.repositories import DownloadJobRepository
from chillify.infrastructure.media.storage import remove_workspace
from chillify.infrastructure.media.workspaces import existing_workspaces, remove_orphan_workspaces

logger = logging.getLogger(__name__)

# Publishes a recovered job's ID to the queue. Same shape as acquisition
# dispatch; a failure here leaves the job durably queued for the next pass.
Dispatcher = Callable[[JobId], str]

# Reports whether the broker can accept work right now.
QueueProbe = Callable[[], bool]


@dataclass(frozen=True, slots=True)
class ReconciliationOutcome:
    """What one reconciliation pass changed, for the log and the tests."""

    restarted: tuple[JobId, ...] = ()
    republished: tuple[JobId, ...] = ()
    removed_workspaces: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ReconciliationService:
    """Recovery of interrupted jobs on startup and on queue reconnection."""

    session_factory: sessionmaker[Session]
    music_root: Path
    dispatch: Dispatcher
    queue_reachable: QueueProbe = field(default=lambda: True)
    _now: Callable[[], datetime] = field(default=lambda: datetime.now(UTC))

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

    def reconcile(self) -> ReconciliationOutcome:
        """Repair the queue once, then hand recovered work back to the broker.

        The database repair is one transaction; workspace removal and dispatch
        follow it, because neither is durable and a crash between them costs
        only a repeated, idempotent recovery — not a wrong committed state.
        """
        now = self._now()
        with self._transaction() as session:
            jobs = DownloadJobRepository(session)
            restarted = tuple(job.id for job in jobs.list_stale_running(now=now))
            for job_id in restarted:
                jobs.restart(job_id, now=now)
            # Read the republish set inside the same transaction, after the
            # restarts, so a just-restarted job is included exactly once.
            queued = tuple(job.id for job in jobs.list_queued())
            active_ids = jobs.active_job_ids()

        # A restarted job keeps its slot but not its half-finished scratch: the
        # next run starts clean. Everything not backing an active job is
        # residue and goes with it.
        workspaces = existing_workspaces(self.music_root)
        for job_id in restarted:
            scratch = workspaces.get(str(job_id))
            if scratch is not None:
                remove_workspace(scratch)
        removed = tuple(remove_orphan_workspaces(self.music_root, active_ids))

        # The DB and workspaces are repaired regardless, but there is no point
        # handing work to a broker that cannot take it — the next reconnection
        # pass republishes the still-queued jobs.
        republished: list[JobId] = []
        if self.queue_reachable():
            for job_id in queued:
                if self._republish(job_id):
                    republished.append(job_id)

        if restarted or republished or removed:
            logger.info(
                "reconciliation pass complete",
                extra={
                    "restarted": len(restarted),
                    "republished": len(republished),
                    "removed_workspaces": len(removed),
                },
            )
        return ReconciliationOutcome(
            restarted=restarted,
            republished=tuple(republished),
            removed_workspaces=removed,
        )

    def _republish(self, job_id: JobId) -> bool:
        """Hand one queued job back to the broker. A failure leaves it queued."""
        try:
            self.dispatch(job_id)
        except Exception as exc:
            # The broker is the process boundary; a durable job survives its
            # loss and the next reconnection publishes it again.
            logger.warning(
                "reconciliation could not republish; job remains queued",
                extra={"job_id": str(job_id), "error": str(exc)},
            )
            return False
        return True
