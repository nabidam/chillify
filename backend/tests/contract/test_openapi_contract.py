"""Generated OpenAPI and wire-envelope contract for the system routes.

The app is exercised through its real lifespan against disposable mounted roots,
so the documented shape and the served shape cannot drift apart.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from chillify.domain.normalization import (
    encode_album_key,
    encode_artist_key,
    encode_year_key,
)

pytestmark = pytest.mark.contract

BACKEND_ROOT = Path(__file__).resolve().parents[2]
STATUS_PATH = "/api/v1/system/status"


@pytest.fixture
def client(
    valid_environment: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    for key, value in valid_environment.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("CHILLIFY_FIXTURE_ROOT", raising=False)

    database_path = Path(valid_environment["CHILLIFY_DATA_ROOT"]) / "db" / "chillify.sqlite3"
    database_path.parent.mkdir(parents=True, exist_ok=True)
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database_path}")
    command.upgrade(config, "head")

    from chillify.api.main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client


def _schema_for(document: dict[str, Any], path: str) -> dict[str, Any]:
    reference = document["paths"][path]["get"]["responses"]["200"]["content"]["application/json"][
        "schema"
    ]["$ref"]
    name = reference.rsplit("/", 1)[-1]
    schema: dict[str, Any] = document["components"]["schemas"][name]
    return schema


class TestDocumentedShape:
    def test_system_status_is_documented(self, client: TestClient) -> None:
        document = client.get("/api/v1/openapi.json").json()

        assert STATUS_PATH in document["paths"]
        properties = _schema_for(document, STATUS_PATH)["properties"]
        assert {
            "ready",
            "degraded",
            "environment",
            "checked_at",
            "database",
            "storage",
            "redis",
            "tools",
            "providers",
        } <= set(properties)

    def test_the_library_and_profile_resources_are_documented(self, client: TestClient) -> None:
        paths = client.get("/api/v1/openapi.json").json()["paths"]

        assert "post" in paths["/api/v1/profiles"]
        assert "get" in paths["/api/v1/profiles"]
        assert "get" in paths["/api/v1/library/tracks"]
        assert "get" in paths["/api/v1/tracks/{track_id}/stream"]

    def test_the_playlist_mutation_routes_are_documented(self, client: TestClient) -> None:
        document = client.get("/api/v1/openapi.json").json()
        paths = document["paths"]

        assert "put" in paths["/api/v1/playlists/{playlist_id}/order"]
        assert "delete" in paths["/api/v1/playlists/{playlist_id}/tracks/{track_id}"]
        # The reorder body is the whole order plus the revision that catches a
        # concurrent change before it is applied.
        order_body = paths["/api/v1/playlists/{playlist_id}/order"]["put"]["requestBody"]
        name = order_body["content"]["application/json"]["schema"]["$ref"].rsplit("/", 1)[-1]
        properties = document["components"]["schemas"][name]["properties"]
        assert {"track_ids", "revision"} <= set(properties)

    def test_collections_share_one_page_envelope(self, client: TestClient) -> None:
        document = client.get("/api/v1/openapi.json").json()

        for path in ("/api/v1/profiles", "/api/v1/library/tracks"):
            properties = _schema_for(document, path)["properties"]
            assert {"items", "next_cursor"} <= set(properties)

    def test_the_track_summary_documents_playability_and_context_keys(
        self, client: TestClient
    ) -> None:
        document = client.get("/api/v1/openapi.json").json()

        summary = document["components"]["schemas"]["TrackSummaryModel"]["properties"]
        assert {
            "id",
            "title",
            "artist",
            "album",
            "release_year",
            "duration_ms",
            "artist_key",
            "album_key",
            "availability",
            "is_playable",
            "revision",
        } <= set(summary)
        # A path in a documented response shape would be a path in a real one.
        assert not {"file_relpath", "artwork_relpath", "content_sha256"} & set(summary)

    def test_the_stream_route_documents_its_audio_responses(self, client: TestClient) -> None:
        document = client.get("/api/v1/openapi.json").json()

        responses = document["paths"]["/api/v1/tracks/{track_id}/stream"]["get"]["responses"]
        assert "audio/mpeg" in responses["200"]["content"]
        assert "audio/mpeg" in responses["206"]["content"]

    def test_error_envelope_is_documented(self, client: TestClient) -> None:
        document = client.get("/api/v1/openapi.json").json()

        error = document["components"]["schemas"]["ErrorBody"]["properties"]
        assert {"code", "message", "field", "retryable", "request_id", "detail"} <= set(error)


class TestServedShape:
    def test_status_reports_readiness_and_degradation_separately(self, client: TestClient) -> None:
        response = client.get(STATUS_PATH)

        assert response.status_code == 200
        body = response.json()
        # A migrated database on writable roots is ready even when Redis and the
        # external tools are absent from this environment.
        assert body["ready"] is True
        assert isinstance(body["degraded"], bool)
        assert body["database"]["health"] == "ok"
        assert body["environment"] == "production"

    def test_status_enumerates_the_seeded_providers(self, client: TestClient) -> None:
        body = client.get(STATUS_PATH).json()

        providers = {provider["name"]: provider for provider in body["providers"]}
        assert set(providers) == {"deezer", "spotdl", "yt_dlp", "lastfm"}
        assert providers["deezer"]["enabled"] is True
        assert providers["lastfm"]["enabled"] is False

    def test_status_names_both_mounted_roots(self, client: TestClient) -> None:
        body = client.get(STATUS_PATH).json()

        assert {item["name"] for item in body["storage"]} == {"data_root", "music_root"}

    def test_unreachable_redis_degrades_without_failing_readiness(self, client: TestClient) -> None:
        body = client.get(STATUS_PATH).json()

        # The test environment has no Redis on database 9 of the default host.
        if body["redis"]["health"] != "ok":
            assert body["degraded"] is True
            assert body["ready"] is True

    def test_health_probe_reports_ready(self, client: TestClient) -> None:
        response = client.get("/api/v1/system/health")

        assert response.status_code == 200
        assert response.json() == {"status": "ready"}

    def test_missing_route_returns_the_documented_error_envelope(self, client: TestClient) -> None:
        response = client.get("/api/v1/system/does-not-exist")

        assert response.status_code == 404
        error = response.json()["error"]
        assert error["code"] == "not_found"
        assert error["retryable"] is False
        assert error["field"] is None
        assert error["detail"] == {}
        assert error["request_id"]

    def test_every_response_carries_its_request_id(self, client: TestClient) -> None:
        response = client.get(STATUS_PATH)

        assert response.headers["X-Request-ID"]

    def test_no_permissive_cors_policy_is_advertised(self, client: TestClient) -> None:
        response = client.get(STATUS_PATH, headers={"Origin": "http://attacker.invalid"})

        assert "access-control-allow-origin" not in {key.lower() for key in response.headers}


# The identity fields each detail context wraps around its ordered track array.
_CONTEXT_DETAILS = {
    "/api/v1/library/artists/{artist_key}": {"artist_key", "artist", "track_count", "tracks"},
    "/api/v1/library/albums/{album_key}": {"album_key", "album", "artist", "track_count", "tracks"},
    "/api/v1/library/years/{year_key}": {"year_key", "release_year", "track_count", "tracks"},
}


class TestContextEndpoints:
    def test_every_context_endpoint_is_documented(self, client: TestClient) -> None:
        paths = client.get("/api/v1/openapi.json").json()["paths"]

        for path in (
            "/api/v1/library/artists",
            "/api/v1/library/albums",
            "/api/v1/library/years",
            *_CONTEXT_DETAILS,
        ):
            assert "get" in paths[path]

    def test_each_detail_context_documents_an_ordered_track_array(self, client: TestClient) -> None:
        document = client.get("/api/v1/openapi.json").json()

        for path, identity in _CONTEXT_DETAILS.items():
            schema = _schema_for(document, path)
            assert identity <= set(schema["properties"])
            tracks = schema["properties"]["tracks"]
            assert tracks["type"] == "array"
            reference = tracks["items"]["$ref"].rsplit("/", 1)[-1]
            assert reference == "TrackSummaryModel"

    def test_each_detail_context_serves_a_track_array(self, client: TestClient) -> None:
        # An empty library still answers with the documented array shape rather
        # than a 404, which is what lets S6/S7/S8 render an empty context.
        cases = {
            "/api/v1/library/artists/": encode_artist_key("nobody"),
            "/api/v1/library/albums/": encode_album_key("nobody", "nothing"),
            "/api/v1/library/years/": encode_year_key(None),
        }
        for prefix, key in cases.items():
            body = client.get(f"{prefix}{key}").json()
            assert body["tracks"] == []
            assert body["track_count"] == 0
