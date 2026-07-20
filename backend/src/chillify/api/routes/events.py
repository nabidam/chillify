"""The single server-sent event stream.

Durable job events carry an SSE `id` taken from `job_events.id`. Transient
invalidations deliberately carry none, so the browser's one `Last-Event-ID`
cursor belongs exclusively to the durable job sequence and a reconnect replays
exactly what was missed — no more, and nothing that was never persisted.

The browser treats every payload here as an invalidation signal, never as the
durable copy of anything.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Iterator
from typing import Annotated, Any, Final

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import StreamingResponse

from chillify.api.dependencies import get_composition, get_download_service
from chillify.api.schemas.downloads import JobEventModel
from chillify.application.downloads import DownloadService
from chillify.composition import Composition
from chillify.domain.jobs import JobState

logger = logging.getLogger(__name__)

router = APIRouter(tags=["events"])

# How often the stream looks for newly committed job events.
POLL_SECONDS: Final = 1.0

# A comment heartbeat detects a dead connection through an idle proxy.
HEARTBEAT_SECONDS: Final = 15.0

MEDIA_TYPE: Final = "text/event-stream"


@router.get(
    "/events",
    summary="Stream job, library, and system invalidations",
    response_class=StreamingResponse,
    responses={200: {"content": {MEDIA_TYPE: {"schema": {"type": "string"}}}}},
)
def stream_events(
    downloads: Annotated[DownloadService, Depends(get_download_service)],
    composition: Annotated[Composition, Depends(get_composition)],
    last_event_id_header: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
    last_event_id: Annotated[
        str | None, Query(description="Cursor fallback for clients that cannot set the header.")
    ] = None,
) -> StreamingResponse:
    cursor = _parse_cursor(last_event_id_header or last_event_id)
    return StreamingResponse(
        event_frames(downloads, composition, cursor),
        media_type=MEDIA_TYPE,
        headers={
            # nginx must not buffer this response; a buffered stream is a
            # stream that arrives after it stopped being useful.
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


def event_frames(
    downloads: DownloadService, composition: Composition, cursor: int
) -> Iterator[str]:
    """Yield the reconnect snapshot, then every durable event as it commits."""
    if cursor < 0:
        # No usable cursor: start from now. Replaying the whole history to a
        # browser that lost its place would show old downloads as if they had
        # just happened.
        cursor = downloads.latest_event_id()
    yield _frame("system.changed", _system_payload(composition))

    last_beat = time.monotonic()
    while True:
        events = downloads.events_after(cursor)
        for event in events:
            cursor = event.id
            yield _frame(
                "job.changed",
                JobEventModel.of(event).model_dump(mode="json"),
                event_id=event.id,
            )
            # A completed job is the moment the library actually changed; the
            # browser refetches rather than trusting this payload as the copy.
            if event.state is JobState.COMPLETED:
                yield _frame("library.changed", {"job_id": str(event.job_id)})

        now = time.monotonic()
        if events:
            last_beat = now
        elif now - last_beat >= HEARTBEAT_SECONDS:
            last_beat = now
            yield ": heartbeat\n\n"

        time.sleep(POLL_SECONDS)


def _system_payload(composition: Composition) -> dict[str, Any]:
    status = composition.system_status()
    return {
        "ready": status.ready,
        "degraded": status.degraded,
        "redis": status.redis.health.value,
    }


def _frame(event: str, data: dict[str, Any], *, event_id: int | None = None) -> str:
    lines = [] if event_id is None else [f"id: {event_id}"]
    lines.append(f"event: {event}")
    lines.append(f"data: {json.dumps(data, separators=(',', ':'), sort_keys=True)}")
    return "\n".join(lines) + "\n\n"


def _parse_cursor(value: str | None) -> int:
    """Parse the SSE cursor, or return -1 meaning "start from now"."""
    if value is None or not value.strip():
        return -1
    try:
        return max(0, int(value))
    except ValueError:
        logger.info("unreadable Last-Event-ID; starting a fresh cursor")
        return -1
