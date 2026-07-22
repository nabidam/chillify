"""Acquisition use cases: request, run, and observe one download.

The API side accepts a request and commits a durable job. The worker side runs
that job. They share nothing but the database, which is what makes closing the
browser irrelevant to whether a download finishes.

Every phase change is one transaction that updates the job and appends its
event together. Nothing the browser is told exists outside a committed row.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from chillify.domain.errors import (
    AcquisitionCancelledError,
    ChillifyError,
    ProviderDisabledError,
    QueueUnavailableError,
    RecordNotFoundError,
    UnsupportedEntityError,
)
from chillify.domain.jobs import (
    ACQUISITION_PHASES,
    PROVIDER_FOR_SOURCE,
    DownloadJob,
    JobEvent,
    JobId,
    JobPhase,
    JobState,
    SourceType,
    build_dedupe_key,
)
from chillify.domain.models import Page, Track, TrackId
from chillify.domain.protocols import TrackCandidate
from chillify.infrastructure.db.repositories import (
    JOB_LEASE_SECONDS,
    JOB_PAGE_LIMIT_DEFAULT,
    DownloadJobRepository,
    IdempotencyRepository,
    TrackRepository,
)
from chillify.infrastructure.media.storage import (
    job_workspace,
    organized_relpath,
    publish_audio,
    remove_workspace,
)
from chillify.infrastructure.media.tags import write_audio_tags
from chillify.infrastructure.media.workspaces import existing_workspaces
from chillify.infrastructure.providers.registry import ProviderRegistry
from chillify.infrastructure.queue.cancellation import ActiveAcquisitions, active_acquisitions

logger = logging.getLogger(__name__)

# Dispatch sends only a job ID. Everything else is reloaded from SQLite, so a
# lost or tampered message cannot change what work happens.
Dispatcher = Callable[[JobId], str]

# Reports whether the queue transport is reachable right now.
QueueProbe = Callable[[], bool]


@dataclass(frozen=True, slots=True)
class JobDetail:
    """One job together with its replayable history."""

    job: DownloadJob
    events: tuple[JobEvent, ...]


@dataclass(frozen=True, slots=True)
class DownloadService:
    """Requesting, running, and reading acquisitions."""

    session_factory: sessionmaker[Session]
    registry: ProviderRegistry
    music_root: Path
    dispatch: Dispatcher
    queue_reachable: QueueProbe
    worker_identity: str = "api"
    proxy_url: str | None = None
    # The in-process channel a same-process cancel uses to stop a live run
    # before its next database poll. Defaults to the worker's shared registry.
    active: ActiveAcquisitions = active_acquisitions

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

    # -- requesting -------------------------------------------------------

    def request_download(self, candidate: TrackCandidate, source_type: SourceType) -> DownloadJob:
        """Validate, durably queue, then dispatch one acquisition.

        The order matters and is the whole point: the job is committed before
        Celery is told about it. A broker that is down therefore costs the
        person a delay, never the request.
        """
        provider = PROVIDER_FOR_SOURCE.get(source_type)
        if provider is None:
            raise UnsupportedEntityError(
                "Chillify does not know how to download that kind of link.",
                field="source_type",
            )
        if not self.registry.has_acquisition(provider):
            raise ProviderDisabledError(
                "Downloading is switched off for that source.",
                context={"provider": str(provider)},
            )
        if not self.queue_reachable():
            raise QueueUnavailableError(
                "Downloads are paused while the queue is unreachable. Your library still plays."
            )

        source_ref = candidate.source_url or candidate.acquisition_locator
        dedupe_key = build_dedupe_key(provider, source_type, source_ref)
        now = datetime.now(UTC)

        with self._transaction() as session:
            # The insert is this transaction's first statement, so the write
            # lock is taken at its start — the guarantee `BEGIN IMMEDIATE`
            # exists to give a read-then-write path. There is deliberately no
            # duplicate pre-check: the partial unique index is the race-safe
            # answer, and a pre-check would only widen the window it closes.
            job = DownloadJobRepository(session).create(
                provider=provider,
                source_type=source_type,
                source_ref=source_ref,
                dedupe_key=dedupe_key,
                request=_candidate_payload(candidate),
                candidate=_candidate_payload(candidate),
                now=now,
            )

        logger.info(
            "download queued",
            extra={"job_id": str(job.id), "provider": str(provider)},
        )
        self._dispatch(job)
        return job

    def _dispatch(self, job: DownloadJob) -> None:
        """Hand the committed job to Celery, or leave it for reconciliation."""
        try:
            task_id = self.dispatch(job.id)
        except Exception as exc:
            # The durable job survives; reconciliation publishes it later. This
            # is caught broadly on purpose: it is the process boundary between
            # committed local state and a remote broker.
            logger.warning(
                "queue dispatch failed; job remains queued",
                extra={"job_id": str(job.id), "error": str(exc)},
            )
            raise QueueUnavailableError(
                "The download is queued but the worker could not be notified yet."
            ) from exc

        with self._transaction() as session:
            DownloadJobRepository(session).record_dispatch(
                job.id, celery_task_id=task_id, now=datetime.now(UTC)
            )

    # -- cancel and retry -------------------------------------------------

    def cancel_download(self, job_id: JobId, *, expected_version: int) -> DownloadJob:
        """Cancel a queued job, or ask a running one to stop and clean up.

        A queued cancel commits `cancelled` and discards any scratch directory
        here, because there is no run to do it. A running cancel records the
        request and trips the in-process signal; the worker commits the terminal
        state and removes the workspace when its acquisition unwinds.
        """
        now = datetime.now(UTC)
        with self._transaction() as session:
            job = DownloadJobRepository(session).request_cancel(
                job_id, expected_version=expected_version, now=now
            )

        if job.state is JobState.CANCELLED:
            scratch = existing_workspaces(self.music_root).get(str(job_id))
            if scratch is not None:
                remove_workspace(scratch)
        else:
            # Reach a run happening in this process now; a run in another
            # process sees the durable flag it just committed on its next check.
            self.active.request(job_id)
        logger.info(
            "download cancel requested",
            extra={"job_id": str(job_id), "state": str(job.state)},
        )
        return job

    def retry_download(self, job_id: JobId) -> DownloadJob:
        """Queue a fresh attempt linked to a finished failed or cancelled job."""
        if not self.queue_reachable():
            raise QueueUnavailableError(
                "Downloads are paused while the queue is unreachable. Your library still plays."
            )
        now = datetime.now(UTC)
        with self._transaction() as session:
            job = DownloadJobRepository(session).retry(job_id, now=now)

        logger.info(
            "download retried",
            extra={"job_id": str(job.id), "parent_job_id": str(job_id)},
        )
        self._dispatch(job)
        return job

    def find_active(self, dedupe_key: str) -> DownloadJob | None:
        """The job already holding this dedupe key, if one is queued or running."""
        with self._transaction() as session:
            return DownloadJobRepository(session).find_active_by_dedupe_key(dedupe_key)

    # -- reading ----------------------------------------------------------

    def list_jobs(
        self,
        *,
        states: tuple[JobState, ...] | None = None,
        cursor: str | None = None,
        limit: int = JOB_PAGE_LIMIT_DEFAULT,
    ) -> Page[DownloadJob]:
        with self._transaction() as session:
            return DownloadJobRepository(session).list_jobs(
                states=states, cursor=cursor, limit=limit
            )

    def get_job(self, job_id: JobId) -> JobDetail:
        with self._transaction() as session:
            jobs = DownloadJobRepository(session)
            job = jobs.get(job_id)
            if job is None:
                raise RecordNotFoundError("That download is not in this queue.")
            return JobDetail(job=job, events=jobs.list_events(job_id))

    def events_after(self, event_id: int) -> tuple[JobEvent, ...]:
        with self._transaction() as session:
            return DownloadJobRepository(session).events_after(event_id)

    def latest_event_id(self) -> int:
        with self._transaction() as session:
            return DownloadJobRepository(session).latest_event_id()

    # -- running ----------------------------------------------------------

    def run_job(self, job_id: JobId) -> None:
        """Perform one acquisition end to end.

        Called by the worker with nothing but an ID. Every input is reloaded
        from SQLite, so a redelivered message runs the same work or, if the job
        is no longer claimable, none at all.
        """
        job = self._claim(job_id)
        if job is None:
            logger.info("job not claimable; ignoring delivery", extra={"job_id": str(job_id)})
            return

        candidate = self._load_candidate(job_id)
        workspace = job_workspace(self.music_root, str(job_id))
        try:
            track = self._acquire_and_publish(job, candidate, workspace)
        except AcquisitionCancelledError as exc:
            self._finish(job_id, JobState.CANCELLED, error=exc)
            logger.info("download cancelled", extra={"job_id": str(job_id)})
        except ChillifyError as exc:
            self._finish(job_id, JobState.FAILED, error=exc)
            logger.warning(
                "download failed",
                extra={"job_id": str(job_id), "error_code": exc.code},
            )
        else:
            logger.info(
                "download completed",
                extra={"job_id": str(job_id), "track_id": str(track.id)},
            )
        finally:
            remove_workspace(workspace)

    def _acquire_and_publish(
        self, job: DownloadJob, candidate: TrackCandidate, workspace: Path
    ) -> Track:
        adapter = self.registry.require_acquisition(job.provider)

        def report(percent: float | None) -> None:
            self._record(job.id, JobPhase.DOWNLOADING, percent)

        self._record(job.id, JobPhase.DOWNLOADING, None)
        # The adapter consults both channels: the in-process signal stops a
        # same-process cancel immediately, and the durable flag catches a cancel
        # committed by another process between the adapter's checks.
        with self.active.begin(job.id) as signal:
            artifact = adapter.acquire(
                candidate,
                str(workspace),
                self.proxy_url,
                report,
                lambda: signal.requested or self._is_cancel_requested(job.id),
            )

        self._record(job.id, JobPhase.CONVERTING, None)
        self._record(job.id, JobPhase.ENRICHING, None)

        self._record(job.id, JobPhase.TAGGING, None)
        acquired = Path(artifact.location)
        write_audio_tags(
            acquired,
            title=candidate.title,
            artist=candidate.artist,
            album=candidate.album,
            release_year=candidate.release_year,
            track_number=candidate.track_number,
        )

        self._record(job.id, JobPhase.ORGANIZING, None)
        published = publish_audio(
            self.music_root,
            acquired,
            organized_relpath(
                artist=candidate.artist,
                album=candidate.album,
                title=candidate.title,
                track_number=candidate.track_number,
            ),
        )

        # The track, its source identity, and the job's completion are one
        # transaction: a person can never see a completed download whose track
        # is not in the library.
        now = datetime.now(UTC)
        with self._transaction() as session:
            track = TrackRepository(session).create(
                title=candidate.title,
                artist=candidate.artist,
                album=candidate.album,
                release_year=candidate.release_year,
                disc_number=candidate.disc_number,
                track_number=candidate.track_number,
                duration_ms=artifact.duration_ms or candidate.duration_ms,
                isrc=candidate.isrc,
                file_relpath=published.relative_path,
                artwork_relpath=None,
                file_size_bytes=published.size_bytes,
                content_sha256=published.content_sha256,
                source_provider=candidate.provider,
                source_id=candidate.source_id,
                source_url=candidate.source_url,
                raw_fingerprint=candidate.raw_fingerprint,
                now=now,
            )
            DownloadJobRepository(session).finish(
                job.id, state=JobState.COMPLETED, now=now, result_track_id=TrackId(track.id)
            )
        return track

    def _claim(self, job_id: JobId) -> DownloadJob | None:
        with self._transaction() as session:
            return DownloadJobRepository(session).claim(
                job_id,
                owner=self.worker_identity,
                now=datetime.now(UTC),
                lease_seconds=JOB_LEASE_SECONDS,
            )

    def _load_candidate(self, job_id: JobId) -> TrackCandidate:
        with self._transaction() as session:
            payload = DownloadJobRepository(session).read_candidate(job_id)
        if payload is None:
            raise UnsupportedEntityError("That download request carries no track to acquire.")
        return _candidate_from_payload(payload)

    def _record(self, job_id: JobId, phase: JobPhase, progress: float | None) -> JobEvent:
        with self._transaction() as session:
            return DownloadJobRepository(session).record_phase(
                job_id, phase=phase, progress_percent=progress, now=datetime.now(UTC)
            )

    def _finish(self, job_id: JobId, state: JobState, *, error: ChillifyError) -> None:
        with self._transaction() as session:
            DownloadJobRepository(session).finish(
                job_id,
                state=state,
                now=datetime.now(UTC),
                error_code=error.code,
                error_message=error.message,
            )

    def _is_cancel_requested(self, job_id: JobId) -> bool:
        with self._transaction() as session:
            job = DownloadJobRepository(session).get(job_id)
        return job is not None and job.is_cancel_requested


@dataclass(frozen=True, slots=True)
class IdempotencyGuard:
    """Replay for mutations that carry an `Idempotency-Key`.

    The stored response is returned verbatim for a repeat of the same request,
    and a key reused with a different body is refused. That is what stops a
    retried tap on a flaky connection from queueing a second download while
    still letting the browser retry safely.
    """

    session_factory: sessionmaker[Session]

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

    def replay(self, *, scope: str, key: str, request_body: bytes) -> str | None:
        with self._transaction() as session:
            return IdempotencyRepository(session).find(
                scope=scope,
                key=key,
                request_sha256=request_digest(request_body),
                now=datetime.now(UTC),
            )

    def remember(
        self, *, scope: str, key: str, request_body: bytes, status_code: int, response_json: str
    ) -> None:
        now = datetime.now(UTC)
        with self._transaction() as session:
            repository = IdempotencyRepository(session)
            repository.remember(
                scope=scope,
                key=key,
                request_sha256=request_digest(request_body),
                status_code=status_code,
                response_json=response_json,
                now=now,
            )
            # Opportunistic: expiry is a retention rule, not a scheduled job.
            repository.prune(now=now)


def request_digest(request_body: bytes) -> str:
    """The hash that binds one idempotency key to one request body."""
    return hashlib.sha256(request_body).hexdigest()


def remaining_phases(current: JobPhase) -> tuple[JobPhase, ...]:
    """The work phases still ahead of `current`, for a progress summary."""
    if current not in ACQUISITION_PHASES:
        return ()
    return ACQUISITION_PHASES[ACQUISITION_PHASES.index(current) + 1 :]


def _candidate_payload(candidate: TrackCandidate) -> dict[str, object]:
    """The immutable stored form of a submitted candidate."""
    return {
        "provider": candidate.provider,
        "source_id": candidate.source_id,
        "source_url": candidate.source_url,
        "title": candidate.title,
        "artist": candidate.artist,
        "album": candidate.album,
        "release_year": candidate.release_year,
        "disc_number": candidate.disc_number,
        "track_number": candidate.track_number,
        "duration_ms": candidate.duration_ms,
        "isrc": candidate.isrc,
        "artwork_url": candidate.artwork_url,
        "acquisition_locator": candidate.acquisition_locator,
        "raw_fingerprint": candidate.raw_fingerprint,
    }


def _candidate_from_payload(payload: dict[str, object]) -> TrackCandidate:
    return TrackCandidate(
        provider=_string(payload, "provider", ""),
        source_id=_optional_string(payload, "source_id"),
        source_url=_string(payload, "source_url", ""),
        title=_string(payload, "title", ""),
        artist=_string(payload, "artist", ""),
        album=_optional_string(payload, "album"),
        release_year=_optional_int(payload, "release_year"),
        disc_number=_optional_int(payload, "disc_number"),
        track_number=_optional_int(payload, "track_number"),
        duration_ms=_optional_int(payload, "duration_ms"),
        isrc=_optional_string(payload, "isrc"),
        artwork_url=_optional_string(payload, "artwork_url"),
        acquisition_locator=_string(payload, "acquisition_locator", ""),
        raw_fingerprint=_optional_string(payload, "raw_fingerprint"),
    )


def _string(payload: dict[str, object], key: str, default: str) -> str:
    value = payload.get(key)
    return value if isinstance(value, str) else default


def _optional_string(payload: dict[str, object], key: str) -> str | None:
    value = payload.get(key)
    return value if isinstance(value, str) else None


def _optional_int(payload: dict[str, object], key: str) -> int | None:
    value = payload.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else None
