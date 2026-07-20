"""The Celery task seam.

This module is deliberately thin. It accepts a job ID, resolves the process
composition, and hands the work to the application use case. Acquisition logic
lives above it, so the same behaviour can be exercised without a broker.
"""

from __future__ import annotations

import logging
from typing import Any

from celery import Celery

from chillify.domain.jobs import JobId
from chillify.infrastructure.queue.celery_app import ACQUIRE_TASK_NAME

logger = logging.getLogger(__name__)


def register_tasks(app: Celery, resolve: Any) -> None:
    """Bind the acquisition task to `app`.

    `resolve` returns the process's `DownloadService`. It is injected rather
    than imported so this module never reaches for a global composition, and a
    test can register the same task against a disposable one.
    """

    @app.task(name=ACQUIRE_TASK_NAME, bind=True, acks_late=True)  # type: ignore[untyped-decorator]
    def acquire_download(self: Any, job_id: str) -> None:  # noqa: ARG001
        """Run one acquisition. The task carries no state beyond the ID."""
        logger.info("acquisition task received", extra={"job_id": job_id})
        resolve().run_job(JobId(job_id))
