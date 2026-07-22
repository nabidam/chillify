"""Reaching the acquisition that is running right now to stop it.

Cancellation has two channels and they are not redundant. The durable one is
`download_jobs.cancel_requested_at`: the worker consults it between phases and
inside downloader hooks, so a cancel always lands even when the request and the
worker are different processes. This module is the in-process fast path that
sits beside it — when a cancel arrives in the same process that is acquiring, it
trips a signal the current run sees immediately, and, for a subprocess adapter,
terminates that adapter's process group instead of waiting for it to poll.

A blocking `spotdl` subprocess will not return to check a flag on its own, so
ARCHITECTURE requires the worker to terminate the process group. That teardown
lives here; the fixture and in-process adapters need only the cooperative flag.
"""

from __future__ import annotations

import logging
import os
import signal
import threading
from types import TracebackType

from chillify.domain.jobs import JobId

logger = logging.getLogger(__name__)


class CancellationSignal:
    """The stop switch for one acquisition currently in flight.

    An adapter's `cancelled` callback reads `requested`; a subprocess adapter
    calls `bind_process_group` once it has spawned its child, so a later
    `request` can signal the whole group rather than only setting the flag.
    """

    __slots__ = ("_event", "_lock", "_process_group")

    def __init__(self) -> None:
        self._event = threading.Event()
        self._lock = threading.Lock()
        self._process_group: int | None = None

    @property
    def requested(self) -> bool:
        return self._event.is_set()

    def bind_process_group(self, process_group_id: int) -> None:
        """Record the subprocess group a later cancel must terminate."""
        with self._lock:
            self._process_group = process_group_id
            already_cancelled = self._event.is_set()
        # A cancel that arrived before the child was bound still has to reach it.
        if already_cancelled:
            self._terminate_group()

    def request(self) -> None:
        """Ask the running acquisition to stop, and tear down its group if any."""
        self._event.set()
        self._terminate_group()

    def _terminate_group(self) -> None:
        with self._lock:
            process_group_id = self._process_group
        if process_group_id is None:
            return
        try:
            os.killpg(process_group_id, signal.SIGTERM)
        except (ProcessLookupError, PermissionError) as exc:
            # The group is already gone or not ours to signal; the cooperative
            # flag remains the authority and the worker still commits cancelled.
            logger.info("cancel could not signal process group", extra={"error": str(exc)})


class ActiveAcquisitions:
    """The at-most-one acquisition a worker process is performing right now.

    Serial execution means this holds zero or one live signal, but it is kept
    keyed by job ID and locked so a cancel arriving on the request thread and a
    run finishing on the worker thread cannot race over the same slot.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._signals: dict[JobId, CancellationSignal] = {}

    def begin(self, job_id: JobId) -> _AcquisitionScope:
        """Register `job_id` as the running acquisition for the scope's lifetime."""
        signal_for_job = CancellationSignal()
        with self._lock:
            self._signals[job_id] = signal_for_job
        return _AcquisitionScope(self, job_id, signal_for_job)

    def request(self, job_id: JobId) -> bool:
        """Signal a running acquisition to stop. True when one was in flight here.

        False is not a failure: the job may be running in another process, where
        the durable `cancel_requested_at` flag is the channel that reaches it.
        """
        with self._lock:
            signal_for_job = self._signals.get(job_id)
        if signal_for_job is None:
            return False
        signal_for_job.request()
        return True

    def _release(self, job_id: JobId) -> None:
        with self._lock:
            self._signals.pop(job_id, None)


class _AcquisitionScope:
    """Keeps one job registered as active for the duration of its acquisition."""

    __slots__ = ("_job_id", "_registry", "signal")

    def __init__(
        self, registry: ActiveAcquisitions, job_id: JobId, cancellation_signal: CancellationSignal
    ) -> None:
        self._registry = registry
        self._job_id = job_id
        self.signal = cancellation_signal

    def __enter__(self) -> CancellationSignal:
        return self.signal

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._registry._release(self._job_id)


# The one registry per worker process. The API process holds its own, unused,
# instance; cross-process cancels travel through the durable flag instead.
active_acquisitions = ActiveAcquisitions()
