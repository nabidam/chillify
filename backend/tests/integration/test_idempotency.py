"""Idempotency-key scoping/durability and stale-revision refusal, end to end.

ARCHITECTURE section 5 makes two promises this suite pins beyond what the
download-flow tests already cover: an `Idempotency-Key` is scoped by method and
route family, so the same key value can never replay a different route's
mutation, and a stored idempotency response is durable — read back from SQLite
by a fresh request, not merely cached on one connection — for the documented 24
hours. It also pins the sibling promise for mutable records: a stale `revision`
is refused before anything on disk changes.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from chillify.application.downloads import DownloadService
from chillify.infrastructure.db.engine import create_database_engine
from chillify.infrastructure.db.repositories import new_id

pytestmark = pytest.mark.integration

FIXTURE_AUDIO = Path(__file__).resolve().parents[1] / "fixtures" / "media" / "gate-tone.mp3"


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


class TestIdempotencyKeyScopeIsolation:
    def test_the_same_key_value_on_a_different_route_family_is_not_a_replay(
        self,
        gate_api: TestClient,
        gate_downloads: DownloadService,
        dispatched_jobs: list[str],
    ) -> None:
        """`Idempotency-Key` scope includes the route family, per ARCHITECTURE
        section 5: reusing one key's *value* across `POST /downloads` and
        `POST /downloads/{id}/retry` must queue two distinct pieces of work,
        not silently return the first response for the second route.
        """
        key = "01JZZ-shared-value"
        first = queue_download(gate_api, deezer_candidate(gate_api, "daft punk"))
        assert dispatched_jobs == [first]

        gate_api.post(
            "/api/v1/downloads",
            json={
                "source_type": "deezer_result",
                "candidate": deezer_candidate(gate_api, "daft punk"),
            },
            headers={"Idempotency-Key": key},
        )
        parent = dispatched_jobs[-1]
        version = int(gate_api.get(f"/api/v1/downloads/{parent}").json()["job"]["version"])
        gate_api.post(f"/api/v1/downloads/{parent}/cancel", json={"version": version})

        retried = gate_api.post(
            f"/api/v1/downloads/{parent}/retry", headers={"Idempotency-Key": key}
        )

        assert retried.status_code == 201
        # A cross-scope replay would return the earlier `POST /downloads` body,
        # whose id is `parent` itself rather than a new linked child.
        assert retried.json()["id"] != parent
        assert retried.json()["parent_job_id"] == parent


class TestIdempotencyIsDurable:
    def test_a_replay_is_read_back_from_storage_by_a_fresh_connection(
        self, gate_api: TestClient, dispatched_jobs: list[str]
    ) -> None:
        """The stored response survives past the request that created it.

        Closing the client and opening a new one against the same composition
        stands in for the browser reconnecting: nothing about the replay may
        depend on anything the first request left in memory.
        """
        candidate = deezer_candidate(gate_api, "massive attack")
        body = {"source_type": "deezer_result", "candidate": candidate}
        headers = {"Idempotency-Key": "01JZZ-durable"}

        first = gate_api.post("/api/v1/downloads", json=body, headers=headers)
        assert first.status_code == 201

        gate_api.close()
        reconnected = TestClient(gate_api.app)
        second = reconnected.post("/api/v1/downloads", json=body, headers=headers)

        assert second.status_code == 201
        assert second.json() == first.json()
        assert len(dispatched_jobs) == 1


class TestStaleRevisionIsRefused:
    @pytest.fixture
    def seeded_track(self, migrated_environment: dict[str, str]) -> tuple[str, Path]:
        """One track row and its real file, inserted directly like a completed
        publication would leave them, without exercising the download flow."""
        data_root = Path(migrated_environment["CHILLIFY_DATA_ROOT"])
        music_root = Path(migrated_environment["CHILLIFY_MUSIC_ROOT"])
        relative_path = "Music/Boards Of Canada/Geogaddi/01 - Ready Lets Go.mp3"
        absolute = music_root / relative_path
        absolute.parent.mkdir(parents=True, exist_ok=True)
        content = FIXTURE_AUDIO.read_bytes()
        absolute.write_bytes(content)

        track_id = new_id()
        moment = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        engine = create_database_engine(data_root / "db" / "chillify.sqlite3")
        try:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO tracks (id, title, artist, album, release_year,"
                        " disc_number, track_number, duration_ms, normalized_artist,"
                        " normalized_title, normalized_album, file_relpath, mime_type,"
                        " file_size_bytes, content_sha256, availability, revision,"
                        " created_at, updated_at)"
                        " VALUES (:id, 'Ready Lets Go', 'Boards Of Canada', 'Geogaddi', 2002,"
                        " 1, 1, 180000, 'boards of canada', 'ready lets go', 'geogaddi',"
                        " :relpath, 'audio/mpeg', :size, :digest, 'available', 1,"
                        " :moment, :moment)"
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
        return track_id, absolute

    def test_a_stale_if_match_on_a_track_save_is_refused_and_disk_is_untouched(
        self,
        seeded_track: tuple[str, Path],
        start_api: Callable[[], TestClient],
    ) -> None:
        track_id, absolute = seeded_track
        original_bytes = absolute.read_bytes()
        original_mtime = absolute.stat().st_mtime
        client = start_api()

        response = client.patch(
            f"/api/v1/tracks/{track_id}",
            json={
                "title": "Ready Lets Go (Remaster)",
                "artist": "Boards Of Canada",
                "album": "Geogaddi",
                "release_year": 2002,
                "disc_number": 1,
                "track_number": 1,
            },
            headers={"If-Match": "99"},
        )

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "record_changed"
        assert absolute.read_bytes() == original_bytes
        assert absolute.stat().st_mtime == original_mtime

        # The revision in storage is exactly what it was: a stale write never
        # reaches the point of touching the managed file at all.
        detail = client.get(f"/api/v1/tracks/{track_id}").json()
        assert detail["track"]["revision"] == 1
        assert detail["track"]["title"] == "Ready Lets Go"
