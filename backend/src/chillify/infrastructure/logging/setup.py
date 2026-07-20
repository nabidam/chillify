"""Rich stdout logging — the only logging system Chillify has.

Records carry service, request/job ID, and phase as structured `extra` fields so
`docker compose logs` shows who did what without a second sink. There is no file
handler and no remote dependency; failures in logging never fail application
work.
"""

from __future__ import annotations

import contextvars
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, Final

from rich.console import Console
from rich.logging import RichHandler

from chillify.infrastructure.logging.redaction import RedactingFilter, SecretRedactor

SERVICE_API: Final = "api"
SERVICE_WORKER: Final = "worker"

# Correlation identity for the current request or job, set at the boundary that
# owns it and inherited by every record emitted underneath.
_request_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "chillify_request_id", default=None
)
_job_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "chillify_job_id", default=None
)
_phase: contextvars.ContextVar[str | None] = contextvars.ContextVar("chillify_phase", default=None)

_redactor = SecretRedactor()


def redactor() -> SecretRedactor:
    """The process-wide redactor; register secrets on it as they are loaded."""
    return _redactor


class ContextFilter(logging.Filter):
    """Stamps every record with service and correlation context."""

    def __init__(self, service: str) -> None:
        super().__init__()
        self._service = service

    def filter(self, record: logging.LogRecord) -> bool:
        record.service = self._service
        record.request_id = _request_id.get()
        record.job_id = _job_id.get()
        record.phase = _phase.get()
        return True


class ContextRichHandler(RichHandler):
    """Rich output that keeps correlation context visible on every line."""

    def get_level_text(self, record: logging.LogRecord) -> Any:
        text = super().get_level_text(record)
        correlation = getattr(record, "job_id", None) or getattr(record, "request_id", None)
        if correlation:
            text.append(f" {correlation}", style="dim")
        phase = getattr(record, "phase", None)
        if phase:
            text.append(f" {phase}", style="dim")
        return text


def configure_logging(
    *,
    service: str,
    level: str = "INFO",
    console: Console | None = None,
) -> logging.Handler:
    """Install the single stdout handler for this process.

    Reconfiguring replaces the previous handler rather than adding a second one,
    so a failure is never logged twice by the same process.
    """
    handler = ContextRichHandler(
        console=console or Console(stderr=False, soft_wrap=True),
        rich_tracebacks=True,
        tracebacks_show_locals=False,
        show_path=False,
        markup=False,
        log_time_format="[%Y-%m-%d %H:%M:%S]",
    )
    handler.addFilter(ContextFilter(service))
    handler.addFilter(RedactingFilter(_redactor))

    root = logging.getLogger()
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(level.upper())

    # Uvicorn and Celery ship their own handlers; route them through this one.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "celery", "celery.app.trace"):
        library_logger = logging.getLogger(name)
        library_logger.handlers = []
        library_logger.propagate = True

    return handler


@contextmanager
def request_context(request_id: str) -> Iterator[None]:
    token = _request_id.set(request_id)
    try:
        yield
    finally:
        _request_id.reset(token)


@contextmanager
def job_context(job_id: str, phase: str | None = None) -> Iterator[None]:
    job_token = _job_id.set(job_id)
    phase_token = _phase.set(phase)
    try:
        yield
    finally:
        _phase.reset(phase_token)
        _job_id.reset(job_token)


def set_phase(phase: str | None) -> None:
    _phase.set(phase)


def current_request_id() -> str | None:
    return _request_id.get()
