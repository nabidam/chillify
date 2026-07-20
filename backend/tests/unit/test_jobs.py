"""The durable job state machine's derived and guarded behaviour."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from chillify.domain.errors import ValidationFailedError
from chillify.domain.jobs import (
    DisplayState,
    DownloadJob,
    InvalidJobTransitionError,
    JobId,
    JobPhase,
    JobProvider,
    JobState,
    SourceType,
    assert_transition,
    build_dedupe_key,
    is_terminal,
)

pytestmark = pytest.mark.unit

MOMENT = datetime(2026, 7, 21, 12, 0, tzinfo=UTC)


def make_job(**overrides: object) -> DownloadJob:
    defaults: dict[str, object] = {
        "id": JobId("019f8000-0000-7000-8000-00000000000a"),
        "provider": JobProvider.YT_DLP,
        "source_type": SourceType.DEEZER_RESULT,
        "source_ref": "https://www.deezer.com/track/3135556",
        "dedupe_key": "yt_dlp:deezer_result:https://www.deezer.com/track/3135556",
        "state": JobState.QUEUED,
        "phase": JobPhase.ACCEPTED,
        "progress_percent": None,
        "celery_task_id": None,
        "parent_job_id": None,
        "restart_count": 0,
        "cancel_requested_at": None,
        "error_code": None,
        "error_message": None,
        "result_track_id": None,
        "version": 1,
        "created_at": MOMENT,
        "started_at": None,
        "finished_at": None,
        "updated_at": MOMENT,
    }
    return DownloadJob(**{**defaults, **overrides})  # type: ignore[arg-type]


class TestDisplayState:
    def test_a_first_attempt_reads_as_queued(self) -> None:
        assert make_job().display_state is DisplayState.QUEUED

    def test_a_queued_job_with_a_parent_reads_as_retrying(self) -> None:
        job = make_job(parent_job_id=JobId("019f8000-0000-7000-8000-000000000001"))

        assert job.display_state is DisplayState.RETRYING

    def test_a_queued_job_that_was_interrupted_reads_as_restarted(self) -> None:
        assert make_job(restart_count=2).display_state is DisplayState.RESTARTED

    def test_a_running_job_reads_as_its_durable_state(self) -> None:
        assert make_job(state=JobState.RUNNING).display_state is DisplayState.RUNNING

    def test_a_retry_that_started_reads_as_running_not_retrying(self) -> None:
        """Only a queued job can be waiting to retry; a started one is running."""
        job = make_job(
            state=JobState.RUNNING,
            parent_job_id=JobId("019f8000-0000-7000-8000-000000000001"),
        )

        assert job.display_state is DisplayState.RUNNING


class TestTransitions:
    @pytest.mark.parametrize(
        ("current", "target"),
        [
            (JobState.QUEUED, JobState.RUNNING),
            (JobState.QUEUED, JobState.CANCELLED),
            (JobState.RUNNING, JobState.COMPLETED),
            (JobState.RUNNING, JobState.FAILED),
            (JobState.RUNNING, JobState.QUEUED),
        ],
    )
    def test_approved_transitions_are_allowed(self, current: JobState, target: JobState) -> None:
        assert_transition(current, target)

    @pytest.mark.parametrize(
        ("current", "target"),
        [
            (JobState.COMPLETED, JobState.RUNNING),
            (JobState.FAILED, JobState.COMPLETED),
            (JobState.CANCELLED, JobState.QUEUED),
            (JobState.QUEUED, JobState.COMPLETED),
        ],
    )
    def test_a_finished_job_cannot_change_state(self, current: JobState, target: JobState) -> None:
        with pytest.raises(InvalidJobTransitionError):
            assert_transition(current, target)

    def test_terminal_states_are_the_three_finished_ones(self) -> None:
        finished = {state for state in JobState if is_terminal(state)}

        assert finished == {JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED}


class TestDedupeKey:
    def test_the_same_request_spelled_differently_collides(self) -> None:
        first = build_dedupe_key(
            JobProvider.YT_DLP, SourceType.YOUTUBE_VIDEO, "https://YouTube.com/watch?v=ABC "
        )
        second = build_dedupe_key(
            JobProvider.YT_DLP, SourceType.YOUTUBE_VIDEO, "https://youtube.com/watch?v=abc"
        )

        assert first == second

    def test_the_same_reference_from_different_sources_does_not_collide(self) -> None:
        video = build_dedupe_key(JobProvider.YT_DLP, SourceType.YOUTUBE_VIDEO, "abc")
        track = build_dedupe_key(JobProvider.SPOTDL, SourceType.SPOTIFY_TRACK, "abc")

        assert video != track

    def test_an_empty_reference_is_rejected(self) -> None:
        with pytest.raises(ValidationFailedError):
            build_dedupe_key(JobProvider.YT_DLP, SourceType.YOUTUBE_VIDEO, "   ")
