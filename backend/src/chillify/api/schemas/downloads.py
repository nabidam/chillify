"""Search-result, download-request, and job wire shapes.

A remote candidate always reports `is_playable: false`. It is stated rather
than implied so no component has to infer playability from a missing field, and
no screen can render Play for something the library does not hold.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from chillify.application.downloads import JobDetail
from chillify.application.search import RemoteResult
from chillify.domain.jobs import DownloadJob, JobEvent
from chillify.domain.protocols import TrackCandidate

JobStateLiteral = Literal["queued", "running", "completed", "failed", "cancelled"]
DisplayStateLiteral = Literal[
    "queued", "retrying", "restarted", "running", "completed", "failed", "cancelled"
]
PhaseLiteral = Literal[
    "accepted",
    "inspecting",
    "queued",
    "restarted",
    "downloading",
    "converting",
    "enriching",
    "tagging",
    "organizing",
    "completed",
    "failed",
    "cancelled",
]
SourceTypeLiteral = Literal["deezer_result", "radiojavan_track", "spotify_track", "youtube_video"]


class TrackCandidateModel(BaseModel):
    """One normalized remote candidate, from any provider, in one shape."""

    provider: str
    source_id: str | None
    source_url: str
    title: str
    artist: str
    album: str | None
    release_year: int | None
    disc_number: int | None
    track_number: int | None
    duration_ms: int | None
    isrc: str | None
    artwork_url: str | None
    acquisition_locator: str
    raw_fingerprint: str | None

    @classmethod
    def of(cls, candidate: TrackCandidate) -> TrackCandidateModel:
        return cls(
            provider=candidate.provider,
            source_id=candidate.source_id,
            source_url=candidate.source_url,
            title=candidate.title,
            artist=candidate.artist,
            album=candidate.album,
            release_year=candidate.release_year,
            disc_number=candidate.disc_number,
            track_number=candidate.track_number,
            duration_ms=candidate.duration_ms,
            isrc=candidate.isrc,
            artwork_url=candidate.artwork_url,
            acquisition_locator=candidate.acquisition_locator,
            raw_fingerprint=candidate.raw_fingerprint,
        )

    def to_candidate(self) -> TrackCandidate:
        return TrackCandidate(
            provider=self.provider,
            source_id=self.source_id,
            source_url=self.source_url,
            title=self.title,
            artist=self.artist,
            album=self.album,
            release_year=self.release_year,
            disc_number=self.disc_number,
            track_number=self.track_number,
            duration_ms=self.duration_ms,
            isrc=self.isrc,
            artwork_url=self.artwork_url,
            acquisition_locator=self.acquisition_locator,
            raw_fingerprint=self.raw_fingerprint,
        )


class RemoteResultModel(BaseModel):
    """One search result, and the local track it duplicates when there is one."""

    candidate: TrackCandidateModel
    is_playable: Literal[False] = Field(
        default=False,
        description="Always false. A remote result has no local file, so no screen offers Play.",
    )
    existing_track_id: str | None = Field(
        default=None,
        description="The local track this result already duplicates, if any.",
    )

    @classmethod
    def of(cls, result: RemoteResult) -> RemoteResultModel:
        return cls(
            candidate=TrackCandidateModel.of(result.candidate),
            existing_track_id=(
                None if result.existing_track_id is None else str(result.existing_track_id)
            ),
        )


class DownloadRequestModel(BaseModel):
    """One immutable acquisition request.

    The candidate is echoed back from a search result rather than re-fetched:
    what the person saw when they pressed Download is exactly what is stored
    and later acquired.
    """

    source_type: SourceTypeLiteral
    candidate: TrackCandidateModel


class CancelRequestModel(BaseModel):
    """The optimistic-concurrency guard for one cancel.

    `version` is the value the browser last saw. A cancel built on a stale view
    is refused rather than applied to a job that has since moved on.
    """

    version: int = Field(ge=1, description="The job version the request was built against.")


class JobEventModel(BaseModel):
    """One durable, replayable step in a job's history."""

    id: int = Field(description="The SSE event ID. The browser's cursor tracks this sequence.")
    job_id: str
    sequence: int
    state: JobStateLiteral
    phase: PhaseLiteral
    progress_percent: float | None
    payload: dict[str, str | int | float | bool]
    occurred_at: datetime

    @classmethod
    def of(cls, event: JobEvent) -> JobEventModel:
        return cls(
            id=event.id,
            job_id=str(event.job_id),
            sequence=event.sequence,
            state=event.state.value,
            phase=event.phase.value,
            progress_percent=event.progress_percent,
            payload=event.payload,
            occurred_at=event.occurred_at,
        )


class JobModel(BaseModel):
    """One download as the Downloads screen and the job indicator render it."""

    id: str
    provider: Literal["deezer", "radiojavan", "spotdl", "yt_dlp"]
    source_type: SourceTypeLiteral
    state: JobStateLiteral
    display_state: DisplayStateLiteral = Field(
        description="Derived state: distinguishes a retry and a restart from a first attempt."
    )
    phase: PhaseLiteral
    progress_percent: float | None = Field(
        description="Null when the provider reports no real percentage. Never invented."
    )
    restart_count: int
    parent_job_id: str | None
    error_code: str | None
    error_message: str | None
    result_track_id: str | None
    version: int
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    updated_at: datetime

    @classmethod
    def of(cls, job: DownloadJob) -> JobModel:
        return cls(
            id=str(job.id),
            provider=job.provider.value,
            source_type=job.source_type.value,
            state=job.state.value,
            display_state=job.display_state.value,
            phase=job.phase.value,
            progress_percent=job.progress_percent,
            restart_count=job.restart_count,
            parent_job_id=None if job.parent_job_id is None else str(job.parent_job_id),
            error_code=job.error_code,
            error_message=job.error_message,
            result_track_id=None if job.result_track_id is None else str(job.result_track_id),
            version=job.version,
            created_at=job.created_at,
            started_at=job.started_at,
            finished_at=job.finished_at,
            updated_at=job.updated_at,
        )


class JobDetailModel(BaseModel):
    """One job together with its complete replayable history."""

    job: JobModel
    events: list[JobEventModel]

    @classmethod
    def of(cls, detail: JobDetail) -> JobDetailModel:
        return cls(
            job=JobModel.of(detail.job),
            events=[JobEventModel.of(event) for event in detail.events],
        )
