"""Recovery of interrupted acquisitions: a dead worker never loses or doubles a job."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from chillify.application.downloads import DownloadService
from chillify.application.reconciliation import ReconciliationService
from chillify.composition import Composition
from chillify.domain.jobs import JobId, JobState
from chillify.domain.models import to_rfc3339
from chillify.infrastructure.db.models import DownloadJobRow
from chillify.infrastructure.db.repositories import JOB_LEASE_SECONDS, DownloadJobRepository

pytestmark = pytest.mark.integration


def deezer_candidate(client: TestClient, query: str) -> dict[str, object]:
    response = client.get("/api/v1/search/deezer", params={"q": query, "limit": 5})
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert items, f"the fixture payload has no match for {query!r}"
    candidate: dict[str, object] = items[0]["candidate"]
    return candidate


def queue_download(client: TestClient, candidate: dict[str, object]) -> str:
    response = client.post(
        "/api/v1/downloads",
        json={"source_type": "deezer_result", "candidate": candidate},
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


@pytest.fixture
def republished_jobs() -> list[str]:
    """Job IDs reconciliation handed back to the broker."""
    return []


@pytest.fixture
def reconcile(gate_composition: Composition, republished_jobs: list[str]) -> ReconciliationService:
    """Recovery bound to the disposable database, with a recording dispatcher."""

    def dispatch(job_id: JobId) -> str:
        republished_jobs.append(str(job_id))
        return f"task-{job_id}"

    return ReconciliationService(
        session_factory=gate_composition.session_factory,
        music_root=gate_composition.settings.music_root,
        dispatch=dispatch,
        queue_reachable=lambda: True,
    )


def _mounted_mp3s(composition: Composition) -> list[str]:
    music = composition.settings.music_root / "Music"
    if not music.is_dir():
        return []
    return sorted(str(path.relative_to(music)) for path in music.rglob("*.mp3"))


def _strand_running(composition: Composition, job_id: str) -> None:
    """Claim a job, then age its lease so it looks like a worker that died mid-run.

    The claim is the real transition a worker performs; ageing the lease past
    now is what a heartbeat that stopped arriving looks like to reconciliation.
    """
    jobs_session = composition.session_factory()
    try:
        jobs = DownloadJobRepository(jobs_session)
        claimed = jobs.claim(
            JobId(job_id),
            owner="dead-worker",
            now=datetime.now(UTC),
            lease_seconds=JOB_LEASE_SECONDS,
        )
        assert claimed is not None and claimed.state is JobState.RUNNING
        row = jobs_session.get(DownloadJobRow, job_id)
        assert row is not None
        row.lease_expires_at = to_rfc3339(datetime.now(UTC) - timedelta(minutes=5))
        jobs_session.commit()
    finally:
        jobs_session.close()


class TestInterruptedRunRecovers:
    def test_a_stranded_running_job_restarts_and_completes_exactly_once(
        self,
        gate_api: TestClient,
        gate_downloads: DownloadService,
        gate_composition: Composition,
        reconcile: ReconciliationService,
        republished_jobs: list[str],
    ) -> None:
        job_id = queue_download(gate_api, deezer_candidate(gate_api, "daft punk"))
        _strand_running(gate_composition, job_id)

        outcome = reconcile.reconcile()

        # The stranded run is returned to the queue as a restart and republished.
        assert outcome.restarted == (JobId(job_id),)
        assert republished_jobs == [job_id]
        detail = gate_api.get(f"/api/v1/downloads/{job_id}").json()["job"]
        assert detail["state"] == "queued"
        assert detail["phase"] == "restarted"
        assert detail["display_state"] == "restarted"
        assert detail["restart_count"] == 1

        # The recovered job now runs to completion, leaving one track and one file.
        gate_downloads.run_job(JobId(job_id))

        final = gate_api.get(f"/api/v1/downloads/{job_id}").json()["job"]
        assert final["state"] == "completed"
        assert final["result_track_id"] is not None
        assert len(gate_api.get("/api/v1/library/tracks").json()["items"]) == 1
        assert len(_mounted_mp3s(gate_composition)) == 1
        workspace = gate_composition.settings.music_root / ".chillify" / "work" / job_id
        assert not workspace.exists()

    def test_reconciliation_removes_the_stranded_runs_scratch_workspace(
        self,
        gate_api: TestClient,
        gate_composition: Composition,
        reconcile: ReconciliationService,
    ) -> None:
        job_id = queue_download(gate_api, deezer_candidate(gate_api, "sigur"))
        _strand_running(gate_composition, job_id)
        # A dead worker leaves a half-written workspace behind.
        workspace = gate_composition.settings.music_root / ".chillify" / "work" / job_id
        workspace.mkdir(parents=True, exist_ok=True)
        (workspace / "partial.part").write_bytes(b"half a download")

        reconcile.reconcile()

        assert not workspace.exists()


class TestUndeliveredWorkRepublishes:
    def test_a_queued_job_the_broker_never_carried_is_republished(
        self,
        gate_api: TestClient,
        gate_composition: Composition,
        reconcile: ReconciliationService,
        republished_jobs: list[str],
    ) -> None:
        """A job committed but never dispatched is exactly what a restart finds."""
        job_id = queue_download(gate_api, deezer_candidate(gate_api, "massive attack"))

        outcome = reconcile.reconcile()

        assert republished_jobs == [job_id]
        assert outcome.republished == (JobId(job_id),)
        # Its durable state is untouched: republication is a redelivery, not a
        # transition, so a queued job stays a first attempt.
        detail = gate_api.get(f"/api/v1/downloads/{job_id}").json()["job"]
        assert detail["state"] == "queued"
        assert detail["display_state"] == "queued"
        assert detail["restart_count"] == 0

    def test_republication_is_skipped_while_the_broker_is_unreachable(
        self,
        gate_api: TestClient,
        gate_composition: Composition,
        republished_jobs: list[str],
    ) -> None:
        job_id = queue_download(gate_api, deezer_candidate(gate_api, "daft punk"))

        def dispatch(job_id: JobId) -> str:
            republished_jobs.append(str(job_id))
            return f"task-{job_id}"

        offline = ReconciliationService(
            session_factory=gate_composition.session_factory,
            music_root=gate_composition.settings.music_root,
            dispatch=dispatch,
            queue_reachable=lambda: False,
        )

        outcome = offline.reconcile()

        # Nothing was handed to the dead broker, and the job is still queued for
        # the next reconnection pass to publish.
        assert republished_jobs == []
        assert outcome.republished == ()
        assert gate_api.get(f"/api/v1/downloads/{job_id}").json()["job"]["state"] == "queued"


def test_a_completed_job_is_left_untouched_by_reconciliation(
    gate_api: TestClient,
    gate_downloads: DownloadService,
    reconcile: ReconciliationService,
    republished_jobs: list[str],
) -> None:
    """Recovery only touches unfinished work; a terminal job is immutable."""
    job_id = queue_download(gate_api, deezer_candidate(gate_api, "sigur"))
    gate_downloads.run_job(JobId(job_id))
    assert gate_api.get(f"/api/v1/downloads/{job_id}").json()["job"]["state"] == "completed"

    outcome = reconcile.reconcile()

    assert outcome.restarted == ()
    assert outcome.republished == ()
    assert republished_jobs == []
    assert _leased_phase(gate_api, job_id) == "completed"


def _leased_phase(client: TestClient, job_id: str) -> str:
    return str(client.get(f"/api/v1/downloads/{job_id}").json()["job"]["phase"])
