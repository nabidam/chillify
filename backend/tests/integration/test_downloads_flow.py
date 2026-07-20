"""Durable acquisition: queueing, running, restarting, and staying serial."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from chillify.application.downloads import DownloadService
from chillify.composition import Composition
from chillify.domain.jobs import JobId, JobState
from chillify.infrastructure.queue.celery_app import create_celery_app

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
    job: dict[str, object] = response.json()
    assert job["state"] == "queued"
    assert job["display_state"] == "queued"
    return str(job["id"])


class TestDurableCompletion:
    def test_a_job_survives_the_browser_and_shows_a_mounted_track_afterwards(
        self,
        gate_api: TestClient,
        gate_downloads: DownloadService,
        gate_composition: Composition,
        dispatched_jobs: list[str],
    ) -> None:
        """The browser is not part of the machinery.

        The request is committed, the worker runs it with no client attached,
        and a freshly opened client sees the completion and the playable track.
        """
        candidate = deezer_candidate(gate_api, "daft punk")
        job_id = queue_download(gate_api, candidate)
        assert dispatched_jobs == [job_id]

        # The browser goes away entirely; only the worker remains.
        gate_api.close()
        gate_downloads.run_job(JobId(job_id))

        reopened = TestClient(gate_api.app)
        detail = reopened.get(f"/api/v1/downloads/{job_id}").json()
        assert detail["job"]["state"] == "completed"
        assert detail["job"]["progress_percent"] == 100.0
        assert detail["job"]["result_track_id"] is not None

        tracks = reopened.get("/api/v1/library/tracks").json()["items"]
        assert [track["title"] for track in tracks] == [candidate["title"]]
        assert tracks[0]["is_playable"] is True

        stream = reopened.get(f"/api/v1/tracks/{tracks[0]['id']}/stream")
        assert stream.status_code == 200
        assert stream.headers["content-type"] == "audio/mpeg"

    def test_the_event_history_records_every_phase_it_passed_through(
        self, gate_api: TestClient, gate_downloads: DownloadService
    ) -> None:
        job_id = queue_download(gate_api, deezer_candidate(gate_api, "sigur"))

        gate_downloads.run_job(JobId(job_id))

        events = gate_api.get(f"/api/v1/downloads/{job_id}").json()["events"]
        phases = [event["phase"] for event in events]
        assert phases[0] == "accepted"
        assert phases[-1] == "completed"
        for phase in ("downloading", "converting", "enriching", "tagging", "organizing"):
            assert phase in phases
        assert [event["sequence"] for event in events] == list(range(1, len(events) + 1))

    def test_the_workspace_is_removed_once_the_track_is_published(
        self,
        gate_api: TestClient,
        gate_downloads: DownloadService,
        gate_composition: Composition,
    ) -> None:
        job_id = queue_download(gate_api, deezer_candidate(gate_api, "daft punk"))

        gate_downloads.run_job(JobId(job_id))

        workspace = gate_composition.settings.music_root / ".chillify" / "work" / job_id
        assert not workspace.exists()

    def test_a_second_request_for_an_active_job_is_refused_as_a_duplicate(
        self, gate_api: TestClient, dispatched_jobs: list[str]
    ) -> None:
        """The partial unique index, not a pre-check, is what makes this true."""
        candidate = deezer_candidate(gate_api, "daft punk")
        first = queue_download(gate_api, candidate)

        repeat = gate_api.post(
            "/api/v1/downloads",
            json={"source_type": "deezer_result", "candidate": candidate},
        )

        assert repeat.status_code == 409
        assert repeat.json()["error"]["code"] == "duplicate_record"
        assert dispatched_jobs == [first]

    def test_an_idempotency_key_replays_the_first_response(
        self, gate_api: TestClient, dispatched_jobs: list[str]
    ) -> None:
        candidate = deezer_candidate(gate_api, "massive attack")
        body = {"source_type": "deezer_result", "candidate": candidate}
        headers = {"Idempotency-Key": "01JZZ-key"}

        first = gate_api.post("/api/v1/downloads", json=body, headers=headers)
        second = gate_api.post("/api/v1/downloads", json=body, headers=headers)

        assert first.status_code == 201
        assert second.status_code == 201
        assert first.json() == second.json()
        assert len(dispatched_jobs) == 1

    def test_reusing_a_key_for_a_different_body_is_refused(self, gate_api: TestClient) -> None:
        headers = {"Idempotency-Key": "01JZZ-key"}
        gate_api.post(
            "/api/v1/downloads",
            json={
                "source_type": "deezer_result",
                "candidate": deezer_candidate(gate_api, "massive attack"),
            },
            headers=headers,
        )

        conflict = gate_api.post(
            "/api/v1/downloads",
            json={
                "source_type": "deezer_result",
                "candidate": deezer_candidate(gate_api, "daft punk"),
            },
            headers=headers,
        )

        assert conflict.status_code == 409
        assert conflict.json()["error"]["code"] == "duplicate_record"


class TestSerialExecution:
    def test_three_jobs_never_overlap_an_acquisition_phase(
        self, gate_api: TestClient, gate_downloads: DownloadService
    ) -> None:
        """Serial means the durable history has no interleaving, not that it
        merely looks fast enough. The committed events are the evidence."""
        job_ids = [
            queue_download(gate_api, deezer_candidate(gate_api, query))
            for query in ("daft punk", "sigur", "massive attack")
        ]

        for job_id in job_ids:
            gate_downloads.run_job(JobId(job_id))

        history = list(_durable_history(gate_api, job_ids))
        running: set[str] = set()
        for job_id, state in history:
            if state == JobState.RUNNING.value:
                running.add(job_id)
            elif state in {"completed", "failed", "cancelled"}:
                running.discard(job_id)
            assert len(running) <= 1, "two jobs held an acquisition phase at once"

        assert all(
            gate_api.get(f"/api/v1/downloads/{job_id}").json()["job"]["state"] == "completed"
            for job_id in job_ids
        )

    def test_the_worker_is_configured_for_one_task_at_a_time(
        self, gate_composition: Composition
    ) -> None:
        celery_app = create_celery_app(gate_composition.settings)

        assert celery_app.conf.worker_concurrency == 1
        assert celery_app.conf.worker_prefetch_multiplier == 1
        assert celery_app.conf.task_acks_late is True
        # Celery retry is reserved for delivery failures; application retries
        # are recorded on the same job, never as a hidden parallel attempt.
        assert celery_app.conf.task_max_retries == 0


def _durable_history(client: TestClient, job_ids: list[str]) -> Iterator[tuple[str, str]]:
    """Every job's events, replayed in the order they were committed."""
    events = []
    for job_id in job_ids:
        events.extend(client.get(f"/api/v1/downloads/{job_id}").json()["events"])
    for event in sorted(events, key=lambda item: int(item["id"])):
        yield str(event["job_id"]), str(event["state"])
