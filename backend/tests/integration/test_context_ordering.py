"""Artist, album, and year browse contexts against real SQLite.

Every claim here is the exact order playback will use: the detail endpoints
return their tracks already sorted, so what the browser renders and what it
queues are the same list. Unknown disc, track, and year values are ordering
facts, not error cases, so they are asserted explicitly.
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
from chillify.domain.normalization import (
    encode_album_key,
    encode_artist_key,
    encode_year_key,
    normalize_album,
    normalize_artist,
    normalize_title,
)
from chillify.infrastructure.db.engine import create_database_engine
from chillify.infrastructure.db.repositories import new_id

pytestmark = pytest.mark.integration

AUDIO_BYTES = b"\xff\xfb\x90\x64" + bytes(range(64))


@pytest.fixture
def seed_track(migrated_environment: dict[str, str]) -> Iterator[Callable[..., str]]:
    """Insert one fully controllable track row and write its managed file."""
    data_root = Path(migrated_environment["CHILLIFY_DATA_ROOT"])
    music_root = Path(migrated_environment["CHILLIFY_MUSIC_ROOT"])
    engine = create_database_engine(data_root / "db" / "chillify.sqlite3")

    def seed(
        *,
        title: str,
        artist: str,
        album: str | None,
        release_year: int | None,
        disc_number: int | None = 1,
        track_number: int | None = 1,
    ) -> str:
        track_id = new_id()
        normalized_artist = normalize_artist(artist)
        normalized_album = normalize_album(album)
        relative_path = f"Music/{normalized_artist}/{normalized_album}/{track_id}.mp3"
        absolute_path = music_root / relative_path
        absolute_path.parent.mkdir(parents=True, exist_ok=True)
        absolute_path.write_bytes(AUDIO_BYTES)

        moment = to_rfc3339(datetime.now(UTC))
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO tracks (id, title, artist, album, release_year, disc_number,"
                    " track_number, duration_ms, normalized_artist, normalized_title,"
                    " normalized_album, file_relpath, mime_type, file_size_bytes,"
                    " content_sha256, availability, revision, created_at, updated_at)"
                    " VALUES (:id, :title, :artist, :album, :year, :disc, :track, 180000,"
                    " :normalized_artist, :normalized_title, :normalized_album, :relpath,"
                    " 'audio/mpeg', :size, :digest, 'available', 1, :moment, :moment)"
                ),
                {
                    "id": track_id,
                    "title": title,
                    "artist": artist,
                    "album": album,
                    "year": release_year,
                    "disc": disc_number,
                    "track": track_number,
                    "normalized_artist": normalized_artist,
                    "normalized_title": normalize_title(title),
                    "normalized_album": normalized_album,
                    "relpath": relative_path,
                    "size": len(AUDIO_BYTES),
                    "digest": hashlib.sha256(AUDIO_BYTES).hexdigest(),
                    "moment": moment,
                },
            )
        return track_id

    yield seed
    engine.dispose()


@pytest.fixture
def client(start_api: Callable[[], TestClient]) -> TestClient:
    return start_api()


def _titles(response_json: dict) -> list[str]:
    return [track["title"] for track in response_json["tracks"]]


class TestArtistContext:
    def test_tracks_order_by_year_then_album_then_disc_track_with_unknown_year_last(
        self, client: TestClient, seed_track: Callable[..., str]
    ) -> None:
        # Seeded out of order; the endpoint is what must sort them.
        seed_track(title="No Year", artist="Sigur Ros", album="Odds", release_year=None)
        seed_track(
            title="Takk Two", artist="Sigur Ros", album="Takk", release_year=2005, track_number=2
        )
        seed_track(
            title="Takk One", artist="Sigur Ros", album="Takk", release_year=2005, track_number=1
        )
        seed_track(title="Agaetis", artist="Sigur Ros", album="Agaetis", release_year=2000)

        key = encode_artist_key(normalize_artist("Sigur Ros"))
        response = client.get(f"/api/v1/library/artists/{key}")

        assert response.status_code == 200
        body = response.json()
        assert body["artist_key"] == key
        assert body["track_count"] == 4
        # 2000 first, then the 2005 album in track order, then the unknown-year
        # track last regardless of its album name.
        assert _titles(body) == ["Agaetis", "Takk One", "Takk Two", "No Year"]

    def test_a_canonical_key_with_no_tracks_is_an_empty_context_not_an_error(
        self, client: TestClient
    ) -> None:
        key = encode_artist_key(normalize_artist("Nobody"))
        response = client.get(f"/api/v1/library/artists/{key}")

        assert response.status_code == 200
        assert response.json()["tracks"] == []

    def test_a_noncanonical_key_is_rejected(self, client: TestClient) -> None:
        assert client.get("/api/v1/library/artists/not-a-key!").status_code == 422


class TestAlbumContext:
    def test_tracks_order_by_disc_then_track_with_unknown_last(
        self, client: TestClient, seed_track: Callable[..., str]
    ) -> None:
        seed_track(
            title="Loose", artist="Band", album="Record", release_year=2010, track_number=None
        )
        seed_track(
            title="Two",
            artist="Band",
            album="Record",
            release_year=2010,
            disc_number=1,
            track_number=2,
        )
        seed_track(
            title="Disc Two",
            artist="Band",
            album="Record",
            release_year=2010,
            disc_number=2,
            track_number=1,
        )
        seed_track(
            title="One",
            artist="Band",
            album="Record",
            release_year=2010,
            disc_number=1,
            track_number=1,
        )

        key = encode_album_key(normalize_artist("Band"), normalize_album("Record"))
        body = client.get(f"/api/v1/library/albums/{key}").json()

        assert body["album"] == "Record"
        assert body["artist"] == "Band"
        # disc1/track1, disc1/track2, disc1's missing-track row, then disc2:
        # an unknown track sorts last within its own disc, not after every disc.
        assert _titles(body) == ["One", "Two", "Loose", "Disc Two"]

    def test_same_named_albums_by_different_artists_stay_separate(
        self, client: TestClient, seed_track: Callable[..., str]
    ) -> None:
        seed_track(title="Alpha", artist="Artist One", album="Greatest Hits", release_year=1999)
        seed_track(title="Beta", artist="Artist Two", album="Greatest Hits", release_year=1999)

        one = encode_album_key(normalize_artist("Artist One"), normalize_album("Greatest Hits"))
        two = encode_album_key(normalize_artist("Artist Two"), normalize_album("Greatest Hits"))

        assert one != two
        assert _titles(client.get(f"/api/v1/library/albums/{one}").json()) == ["Alpha"]
        assert _titles(client.get(f"/api/v1/library/albums/{two}").json()) == ["Beta"]

    def test_an_absent_album_is_the_unknown_album_context(
        self, client: TestClient, seed_track: Callable[..., str]
    ) -> None:
        seed_track(title="Orphan", artist="Solo", album=None, release_year=2001)

        key = encode_album_key(normalize_artist("Solo"), normalize_album(None))
        body = client.get(f"/api/v1/library/albums/{key}").json()

        assert body["album"] is None
        assert _titles(body) == ["Orphan"]


class TestYearContext:
    def test_tracks_order_by_artist_then_album_then_disc_track(
        self, client: TestClient, seed_track: Callable[..., str]
    ) -> None:
        seed_track(title="Zed Song", artist="Zed", album="Z", release_year=1990)
        seed_track(title="Abe Two", artist="Abe", album="A", release_year=1990, track_number=2)
        seed_track(title="Abe One", artist="Abe", album="A", release_year=1990, track_number=1)

        key = encode_year_key(1990)
        body = client.get(f"/api/v1/library/years/{key}").json()

        assert body["release_year"] == 1990
        assert _titles(body) == ["Abe One", "Abe Two", "Zed Song"]

    def test_unknown_year_is_a_first_class_context(
        self, client: TestClient, seed_track: Callable[..., str]
    ) -> None:
        seed_track(title="Undated", artist="Someone", album="Demo", release_year=None)

        body = client.get(f"/api/v1/library/years/{encode_year_key(None)}").json()

        assert body["year_key"] == "unknown"
        assert body["release_year"] is None
        assert _titles(body) == ["Undated"]


class TestCollections:
    def test_years_list_places_unknown_last_and_counts_each_grouping(
        self, client: TestClient, seed_track: Callable[..., str]
    ) -> None:
        seed_track(title="A", artist="X", album="One", release_year=2000)
        seed_track(title="B", artist="X", album="One", release_year=2000, track_number=2)
        seed_track(title="C", artist="X", album="Two", release_year=None)

        items = client.get("/api/v1/library/years").json()["items"]

        assert [item["release_year"] for item in items] == [2000, None]
        assert [item["track_count"] for item in items] == [2, 1]

    def test_artists_list_is_ordered_and_search_narrows_it(
        self, client: TestClient, seed_track: Callable[..., str]
    ) -> None:
        seed_track(title="A", artist="Björk", album="Post", release_year=1995)
        seed_track(title="B", artist="Aphex Twin", album="RDJ", release_year=1996)

        all_items = client.get("/api/v1/library/artists").json()["items"]
        assert [item["artist"] for item in all_items] == ["Aphex Twin", "Björk"]

        # Search folds accents against the stored normalized column.
        narrowed = client.get("/api/v1/library/artists", params={"q": "bjork"}).json()["items"]
        assert [item["artist"] for item in narrowed] == ["Björk"]
