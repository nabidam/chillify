"""The wire contract for atomic correction and playlists.

The documented OpenAPI shape and the shape the running app actually serves are
asserted against each other here, so the generated browser client cannot drift
away from the server that answers it.
"""

from __future__ import annotations

import hashlib
import io
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from PIL import Image
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
def seeded_track(environment: dict[str, str]) -> str:
    """One real MP3 and its row, so the contract is exercised end to end."""
    music_root = Path(environment["CHILLIFY_MUSIC_ROOT"])
    engine = create_database_engine(
        Path(environment["CHILLIFY_DATA_ROOT"]) / "db" / "chillify.sqlite3"
    )
    track_id = new_id()
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
                    " normalized_album, file_relpath, mime_type, file_size_bytes,"
                    " content_sha256, availability, revision, created_at, updated_at)"
                    " VALUES (:id, 'Hoppipolla', 'Sigur Ros', 'Takk', 2005, 1, 1, 180000,"
                    " 'sigur ros', 'hoppipolla', 'takk', :relpath, 'audio/mpeg', :size,"
                    " :digest, 'available', 1, :moment, :moment)"
                ),
                {
                    "id": track_id,
                    "relpath": relative_path,
                    "size": len(content),
                    "digest": hashlib.sha256(content).hexdigest(),
                    "moment": moment,
                },
            )
    finally:
        engine.dispose()
    return track_id


def _schema(document: dict[str, Any], name: str) -> dict[str, Any]:
    schema: dict[str, Any] = document["components"]["schemas"][name]
    return schema


def _cover_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (300, 300), color=(10, 120, 200)).save(buffer, format="PNG")
    return buffer.getvalue()


class TestDocumentedShape:
    def test_the_correction_and_playlist_routes_are_documented(self, client: TestClient) -> None:
        paths = client.get(OPENAPI_PATH).json()["paths"]

        assert "patch" in paths["/api/v1/tracks/{track_id}"]
        assert "get" in paths["/api/v1/tracks/{track_id}"]
        assert "post" in paths["/api/v1/profiles/{profile_id}/playlists"]
        assert "get" in paths["/api/v1/profiles/{profile_id}/playlists"]
        assert "post" in paths["/api/v1/playlists/{playlist_id}/tracks"]
        assert "patch" in paths["/api/v1/playlists/{playlist_id}"]

    def test_the_artwork_stage_routes_are_documented_as_creating_a_stage(
        self, client: TestClient
    ) -> None:
        document = client.get(OPENAPI_PATH).json()

        for path in (
            "/api/v1/artwork/stages/upload",
            "/api/v1/artwork/stages/url",
            "/api/v1/artwork/stages/lastfm",
        ):
            assert "201" in document["paths"][path]["post"]["responses"]

        stage = _schema(document, "ArtworkStageModel")
        assert stage["properties"]["mime_type"]["const"] == "image/jpeg"
        assert "expires_at" in stage["properties"]

    def test_the_edit_request_carries_the_complete_record(self, client: TestClient) -> None:
        request = _schema(client.get(OPENAPI_PATH).json(), "UpdateTrackRequest")

        assert set(request["required"]) == {"title", "artist"}
        for field in ("album", "release_year", "disc_number", "track_number"):
            assert field in request["properties"]
        assert "artwork_stage_id" in request["properties"]

    def test_the_edit_route_documents_its_if_match_header(self, client: TestClient) -> None:
        parameters = client.get(OPENAPI_PATH).json()["paths"]["/api/v1/tracks/{track_id}"]["patch"][
            "parameters"
        ]

        assert any(
            parameter["name"] == "If-Match" and parameter["in"] == "header"
            for parameter in parameters
        )

    def test_the_playlist_shapes_expose_revision_and_track_count(self, client: TestClient) -> None:
        document = client.get(OPENAPI_PATH).json()
        playlist = _schema(document, "PlaylistModel")
        detail = _schema(document, "PlaylistDetailModel")

        assert {"revision", "track_count", "profile_id"} <= set(playlist["properties"])
        assert set(detail["properties"]) == {"playlist", "tracks"}

    def test_no_documented_shape_exposes_a_managed_path(self, client: TestClient) -> None:
        document = client.get(OPENAPI_PATH).json()

        for name in ("TrackDetailModel", "TrackSummaryModel", "ArtworkStageModel"):
            properties = _schema(document, name)["properties"]
            assert not {"file_relpath", "artwork_relpath", "path"} & set(properties)


