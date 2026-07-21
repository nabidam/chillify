"""Playlists against real SQLite: ownership, uniqueness, and saved order.

A playlist is the one thing in Chillify that belongs to a profile rather than
the household, so most of what is asserted here is about which profile a
playlist is visible from and what two people pressing the same button produce.
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
AUDIO_BYTES = b"\xff\xfb\x90\x64" + bytes(range(256)) * 16


@pytest.fixture
def seed_track(migrated_environment: dict[str, str]) -> Iterator[Callable[..., str]]:
    data_root = Path(migrated_environment["CHILLIFY_DATA_ROOT"])
    music_root = Path(migrated_environment["CHILLIFY_MUSIC_ROOT"])
    engine = create_database_engine(data_root / "db" / "chillify.sqlite3")

    def seed(*, title: str = "Hoppipolla", artist: str = "Sigur Ros") -> str:
        track_id = new_id()
        relative_path = f"Music/{artist}/Takk/{track_id}.mp3"
        absolute = music_root / relative_path
        absolute.parent.mkdir(parents=True, exist_ok=True)
        absolute.write_bytes(AUDIO_BYTES)

        moment = to_rfc3339(datetime.now(UTC))
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO tracks (id, title, artist, album, release_year, disc_number,"
                    " track_number, duration_ms, normalized_artist, normalized_title,"
                    " normalized_album, file_relpath, mime_type, file_size_bytes,"
                    " content_sha256, availability, revision, created_at, updated_at)"
                    " VALUES (:id, :title, :artist, 'Takk', 2005, 1, 1, 180000,"
                    " :normalized_artist, :normalized_title, 'takk', :relpath,"
                    " 'audio/mpeg', :size, :digest, 'available', 1, :moment, :moment)"
                ),
                {
                    "id": track_id,
                    "title": title,
                    "artist": artist,
                    "normalized_artist": artist.casefold(),
                    "normalized_title": title.casefold(),
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


@pytest.fixture
def profile_id(client: TestClient) -> str:
    return str(client.post(PROFILES_PATH, json={"name": "Household"}).json()["id"])


def _playlists_path(profile_id: str) -> str:
    return f"/api/v1/profiles/{profile_id}/playlists"


class TestPlaylistCreation:
    def test_a_created_playlist_is_listed_for_its_profile(
        self, client: TestClient, profile_id: str
    ) -> None:
        created = client.post(_playlists_path(profile_id), json={"name": "Sunday Morning"})

        assert created.status_code == 201
        assert created.json()["track_count"] == 0
        assert created.json()["revision"] == 1

        listed = client.get(_playlists_path(profile_id)).json()
        assert [item["name"] for item in listed["items"]] == ["Sunday Morning"]

    def test_a_duplicate_name_within_one_profile_is_a_conflict_on_the_name_field(
        self, client: TestClient, profile_id: str
    ) -> None:
        client.post(_playlists_path(profile_id), json={"name": "Sunday Morning"})

        again = client.post(_playlists_path(profile_id), json={"name": "sunday   morning"})

        assert again.status_code == 409
        assert again.json()["error"]["code"] == "duplicate_record"
        assert again.json()["error"]["field"] == "name"

    def test_two_profiles_may_each_hold_the_same_playlist_name(
        self, client: TestClient, profile_id: str
    ) -> None:
        other = client.post(PROFILES_PATH, json={"name": "Guest"}).json()["id"]

        first = client.post(_playlists_path(profile_id), json={"name": "Sunday Morning"})
        second = client.post(_playlists_path(other), json={"name": "Sunday Morning"})

        assert first.status_code == 201
        assert second.status_code == 201
        assert [item["name"] for item in client.get(_playlists_path(other)).json()["items"]] == [
            "Sunday Morning"
        ]

    def test_one_profile_never_sees_another_profile_s_playlists(
        self, client: TestClient, profile_id: str
    ) -> None:
        other = client.post(PROFILES_PATH, json={"name": "Guest"}).json()["id"]
        client.post(_playlists_path(profile_id), json={"name": "Sunday Morning"})

        assert client.get(_playlists_path(other)).json()["items"] == []

    def test_a_blank_name_is_reported_on_its_own_field(
        self, client: TestClient, profile_id: str
    ) -> None:
        response = client.post(_playlists_path(profile_id), json={"name": "   "})

        assert response.status_code == 422
        assert response.json()["error"]["field"] == "name"

    def test_an_unknown_profile_cannot_hold_a_playlist(self, client: TestClient) -> None:
        response = client.post(_playlists_path(new_id()), json={"name": "Sunday Morning"})

        assert response.status_code == 404


class TestPlaylistTracks:
    def test_added_tracks_keep_the_order_they_were_added_in(
        self, client: TestClient, profile_id: str, seed_track: Callable[..., str]
    ) -> None:
        playlist = client.post(_playlists_path(profile_id), json={"name": "Sunday"}).json()
        first = seed_track(title="Hoppipolla")
        second = seed_track(title="Glosoli")

        after_first = client.post(
            f"/api/v1/playlists/{playlist['id']}/tracks",
            json={"track_id": first, "revision": playlist["revision"]},
        ).json()
        after_second = client.post(
            f"/api/v1/playlists/{playlist['id']}/tracks",
            json={"track_id": second, "revision": after_first["playlist"]["revision"]},
        ).json()

        assert [track["id"] for track in after_second["tracks"]] == [first, second]
        assert after_second["playlist"]["track_count"] == 2

    def test_the_same_track_cannot_appear_twice_in_one_playlist(
        self, client: TestClient, profile_id: str, seed_track: Callable[..., str]
    ) -> None:
        playlist = client.post(_playlists_path(profile_id), json={"name": "Sunday"}).json()
        track_id = seed_track()
        added = client.post(
            f"/api/v1/playlists/{playlist['id']}/tracks",
            json={"track_id": track_id, "revision": playlist["revision"]},
        ).json()

        again = client.post(
            f"/api/v1/playlists/{playlist['id']}/tracks",
            json={"track_id": track_id, "revision": added["playlist"]["revision"]},
        )

        assert again.status_code == 409
        assert again.json()["error"]["field"] == "track_id"

    def test_one_track_may_belong_to_two_playlists(
        self, client: TestClient, profile_id: str, seed_track: Callable[..., str]
    ) -> None:
        track_id = seed_track()
        first = client.post(_playlists_path(profile_id), json={"name": "Sunday"}).json()
        second = client.post(_playlists_path(profile_id), json={"name": "Monday"}).json()

        for playlist in (first, second):
            response = client.post(
                f"/api/v1/playlists/{playlist['id']}/tracks",
                json={"track_id": track_id, "revision": playlist["revision"]},
            )
            assert response.status_code == 200

    def test_a_stale_revision_is_refused_and_the_playlist_is_unchanged(
        self, client: TestClient, profile_id: str, seed_track: Callable[..., str]
    ) -> None:
        playlist = client.post(_playlists_path(profile_id), json={"name": "Sunday"}).json()
        track_id = seed_track()

        response = client.post(
            f"/api/v1/playlists/{playlist['id']}/tracks",
            json={"track_id": track_id, "revision": 99},
        )

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "record_changed"
        assert client.get(f"/api/v1/playlists/{playlist['id']}").json()["tracks"] == []

    def test_a_track_that_is_not_in_the_library_cannot_be_added(
        self, client: TestClient, profile_id: str
    ) -> None:
        playlist = client.post(_playlists_path(profile_id), json={"name": "Sunday"}).json()

        response = client.post(
            f"/api/v1/playlists/{playlist['id']}/tracks",
            json={"track_id": new_id(), "revision": playlist["revision"]},
        )

        assert response.status_code == 404

    def test_the_detail_carries_playable_track_summaries(
        self, client: TestClient, profile_id: str, seed_track: Callable[..., str]
    ) -> None:
        playlist = client.post(_playlists_path(profile_id), json={"name": "Sunday"}).json()
        track_id = seed_track()
        client.post(
            f"/api/v1/playlists/{playlist['id']}/tracks",
            json={"track_id": track_id, "revision": playlist["revision"]},
        )

        detail = client.get(f"/api/v1/playlists/{playlist['id']}").json()

        assert detail["tracks"][0]["is_playable"] is True
        assert detail["tracks"][0]["title"] == "Hoppipolla"


class TestPlaylistRename:
    def test_a_rename_bumps_the_revision(self, client: TestClient, profile_id: str) -> None:
        playlist = client.post(_playlists_path(profile_id), json={"name": "Sunday"}).json()

        renamed = client.patch(
            f"/api/v1/playlists/{playlist['id']}",
            json={"name": "Sunday Morning", "revision": playlist["revision"]},
        )

        assert renamed.status_code == 200
        assert renamed.json()["name"] == "Sunday Morning"
        assert renamed.json()["revision"] == 2

    def test_a_rename_onto_an_existing_name_is_refused(
        self, client: TestClient, profile_id: str
    ) -> None:
        client.post(_playlists_path(profile_id), json={"name": "Sunday"})
        second = client.post(_playlists_path(profile_id), json={"name": "Monday"}).json()

        response = client.patch(
            f"/api/v1/playlists/{second['id']}",
            json={"name": "Sunday", "revision": second["revision"]},
        )

        assert response.status_code == 409


class TestDurability:
    def test_playlists_and_their_order_survive_a_restart(
        self,
        start_api: Callable[[], TestClient],
        seed_track: Callable[..., str],
    ) -> None:
        first_run = start_api()
        profile_id = first_run.post(PROFILES_PATH, json={"name": "Household"}).json()["id"]
        playlist = first_run.post(_playlists_path(profile_id), json={"name": "Sunday"}).json()
        first = seed_track(title="Hoppipolla")
        second = seed_track(title="Glosoli")
        after = first_run.post(
            f"/api/v1/playlists/{playlist['id']}/tracks",
            json={"track_id": first, "revision": playlist["revision"]},
        ).json()
        first_run.post(
            f"/api/v1/playlists/{playlist['id']}/tracks",
            json={"track_id": second, "revision": after["playlist"]["revision"]},
        )

        restarted = start_api()
        detail = restarted.get(f"/api/v1/playlists/{playlist['id']}").json()

        assert [track["id"] for track in detail["tracks"]] == [first, second]
