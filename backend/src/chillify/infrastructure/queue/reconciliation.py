"""Where recovery is triggered: worker start, and every queue reconnection.

The recovery logic is the application `ReconciliationService`; this module is
only the seam that decides *when* it runs. ARCHITECTURE names two moments —
process startup and Redis reconnection — and both are Celery signals, so binding
them here keeps the trigger out of the use case and lets a test drive the use
case directly with no broker at all.

Reconciliation is idempotent by construction, so running it once too often costs
a repeated read; missing a reconnection would strand real work. The bias is
therefore always toward running it.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from celery.signals import worker_ready

from chillify.application.reconciliation import ReconciliationOutcome

logger = logging.getLogger(__name__)

# Returns a fresh reconciliation pass's outcome. Injected rather than imported so
# this seam never reaches for a global composition.
Reconcile = Callable[[], ReconciliationOutcome]


def install_reconciliation(reconcile: Reconcile) -> None:
    """Run reconciliation when this worker comes up and when Redis returns.

    `worker_ready` fires once the worker process has a live broker connection —
    exactly both moments: the first connect on startup and every reconnection
    after a Redis outage. It is a process-global Celery signal, so there is one
    handler per worker process, which is one worker.
    """

    @worker_ready.connect(weak=False)  # type: ignore[untyped-decorator]
    def _on_worker_ready(**_: Any) -> None:
        run_reconciliation(reconcile)


def run_reconciliation(reconcile: Reconcile) -> ReconciliationOutcome:
    """Perform one pass, never letting a recovery failure crash the caller.

    Startup must proceed even if recovery hits a transient error; the next
    trigger runs it again, and the durable rows it did not repair are still
    exactly where the following pass will find them.
    """
    try:
        return reconcile()
    except Exception:
        logger.exception("reconciliation pass failed; durable state is unchanged")
        return ReconciliationOutcome()