class TestServedShape:
    def test_lastfm_lookup_stages_cover_and_returns_missing_metadata(
        self, client: TestClient, seeded_track: str
    ) -> None:
        settings = client.get("/api/v1/settings").json()
        lastfm = next(
            provider for provider in settings["providers"] if provider["name"] == "lastfm"
        )
        saved = client.patch(
            "/api/v1/settings/providers/lastfm",
            json={
                "enabled": True,
                "credential": "test-lastfm-key",
                "revision": lastfm["revision"],
            },
        )
        assert saved.status_code == 200

        with respx.mock:
            respx.get("https://ws.audioscrobbler.com/2.0/").mock(
                return_value=httpx.Response(
                    200,
                    json={
                        "track": {
                            "name": "Hoppipolla",
                            "artist": {"name": "Sigur Ros"},
                            "album": {
                                "title": "Takk",
                                "image": [
                                    {"#text": "https://img.invalid/takk.jpg", "size": "large"}
                                ],
                            },
                        }
                    },
                )
            )
            respx.get("https://img.invalid/takk.jpg").mock(
                return_value=httpx.Response(200, content=_cover_bytes())
            )
            response = client.post(
                "/api/v1/artwork/stages/lastfm",
                json={"artist": "Sigur Ros", "title": "Hoppipolla", "album": None},
            )

        assert response.status_code == 201
        body = response.json()
        assert body["stage"]["origin"] == "lastfm"
        assert body["metadata"] == {
            "title": None,
            "artist": None,
            "album": "Takk",
            "duration_ms": None,
        }
        assert seeded_track not in response.text

    def test_patching_a_track_returns_the_documented_detail_shape(
        self, client: TestClient, seeded_track: str
    ) -> None:
        stage_id = client.post(
            "/api/v1/artwork/stages/upload",
            files={"file": ("cover.png", _cover_bytes(), "image/png")},
        ).json()["id"]

        response = client.patch(
            f"/api/v1/tracks/{seeded_track}",
            headers={"If-Match": "1"},
            json={
                "title": "Hoppipolla",
                "artist": "Sigur Ros",
                "album": "Takk",
                "release_year": 2005,
                "disc_number": 1,
                "track_number": 1,
                "artwork_stage_id": stage_id,
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert set(body) == {"track", "has_artwork", "sources"}
        assert body["has_artwork"] is True
        assert body["track"]["revision"] == 2
        assert body["track"]["is_playable"] is True

    def test_creating_a_playlist_returns_the_documented_playlist_shape(
        self, client: TestClient
    ) -> None:
        profile_id = client.post("/api/v1/profiles", json={"name": "Household"}).json()["id"]

        response = client.post(
            f"/api/v1/profiles/{profile_id}/playlists", json={"name": "Sunday Morning"}
        )

        assert response.status_code == 201
        body = response.json()
        assert set(body) == {
            "id",
            "profile_id",
            "name",
            "track_count",
            "revision",
            "created_at",
            "updated_at",
        }
        assert body["profile_id"] == profile_id
        assert body["track_count"] == 0

    def test_a_refused_correction_uses_the_one_error_envelope(
        self, client: TestClient, seeded_track: str
    ) -> None:
        response = client.patch(
            f"/api/v1/tracks/{seeded_track}",
            headers={"If-Match": "9"},
            json={"title": "Hoppipolla", "artist": "Sigur Ros"},
        )

        assert response.status_code == 409
        error = response.json()["error"]
        assert set(error) == {"code", "message", "field", "retryable", "request_id", "detail"}
        assert error["code"] == "record_changed"
