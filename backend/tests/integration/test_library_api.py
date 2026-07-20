"""Profiles, the local library, and track streaming against real SQLite and files.

Every claim here is durable-state behavior: what a household still has after
Compose restarts, and what the browser's `<audio>` element actually receives.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from chillify.domain.models import to_rfc3339
from chillify.infrastructure.db.engine import create_database_engine
from chillify.infrastructure.db.repositories import new_id

pytestmark = pytest.mark.integration

PROFILES_PATH = "/api/v1/profiles"
TRACKS_PATH = "/api/v1/library/tracks"

# 32 KiB of deterministic bytes behind a real MPEG frame header. The stream
# route never decodes audio, so byte-exactness is what matters here, not
# decodability — and deterministic bytes make range assertions exact.
AUDIO_BYTES = b"\xff\xfb\x90\x64" + bytes(range(256)) * 128


@pytest.fixture
def seed_track(migrated_environment: dict[str, str]) -> Iterator[Callable[..., str]]:
    """Insert one track row and write its managed file, as the worker would."""
    data_root = Path(migrated_environment["CHILLIFY_DATA_ROOT"])
    music_root = Path(migrated_environment["CHILLIFY_MUSIC_ROOT"])
    engine = create_database_engine(data_root / "db" / "chillify.sqlite3")

    def seed(
        *,
        title: str = "Hoppipolla",
        artist: str = "Sigur Rós",
        album: str | None = "Takk...",
        normalized_artist: str = "sigur ros",
        normalized_title: str = "hoppipolla",
        normalized_album: str = "takk",
        release_year: int | None = 2005,
        created_at: datetime | None = None,
        content: bytes = AUDIO_BYTES,
        write_file: bool = True,
    ) -> str:
        track_id = new_id()
        relative_path = f"Music/{normalized_artist}/{normalized_album}/{track_id}.mp3"
        absolute_path = music_root / relative_path
        if write_file:
            absolute_path.parent.mkdir(parents=True, exist_ok=True)
            absolute_path.write_bytes(content)

        moment = to_rfc3339(created_at or datetime.now(UTC))
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO tracks (id, title, artist, album, release_year, disc_number,"
                    " track_number, duration_ms, normalized_artist, normalized_title,"
                    " normalized_album, file_relpath, mime_type, file_size_bytes,"
                    " content_sha256, availability, revision, created_at, updated_at)"
                    " VALUES (:id, :title, :artist, :album, :year, 1, 1, 180000,"
                    " :normalized_artist, :normalized_title, :normalized_album, :relpath,"
                    " 'audio/mpeg', :size, :digest, 'available', 1, :moment, :moment)"
                ),
                {
                    "id": track_id,
                    "title": title,
                    "artist": artist,
                    "album": album,
                    "year": release_year,
                    "normalized_artist": normalized_artist,
                    "normalized_title": normalized_title,
                    "normalized_album": normalized_album,
                    "relpath": relative_path,
                    "size": len(content),
                    "digest": hashlib.sha256(content).hexdigest(),
                    "moment": moment,
                },
            )
        return track_id

    yield seed
    engine.dispose()


@pytest.fixture
def client(start_api: Callable[[], TestClient]) -> TestClient:
    return start_api()


class TestProfiles:
    def test_a_created_profile_is_listed(self, client: TestClient) -> None:
        created = client.post(PROFILES_PATH, json={"name": "Household"})

        assert created.status_code == 201
        listed = client.get(PROFILES_PATH).json()
        assert [profile["name"] for profile in listed["items"]] == ["Household"]
        assert listed["next_cursor"] is None

    def test_a_duplicate_name_is_reported_as_a_conflict_on_the_name_field(
        self, client: TestClient
    ) -> None:
        client.post(PROFILES_PATH, json={"name": "Household"})

        response = client.post(PROFILES_PATH, json={"name": "  HOUSEHOLD "})

        assert response.status_code == 409
        error = response.json()["error"]
        assert error["code"] == "duplicate_record"
        assert error["field"] == "name"

    def test_a_blank_name_is_refused_before_any_row_is_written(self, client: TestClient) -> None:
        response = client.post(PROFILES_PATH, json={"name": "   "})

        assert response.status_code == 422
        assert client.get(PROFILES_PATH).json()["items"] == []

    def test_a_profile_survives_an_api_restart(
        self, client: TestClient, start_api: Callable[[], TestClient]
    ) -> None:
        client.post(PROFILES_PATH, json={"name": "Household"})

        restarted = start_api()

        assert [profile["name"] for profile in restarted.get(PROFILES_PATH).json()["items"]] == [
            "Household"
        ]


class TestLibraryListing:
    def test_a_seeded_track_is_listed_with_its_derived_context_keys(
        self, client: TestClient, seed_track: Callable[..., str]
    ) -> None:
        track_id = seed_track()

        items = client.get(TRACKS_PATH).json()["items"]

        assert len(items) == 1
        assert items[0]["id"] == track_id
        assert items[0]["title"] == "Hoppipolla"
        assert items[0]["is_playable"] is True
        assert items[0]["artist_key"] and items[0]["album_key"]

    def test_a_track_survives_an_api_restart(
        self,
        client: TestClient,
        seed_track: Callable[..., str],
        start_api: Callable[[], TestClient],
    ) -> None:
        track_id = seed_track()

        restarted = start_api()

        assert [item["id"] for item in restarted.get(TRACKS_PATH).json()["items"]] == [track_id]

    def test_search_matches_the_normalized_columns(
        self, client: TestClient, seed_track: Callable[..., str]
    ) -> None:
        seed_track()

        assert len(client.get(TRACKS_PATH, params={"q": "Sigur Rós"}).json()["items"]) == 1
        assert len(client.get(TRACKS_PATH, params={"q": "sigur ros"}).json()["items"]) == 1
        assert client.get(TRACKS_PATH, params={"q": "nothing here"}).json()["items"] == []

    def test_the_default_sort_is_newest_first(
        self, client: TestClient, seed_track: Callable[..., str]
    ) -> None:
        older = seed_track(normalized_title="older", created_at=datetime(2026, 1, 1, tzinfo=UTC))
        newer = seed_track(normalized_title="newer", created_at=datetime(2026, 6, 1, tzinfo=UTC))

        assert [item["id"] for item in client.get(TRACKS_PATH).json()["items"]] == [newer, older]

    def test_a_page_cursor_walks_the_whole_library_without_repeating_a_row(
        self, client: TestClient, seed_track: Callable[..., str]
    ) -> None:
        expected = {
            seed_track(
                normalized_title=f"title {index}",
                created_at=datetime(2026, 1, 1 + index, tzinfo=UTC),
            )
            for index in range(5)
        }

        seen: list[str] = []
        cursor: str | None = None
        for _ in range(5):
            params = {"limit": 2} | ({"cursor": cursor} if cursor else {})
            page = client.get(TRACKS_PATH, params=params).json()
            seen.extend(item["id"] for item in page["items"])
            cursor = page["next_cursor"]
            if cursor is None:
                break

        assert cursor is None
        assert len(seen) == len(set(seen))
        assert set(seen) == expected

    def test_a_cursor_issued_for_another_sort_is_refused(
        self, client: TestClient, seed_track: Callable[..., str]
    ) -> None:
        seed_track()
        seed_track(normalized_title="second")
        cursor = client.get(TRACKS_PATH, params={"limit": 1}).json()["next_cursor"]

        response = client.get(TRACKS_PATH, params={"limit": 1, "sort": "title", "cursor": cursor})

        assert response.status_code == 422
        assert response.json()["error"]["field"] == "cursor"


class TestTrackStream:
    def _stream_path(self, track_id: str) -> str:
        return f"/api/v1/tracks/{track_id}/stream"

    def test_a_full_request_serves_the_whole_file(
        self, client: TestClient, seed_track: Callable[..., str]
    ) -> None:
        response = client.get(self._stream_path(seed_track()))

        assert response.status_code == 200
        assert response.content == AUDIO_BYTES
        assert response.headers["content-type"] == "audio/mpeg"
        assert response.headers["accept-ranges"] == "bytes"
        assert response.headers["etag"]

    def test_a_byte_range_serves_exactly_that_range(
        self, client: TestClient, seed_track: Callable[..., str]
    ) -> None:
        response = client.get(self._stream_path(seed_track()), headers={"Range": "bytes=100-199"})

        assert response.status_code == 206
        assert response.content == AUDIO_BYTES[100:200]
        assert response.headers["content-length"] == "100"
        assert response.headers["content-range"] == f"bytes 100-199/{len(AUDIO_BYTES)}"

    def test_a_suffix_range_serves_the_tail(
        self, client: TestClient, seed_track: Callable[..., str]
    ) -> None:
        response = client.get(self._stream_path(seed_track()), headers={"Range": "bytes=-64"})

        assert response.status_code == 206
        assert response.content == AUDIO_BYTES[-64:]

    def test_a_range_beyond_the_file_is_unsatisfiable(
        self, client: TestClient, seed_track: Callable[..., str]
    ) -> None:
        response = client.get(
            self._stream_path(seed_track()), headers={"Range": "bytes=999999-1000000"}
        )

        assert response.status_code == 416

    def test_the_etag_changes_when_the_file_does(
        self, client: TestClient, seed_track: Callable[..., str]
    ) -> None:
        first = client.get(self._stream_path(seed_track()))
        second = client.get(
            self._stream_path(seed_track(normalized_title="longer", content=AUDIO_BYTES + b"tail"))
        )

        assert first.headers["etag"] != second.headers["etag"]

    def test_an_unknown_track_is_not_found(self, client: TestClient) -> None:
        response = client.get(self._stream_path(new_id()))

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "record_not_found"

    def test_a_vanished_file_marks_the_track_missing_and_reports_gone(
        self, client: TestClient, seed_track: Callable[..., str]
    ) -> None:
        track_id = seed_track(write_file=False)

        response = client.get(self._stream_path(track_id))

        assert response.status_code == 410
        assert response.json()["error"]["code"] == "track_file_missing"
        listed = client.get(TRACKS_PATH).json()["items"][0]
        assert listed["availability"] == "missing"
        assert listed["is_playable"] is False

    def test_a_stream_failure_never_discloses_a_path(
        self, client: TestClient, seed_track: Callable[..., str]
    ) -> None:
        body = client.get(self._stream_path(seed_track(write_file=False))).text

        assert "/" not in body.replace("\\/", "")
