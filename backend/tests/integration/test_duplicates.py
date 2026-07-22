"""Cancel, retry, and deduplication: one intent, one track, one file."""

from __future__ import annotations

import threading
import time

import pytest
from fastapi.testclient import TestClient

from chillify.application.downloads import DownloadService
from chillify.composition import Composition
from chillify.domain.errors import RecordChangedError
from chillify.domain.jobs import InvalidJobTransitionError, JobId, JobState

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


def read_job(client: TestClient, job_id: str) -> dict[str, object]:
    detail: dict[str, object] = client.get(f"/api/v1/downloads/{job_id}").json()["job"]
    return detail


def _mounted_mp3s(composition: Composition) -> list[str]:
    music = composition.settings.music_root / "Music"
    if not music.is_dir():
        return []
    return sorted(str(path.relative_to(music)) for path in music.rglob("*.mp3"))


class TestDuplicateRequests:
    def test_two_requests_for_one_result_yield_a_single_job(
        self, gate_api: TestClient, dispatched_jobs: list[str]
    ) -> None:
        """The partial unique index, not a pre-check, keeps a race to one job."""
        candidate = deezer_candidate(gate_api, "daft punk")
        first = queue_download(gate_api, candidate)

        second = gate_api.post(
            "/api/v1/downloads",
            json={"source_type": "deezer_result", "candidate": candidate},
        )

        assert second.status_code == 409
        assert second.json()["error"]["code"] == "duplicate_record"
        assert dispatched_jobs == [first]

    def test_a_completed_download_makes_the_next_search_report_the_existing_track(
        self, gate_api: TestClient, gate_downloads: DownloadService
    ) -> None:
        """Resubmitting a duplicate reaches the track already held, not a copy."""
        candidate = deezer_candidate(gate_api, "daft punk")
        job_id = queue_download(gate_api, candidate)
        gate_downloads.run_job(JobId(job_id))

        track_id = read_job(gate_api, job_id)["result_track_id"]
        results = gate_api.get("/api/v1/search/deezer", params={"q": "daft punk"}).json()["items"]
        matching = [r for r in results if r["candidate"]["title"] == candidate["title"]]
        assert matching, "the completed track should still appear as a search result"
        assert matching[0]["existing_track_id"] == track_id

    def test_running_the_same_acquisition_leaves_one_track_and_one_file(
        self, gate_api: TestClient, gate_downloads: DownloadService, gate_composition: Composition
    ) -> None:
        job_id = queue_download(gate_api, deezer_candidate(gate_api, "sigur"))
        gate_downloads.run_job(JobId(job_id))

        assert len(gate_api.get("/api/v1/library/tracks").json()["items"]) == 1
        assert len(_mounted_mp3s(gate_composition)) == 1


class TestCancel:
    def test_cancelling_a_queued_job_finishes_it_and_frees_the_queue(
        self,
        gate_api: TestClient,
        gate_downloads: DownloadService,
        gate_composition: Composition,
    ) -> None:
        first = queue_download(gate_api, deezer_candidate(gate_api, "daft punk"))
        second = queue_download(gate_api, deezer_candidate(gate_api, "sigur"))
        # A queued job may already own a scratch workspace; cancel must clear it.
        workspace = gate_composition.settings.music_root / ".chillify" / "work" / first
        workspace.mkdir(parents=True, exist_ok=True)
        (workspace / "partial.part").write_bytes(b"half a download")

        version = int(read_job(gate_api, first)["version"])
        response = gate_api.post(f"/api/v1/downloads/{first}/cancel", json={"version": version})

        assert response.status_code == 200, response.text
        assert response.json()["state"] == "cancelled"
        assert not workspace.exists()

        # The queue advances: the untouched second job still runs to completion.
        gate_downloads.run_job(JobId(second))
        assert read_job(gate_api, second)["state"] == "completed"

    def test_cancelling_a_finished_job_is_refused(
        self, gate_api: TestClient, gate_downloads: DownloadService
    ) -> None:
        job_id = queue_download(gate_api, deezer_candidate(gate_api, "sigur"))
        gate_downloads.run_job(JobId(job_id))

        version = int(read_job(gate_api, job_id)["version"])
        response = gate_api.post(f"/api/v1/downloads/{job_id}/cancel", json={"version": version})

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "invalid_job_transition"

    def test_a_stale_version_cannot_cancel(self, gate_api: TestClient) -> None:
        job_id = queue_download(gate_api, deezer_candidate(gate_api, "daft punk"))

        response = gate_api.post(f"/api/v1/downloads/{job_id}/cancel", json={"version": 999})

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "record_changed"

    def test_cancelling_mid_download_stops_the_run_and_cleans_up(
        self,
        gate_api: TestClient,
        gate_downloads: DownloadService,
        gate_composition: Composition,
    ) -> None:
        """The real cooperative cancel: a running acquisition is stopped in flight.

        The worker runs on one thread while the cancel arrives on another, just
        as the request and the worker are different callers in production. The
        in-process signal trips the adapter's next cancellation check, so the
        run unwinds to `cancelled` and its workspace is removed.
        """
        job_id = queue_download(gate_api, deezer_candidate(gate_api, "massive attack"))

        worker = threading.Thread(target=gate_downloads.run_job, args=(JobId(job_id),))
        worker.start()
        try:
            _wait_until_running(gate_downloads, job_id)
            _cancel_running(gate_downloads, job_id)
        finally:
            worker.join(timeout=10)
        assert not worker.is_alive(), "the worker thread did not stop after the cancel"

        final = read_job(gate_api, job_id)
        assert final["state"] == "cancelled"
        assert final["result_track_id"] is None
        assert gate_api.get("/api/v1/library/tracks").json()["items"] == []
        workspace = gate_composition.settings.music_root / ".chillify" / "work" / job_id
        assert not workspace.exists()


