"""The wire contract for permanent deletion.

The documented OpenAPI shape and the shape the running app serves are asserted
against each other, so the generated browser client cannot drift from the server
that answers it. The behavior the contract fixes is a no-content success and an
anonymous job-history shell — the deleted track leaves no identity behind.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text

from chillify.domain.models import to_rfc3339
from chillify.infrastructure.db.engine import create_database_engine
from chillify.infrastructure.db.repositories import new_id

pytestmark = pytest.mark.contract

BACKEND_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_AUDIO = BACKEND_ROOT / "tests" / "fixtures" / "media" / "gate-tone.mp3"
OPENAPI_PATH = "/api/v1/openapi.json"


@pytest.fixture
def environment(
    valid_environment: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> dict[str, str]:
    for key, value in valid_environment.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("CHILLIFY_FIXTURE_ROOT", raising=False)

    database_path = Path(valid_environment["CHILLIFY_DATA_ROOT"]) / "db" / "chillify.sqlite3"
    database_path.parent.mkdir(parents=True, exist_ok=True)
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database_path}")
    command.upgrade(config, "head")
    return valid_environment


@pytest.fixture
def client(environment: dict[str, str]) -> Iterator[TestClient]:
    from chillify.api.main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client


@pytest.fixture
def seeded_track_with_job(environment: dict[str, str]) -> tuple[str, str]:
    """One real MP3 and its completed job, so anonymization is exercised."""
    music_root = Path(environment["CHILLIFY_MUSIC_ROOT"])
    engine = create_database_engine(
        Path(environment["CHILLIFY_DATA_ROOT"]) / "db" / "chillify.sqlite3"
    )
    track_id = new_id()
    job_id = new_id()
    relative_path = "Music/Sigur Ros/Takk/01 - Hoppipolla.mp3"
    content = FIXTURE_AUDIO.read_bytes()
    absolute = music_root / relative_path
    absolute.parent.mkdir(parents=True, exist_ok=True)
    absolute.write_bytes(content)

    moment = to_rfc3339(datetime.now(UTC))
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO tracks (id, title, artist, album, release_year, disc_number,"
                    " track_number, duration_ms, normalized_artist, normalized_title,"
                    " normalized_album, file_relpath, mime_type, file_size_bytes, content_sha256,"
                    " availability, revision, created_at, updated_at)"
                    " VALUES (:id, 'Hoppipolla', 'Sigur Ros', 'Takk', 2005, 1, 1, 180000,"
                    " 'sigur ros', 'hoppipolla', 'takk', :relpath, 'audio/mpeg', :size, :digest,"
                    " 'available', 1, :moment, :moment)"
                ),
                {
                    "id": track_id,
                    "relpath": relative_path,
                    "size": len(content),
                    "digest": hashlib.sha256(content).hexdigest(),
                    "moment": moment,
                },
            )
            connection.execute(
                text(
                    "INSERT INTO download_jobs (id, provider, source_type, source_ref, dedupe_key,"
                    " request_json, candidate_json, state, phase, result_track_id, restart_count,"
                    " version, created_at, started_at, finished_at, updated_at)"
                    " VALUES (:id, 'deezer', 'deezer_result', 'deezer:track:42', 'deezer:42',"
                    " :request, :candidate, 'completed', 'completed', :track, 0, 1, :moment,"
                    " :moment, :moment, :moment)"
                ),
                {
                    "id": job_id,
                    "request": json.dumps({"deezer_id": 42, "title": "Hoppipolla"}),
                    "candidate": json.dumps({"url": "https://deezer/42"}),
                    "track": track_id,
                    "moment": moment,
                },
            )
    finally:
        engine.dispose()
    return track_id, job_id


class TestDocumentedShape:
    def test_the_deletion_routes_are_documented(self, client: TestClient) -> None:
        paths = client.get(OPENAPI_PATH).json()["paths"]

        assert "delete" in paths["/api/v1/tracks/{track_id}"]
        assert "get" in paths["/api/v1/tracks/{track_id}/delete-impact"]

    def test_deletion_documents_a_no_content_response_and_if_match(
        self, client: TestClient
    ) -> None:
        operation = client.get(OPENAPI_PATH).json()["paths"]["/api/v1/tracks/{track_id}"]["delete"]

        assert "204" in operation["responses"]
        assert "content" not in operation["responses"]["204"]
        assert any(
            parameter["name"] == "If-Match" and parameter["in"] == "header"
            for parameter in operation["parameters"]
        )

    def test_the_delete_impact_shape_exposes_only_a_playlist_count(
        self, client: TestClient
    ) -> None:
        document = client.get(OPENAPI_PATH).json()
        impact: dict[str, Any] = document["components"]["schemas"]["DeleteImpactModel"]

        assert set(impact["properties"]) == {"playlist_count"}


class TestServedShape:
    def test_deleting_a_track_returns_no_content(
        self, client: TestClient, seeded_track_with_job: tuple[str, str]
    ) -> None:
        track_id, _ = seeded_track_with_job

        response = client.delete(f"/api/v1/tracks/{track_id}", headers={"If-Match": "1"})

        assert response.status_code == 204
        assert response.content == b""
        assert client.get(f"/api/v1/tracks/{track_id}").status_code == 404

    def test_deletion_leaves_only_an_anonymous_history_shell(
        self,
        client: TestClient,
        seeded_track_with_job: tuple[str, str],
        environment: dict[str, str],
    ) -> None:
        track_id, job_id = seeded_track_with_job

        client.delete(f"/api/v1/tracks/{track_id}", headers={"If-Match": "1"})

        engine = create_database_engine(
            Path(environment["CHILLIFY_DATA_ROOT"]) / "db" / "chillify.sqlite3"
        )
        try:
            with engine.connect() as connection:
                job = (
                    connection.execute(
                        text(
                            "SELECT provider, state, phase, source_ref, dedupe_key, request_json,"
                            " candidate_json, result_track_id FROM download_jobs WHERE id = :id"
                        ),
                        {"id": job_id},
                    )
                    .mappings()
                    .one()
                )
        finally:
            engine.dispose()

        # The shell keeps its provider and lifecycle, and nothing that identifies
        # the track it produced.
        assert job["provider"] == "deezer"
        assert job["state"] == "completed"
        assert job["phase"] == "completed"
        assert job["result_track_id"] is None
        assert job["source_ref"] == "deleted"
        assert job["dedupe_key"] == "deleted"
        assert job["request_json"] == "{}"
        assert job["candidate_json"] is None

    def test_a_refused_deletion_uses_the_one_error_envelope(
        self, client: TestClient, seeded_track_with_job: tuple[str, str]
    ) -> None:
        track_id, _ = seeded_track_with_job

        response = client.delete(f"/api/v1/tracks/{track_id}", headers={"If-Match": "9"})

        assert response.status_code == 409
        error = response.json()["error"]
        assert set(error) == {"code", "message", "field", "retryable", "request_id", "detail"}
        assert error["code"] == "record_changed"
