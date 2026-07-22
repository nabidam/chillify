"""Celery worker bootstrap.

The worker runs strictly serially: one process, concurrency one, prefetch one.
That is what lets downloads share the SQLite database and mounted media root
with the API without contending for either.

Redis carries job IDs only. The worker always reloads authoritative state from
the database, so a lost or tampered message cannot change what work happens.
"""

from __future__ import annotations

import argparse
import logging
import sys
from typing import Final

from chillify.application.downloads import DownloadService
from chillify.composition import Composition, Health, build_composition
from chillify.config import ConfigurationError, load_settings
from chillify.infrastructure.logging.setup import SERVICE_WORKER, configure_logging
from chillify.infrastructure.queue.celery_app import QUEUE_NAME, create_celery_app
from chillify.infrastructure.queue.reconciliation import install_reconciliation
from chillify.infrastructure.queue.tasks import register_tasks

logger = logging.getLogger(__name__)

# The lease owner recorded on every job this process runs, so a job's history
# says which process performed it.
WORKER_IDENTITY: Final = "worker"

_composition: Composition | None = None


def download_service() -> DownloadService:
    """The worker's acquisition use cases, bound to this process."""
    return composition().download_service(worker_identity=WORKER_IDENTITY)


def composition() -> Composition:
    """The worker's bound dependencies, built once per process."""
    global _composition
    if _composition is None:
        _composition = build_composition(load_settings())
    return _composition


def run_health_check() -> int:
    """Container health probe: valid config, usable paths, and reachable Redis.

    Unlike the API, the worker's readiness does require Redis — without it there
    is no acquisition to perform.
    """
    try:
        settings = load_settings()
        configure_logging(service=SERVICE_WORKER, level=settings.log_level)
        current = build_composition(settings).system_status()
    except ConfigurationError as exc:
        logger.error("worker configuration invalid", extra={"error_code": exc.code})
        return 1
    if not current.ready:
        logger.error("worker storage or database is not ready")
        return 1
    if current.redis.health is not Health.OK:
        logger.error("worker cannot reach the queue transport")
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="chillify-worker")
    parser.add_argument(
        "--health",
        action="store_true",
        help="Run the readiness probe and exit instead of starting the worker.",
    )
    arguments = parser.parse_args(argv)

    if arguments.health:
        return run_health_check()

    settings = load_settings()
    configure_logging(service=SERVICE_WORKER, level=settings.log_level)
    logger.info("starting worker", extra={"environment": str(settings.environment)})

    composition()
    celery_app = create_celery_app(settings)
    register_tasks(celery_app, download_service)
    # Recover interrupted jobs when this worker connects — on startup and on
    # every Redis reconnection — before it starts pulling new work.
    install_reconciliation(lambda: composition().reconciliation_service().reconcile())
    celery_app.worker_main(
        [
            "worker",
            "--loglevel",
            settings.log_level,
            "--concurrency",
            "1",
            "--prefetch-multiplier",
            "1",
            "--without-gossip",
            "--without-mingle",
            "--queues",
            f"{settings.redis_prefix}{QUEUE_NAME}",
        ]
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
