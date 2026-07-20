"""The durable download-job state machine.

Five stored states and one stored phase describe every acquisition. The states
are the durable truth; the phases are the narrative a person reads while the
work happens. Everything a UI shows is derived from these two columns, so a
restart never has to reconstruct a transition it did not persist.

`display_state` exists because the browser needs to distinguish a first attempt
from a retry and from a restart, while persistence must not grow ambiguous
values. It is derived, never stored.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Final, NewType

from chillify.domain.errors import ValidationFailedError
from chillify.domain.models import TrackId

JobId = NewType("JobId", str)


class JobState(StrEnum):
    """The five durable states in the `download_jobs` check constraint."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobPhase(StrEnum):
    """Where inside a state the work currently is."""

    ACCEPTED = "accepted"
    INSPECTING = "inspecting"
    QUEUED = "queued"
    RESTARTED = "restarted"
    DOWNLOADING = "downloading"
    CONVERTING = "converting"
    ENRICHING = "enriching"
    TAGGING = "tagging"
    ORGANIZING = "organizing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobProvider(StrEnum):
    """The adapter that will perform the acquisition."""

    DEEZER = "deezer"
    SPOTDL = "spotdl"
    YT_DLP = "yt_dlp"


class SourceType(StrEnum):
    """The kind of thing the person asked Chillify to acquire."""

    DEEZER_RESULT = "deezer_result"
    SPOTIFY_TRACK = "spotify_track"
    YOUTUBE_VIDEO = "youtube_video"


class DisplayState(StrEnum):
    """The state a UI renders. Derived from the durable columns, never stored."""

    QUEUED = "queued"
    RETRYING = "retrying"
    RESTARTED = "restarted"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# The ordered work phases a successful acquisition passes through. The worker
# walks exactly this sequence, so the browser can render remaining work without
# each adapter inventing its own vocabulary.
ACQUISITION_PHASES: Final = (
    JobPhase.DOWNLOADING,
    JobPhase.CONVERTING,
    JobPhase.ENRICHING,
    JobPhase.TAGGING,
    JobPhase.ORGANIZING,
)

# Which adapter serves which requested entity. A source type absent from this
# mapping is an entity Chillify does not acquire.
PROVIDER_FOR_SOURCE: Final = {
    SourceType.DEEZER_RESULT: JobProvider.YT_DLP,
    SourceType.YOUTUBE_VIDEO: JobProvider.YT_DLP,
    SourceType.SPOTIFY_TRACK: JobProvider.SPOTDL,
}

_TERMINAL_STATES: Final = frozenset({JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED})

# The complete durable transition table. A transition absent here is a bug in a
# caller, not a condition to tolerate: the stored row is what a restart reads.
_ALLOWED_TRANSITIONS: Final = {
    JobState.QUEUED: frozenset({JobState.QUEUED, JobState.RUNNING, JobState.CANCELLED}),
    JobState.RUNNING: frozenset(
        {
            JobState.RUNNING,
            JobState.QUEUED,
            JobState.COMPLETED,
            JobState.FAILED,
            JobState.CANCELLED,
        }
    ),
    JobState.COMPLETED: frozenset(),
    JobState.FAILED: frozenset(),
    JobState.CANCELLED: frozenset(),
}


class InvalidJobTransitionError(ValidationFailedError):
    """A caller asked for a durable transition the state machine forbids."""

    code = "invalid_job_transition"
    status_code = 409


def assert_transition(current: JobState, target: JobState) -> None:
    """Raise unless `current -> target` is an approved durable transition."""
    if target not in _ALLOWED_TRANSITIONS[current]:
        raise InvalidJobTransitionError(
            "That download has already finished and cannot change state.",
            context={"from_state": str(current), "to_state": str(target)},
        )


def is_terminal(state: JobState) -> bool:
    return state in _TERMINAL_STATES


def build_dedupe_key(provider: JobProvider, source_type: SourceType, source_ref: str) -> str:
    """The key the partial unique index uses to reject a duplicate active request.

    Two people in the house pressing Download on the same result must produce
    one job. The reference is case-folded and whitespace-collapsed so trivially
    different spellings of the same URL still collide.
    """
    reference = unicodedata.normalize("NFKC", source_ref).strip().casefold()
    if not reference:
        raise ValidationFailedError(
            "A download request must name what to acquire.", field="source_ref"
        )
    return f"{provider}:{source_type}:{reference}"


@dataclass(frozen=True, slots=True)
class JobEvent:
    """One durable, replayable step in a job's history.

    `id` is the SSE event ID: the browser's single `Last-Event-ID` cursor
    belongs to this sequence and to nothing else.
    """

    id: int
    job_id: JobId
    sequence: int
    state: JobState
    phase: JobPhase
    progress_percent: float | None
    payload: dict[str, str | int | float | bool]
    occurred_at: datetime


@dataclass(frozen=True, slots=True)
class DownloadJob:
    """One durable acquisition request and everything a restart needs to resume it."""

    id: JobId
    provider: JobProvider
    source_type: SourceType
    source_ref: str
    dedupe_key: str
    state: JobState
    phase: JobPhase
    progress_percent: float | None
    celery_task_id: str | None
    parent_job_id: JobId | None
    restart_count: int
    cancel_requested_at: datetime | None
    error_code: str | None
    error_message: str | None
    result_track_id: TrackId | None
    version: int
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    updated_at: datetime

    @property
    def display_state(self) -> DisplayState:
        """The state a person sees, distinguishing a retry from a restart."""
        if self.state is not JobState.QUEUED:
            return DisplayState(self.state.value)
        if self.parent_job_id is not None:
            return DisplayState.RETRYING
        if self.restart_count > 0:
            return DisplayState.RESTARTED
        return DisplayState.QUEUED

    @property
    def is_cancel_requested(self) -> bool:
        return self.cancel_requested_at is not None
