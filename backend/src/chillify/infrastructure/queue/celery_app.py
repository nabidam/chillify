"""The Celery application and its dispatch seam.

Redis carries job IDs and nothing else — no credentials, no candidate payload,
no metadata. The worker reloads authoritative state from SQLite, so the broker
is a doorbell rather than a source of truth.

Concurrency and prefetch are both one. That is what makes acquisition serial,
which is what lets the worker share the mounted media root and the SQLite file
with the API without contending for either.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Final

from celery import Celery

from chillify.config import Settings
from chillify.domain.jobs import JobId

logger = logging.getLogger(__name__)

QUEUE_NAME: Final = "acquisition"
ACQUIRE_TASK_NAME: Final = "chillify.acquire_download"


def queue_name(settings: Settings) -> str:
    """The prefixed queue this deployment owns.

    The prefix is what keeps a gate run's messages out of the household queue,
    which is why it is part of the name rather than a convention.
    """
    return f"{settings.redis_prefix}{QUEUE_NAME}"


def create_celery_app(settings: Settings) -> Celery:
    app = Celery("chillify")
    app.conf.update(
        broker_url=settings.redis_url,
        result_backend=None,
        task_default_queue=queue_name(settings),
        # Serial execution: one task in flight, one reserved, never more.
        worker_concurrency=1,
        worker_prefetch_multiplier=1,
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        broker_connection_retry_on_startup=True,
        timezone="UTC",
        enable_utc=True,
        # Celery retry is reserved for broker delivery failures. Application
        # and provider retries are owned by the adapter and recorded on the
        # same job, so Celery must never create a parallel hidden attempt.
        task_default_retry_delay=5,
        task_max_retries=0,
        # Chillify configures logging; Celery must not install its own handlers.
        worker_hijack_root_logger=False,
        worker_redirect_stdouts=False,
    )
    return app


def make_dispatcher(app: Celery, settings: Settings) -> Callable[[JobId], str]:
    """Return the callable the application layer uses to publish one job ID."""

    def dispatch(job_id: JobId) -> str:
        result = app.send_task(ACQUIRE_TASK_NAME, args=[str(job_id)], queue=queue_name(settings))
        return str(result.id)

    return dispatch