class TestRetry:
    def test_retry_creates_a_new_attempt_linked_to_the_cancelled_job(
        self, gate_api: TestClient, gate_downloads: DownloadService, dispatched_jobs: list[str]
    ) -> None:
        parent = queue_download(gate_api, deezer_candidate(gate_api, "daft punk"))
        version = int(read_job(gate_api, parent)["version"])
        gate_api.post(f"/api/v1/downloads/{parent}/cancel", json={"version": version})

        response = gate_api.post(f"/api/v1/downloads/{parent}/retry")

        assert response.status_code == 201, response.text
        child = response.json()
        assert child["id"] != parent
        assert child["parent_job_id"] == parent
        assert child["state"] == "queued"
        assert child["display_state"] == "retrying"
        assert child["restart_count"] == 0
        assert dispatched_jobs[-1] == child["id"]

        # The linked attempt runs to completion and lands the track.
        gate_downloads.run_job(JobId(child["id"]))
        assert read_job(gate_api, str(child["id"]))["state"] == "completed"
        assert len(gate_api.get("/api/v1/library/tracks").json()["items"]) == 1

    def test_retrying_a_completed_job_is_refused(
        self, gate_api: TestClient, gate_downloads: DownloadService
    ) -> None:
        job_id = queue_download(gate_api, deezer_candidate(gate_api, "sigur"))
        gate_downloads.run_job(JobId(job_id))

        response = gate_api.post(f"/api/v1/downloads/{job_id}/retry")

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "invalid_job_transition"

    def test_a_repeated_retry_key_replays_the_first_linked_job(
        self, gate_api: TestClient, dispatched_jobs: list[str]
    ) -> None:
        parent = queue_download(gate_api, deezer_candidate(gate_api, "massive attack"))
        version = int(read_job(gate_api, parent)["version"])
        gate_api.post(f"/api/v1/downloads/{parent}/cancel", json={"version": version})
        headers = {"Idempotency-Key": "01JZZ-retry"}

        first = gate_api.post(f"/api/v1/downloads/{parent}/retry", headers=headers)
        second = gate_api.post(f"/api/v1/downloads/{parent}/retry", headers=headers)

        assert first.status_code == 201
        assert second.status_code == 201
        assert first.json() == second.json()
        # One child job, dispatched once, despite the repeated request.
        assert dispatched_jobs.count(first.json()["id"]) == 1


def _wait_until_running(downloads: DownloadService, job_id: str, *, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = downloads.get_job(JobId(job_id)).job
        if job.state is JobState.RUNNING:
            return
        if job.state in (JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED):
            raise AssertionError(f"job reached {job.state} before it could be cancelled")
        time.sleep(0.02)
    raise AssertionError("the job never entered the running state")


def _cancel_running(downloads: DownloadService, job_id: str, *, timeout: float = 5.0) -> None:
    """Cancel a running job, re-reading the churning version until it takes."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        version = downloads.get_job(JobId(job_id)).job.version
        try:
            downloads.cancel_download(JobId(job_id), expected_version=version)
            return
        except RecordChangedError:
            # Progress events advance the version between the read and the
            # cancel; take the next reading and try again.
            time.sleep(0.01)
        except InvalidJobTransitionError:
            # The run finished on its own before the cancel landed.
            return
    raise AssertionError("the running job could not be cancelled before it finished")
