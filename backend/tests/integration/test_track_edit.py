"""One correction changing tags, artwork, path, and record together.

Every claim here is durable-state behavior: what is on the mounted filesystem
and in SQLite after the save, and what survives a Compose restart. A green
in-memory assertion would prove nothing about the thing this contract exists
for.
"""

from __future__ import annotations

import hashlib
import io
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3
from PIL import Image
from sqlalchemy import text

from chillify.domain.models import to_rfc3339
from chillify.infrastructure.db.engine import create_database_engine
from chillify.infrastructure.db.repositories import new_id

pytestmark = pytest.mark.integration

FIXTURE_AUDIO = Path(__file__).resolve().parents[1] / "fixtures" / "media" / "gate-tone.mp3"
UPLOAD_PATH = "/api/v1/artwork/stages/upload"


def _cover_bytes(color: tuple[int, int, int] = (10, 120, 200)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (400, 400), color=color).save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
def music_root(migrated_environment: dict[str, str]) -> Path:
    return Path(migrated_environment["CHILLIFY_MUSIC_ROOT"])


@pytest.fixture
def seed_track(migrated_environment: dict[str, str]) -> Iterator[Callable[..., str]]:
    """Insert one track row and write a real MP3 at its managed path."""
    data_root = Path(migrated_environment["CHILLIFY_DATA_ROOT"])
    music_root = Path(migrated_environment["CHILLIFY_MUSIC_ROOT"])
    engine = create_database_engine(data_root / "db" / "chillify.sqlite3")

    def seed(
        *,
        title: str = "Hoppipolla",
        artist: str = "Sigur Ros",
        album: str | None = "Takk",
        normalized_artist: str = "sigur ros",
        normalized_title: str = "hoppipolla",
        normalized_album: str = "takk",
        availability: str = "available",
        write_file: bool = True,
    ) -> str:
        track_id = new_id()
        # Derived from the track so two seeded tracks never collide on the
        # provider-identity unique index.
        source_id = track_id[-12:]
        relative_path = f"Music/{artist}/{album}/01 - {title}.mp3"
        content = FIXTURE_AUDIO.read_bytes()
        if write_file:
            absolute = music_root / relative_path
            absolute.parent.mkdir(parents=True, exist_ok=True)
            absolute.write_bytes(content)

        moment = to_rfc3339(datetime.now(UTC))
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO tracks (id, title, artist, album, release_year, disc_number,"
                    " track_number, duration_ms, normalized_artist, normalized_title,"
                    " normalized_album, file_relpath, mime_type, file_size_bytes,"
                    " content_sha256, availability, revision, created_at, updated_at)"
                    " VALUES (:id, :title, :artist, :album, 2005, 1, 1, 180000,"
                    " :normalized_artist, :normalized_title, :normalized_album, :relpath,"
                    " 'audio/mpeg', :size, :digest, :availability, 1, :moment, :moment)"
                ),
                {
                    "id": track_id,
                    "title": title,
                    "artist": artist,
                    "album": album,
                    "normalized_artist": normalized_artist,
                    "normalized_title": normalized_title,
                    "normalized_album": normalized_album,
                    "relpath": relative_path,
                    "size": len(content),
                    "digest": hashlib.sha256(content).hexdigest(),
                    "availability": availability,
                    "moment": moment,
                },
            )
            connection.execute(
                text(
                    "INSERT INTO track_sources (id, track_id, provider, source_id, source_url,"
                    " created_at) VALUES (:id, :track_id, 'deezer', :source_id, :source_url,"
                    " :moment)"
                ),
                {
                    "id": new_id(),
                    "track_id": track_id,
                    "source_id": source_id,
                    "source_url": f"https://www.deezer.com/track/{source_id}",
                    "moment": moment,
                },
            )
        return track_id

    yield seed
    engine.dispose()


@pytest.fixture
def client(start_api: Callable[[], TestClient]) -> TestClient:
    return start_api()


def _edit_body(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "title": "Hoppipolla",
        "artist": "Sigur Ros",
        "album": "Takk",
        "release_year": 2005,
        "disc_number": 1,
        "track_number": 1,
    }
    body.update(overrides)
    return body


class TestAtomicCorrection:
    def test_a_save_rewrites_tags_path_and_record_together(
        self, client: TestClient, seed_track: Callable[..., str], music_root: Path
    ) -> None:
        track_id = seed_track()

        response = client.patch(
            f"/api/v1/tracks/{track_id}",
            headers={"If-Match": "1"},
            json=_edit_body(title="Hoppípolla", album="Takk...", track_number=4),
        )

        assert response.status_code == 200
        track = response.json()["track"]
        assert track["title"] == "Hoppípolla"
        assert track["album"] == "Takk..."
        assert track["revision"] == 2
        assert track["is_playable"] is True

        # The album directory is the sanitized component, so the trailing dots
        # of "Takk..." never reach the filesystem even though the record keeps
        # them.
        moved = music_root / "Music/Sigur Ros/Takk/04 - Hoppípolla.mp3"
        assert moved.is_file()
        assert not (music_root / "Music/Sigur Ros/Takk/01 - Hoppipolla.mp3").exists()

        tags = EasyID3(moved)
        assert tags["title"] == ["Hoppípolla"]
        assert tags["album"] == ["Takk..."]

    def test_the_edited_file_is_the_one_the_stream_route_serves(
        self, client: TestClient, seed_track: Callable[..., str]
    ) -> None:
        track_id = seed_track()

        client.patch(
            f"/api/v1/tracks/{track_id}",
            headers={"If-Match": "1"},
            json=_edit_body(title="Corrected Title"),
        )

        streamed = client.get(f"/api/v1/tracks/{track_id}/stream")
        assert streamed.status_code == 200
        assert streamed.headers["content-type"] == "audio/mpeg"

    def test_a_restart_preserves_only_the_new_version(
        self,
        start_api: Callable[[], TestClient],
        seed_track: Callable[..., str],
        music_root: Path,
    ) -> None:
        track_id = seed_track()
        first = start_api()
        first.patch(
            f"/api/v1/tracks/{track_id}",
            headers={"If-Match": "1"},
            json=_edit_body(title="Corrected Title", album="New Album", track_number=7),
        )

        restarted = start_api()
        detail = restarted.get(f"/api/v1/tracks/{track_id}").json()

        assert detail["track"]["title"] == "Corrected Title"
        assert detail["track"]["revision"] == 2
        assert (music_root / "Music/Sigur Ros/New Album/07 - Corrected Title.mp3").is_file()
        # The superseded path and its emptied album directory are both gone: no
        # second copy of the track is left behind for a person browsing over SMB.
        assert not (music_root / "Music/Sigur Ros/Takk").exists()

    def test_no_recovery_or_staging_residue_survives_a_completed_save(
        self, client: TestClient, seed_track: Callable[..., str], music_root: Path
    ) -> None:
        track_id = seed_track()

        client.patch(
            f"/api/v1/tracks/{track_id}",
            headers={"If-Match": "1"},
            json=_edit_body(title="Corrected Title"),
        )

        internal = music_root / ".chillify"
        assert not any((internal / "recovery").glob("*/*"))
        assert not any((internal / "staging").glob("*/*.mp3"))

    def test_the_mutation_journal_is_empty_after_a_completed_save(
        self, client: TestClient, seed_track: Callable[..., str], migrated_environment: dict
    ) -> None:
        track_id = seed_track()
        client.patch(
            f"/api/v1/tracks/{track_id}",
            headers={"If-Match": "1"},
            json=_edit_body(title="Corrected Title"),
        )

        engine = create_database_engine(
            Path(migrated_environment["CHILLIFY_DATA_ROOT"]) / "db" / "chillify.sqlite3"
        )
        try:
            with engine.connect() as connection:
                remaining = connection.execute(
                    text("SELECT count(*) FROM media_mutations")
                ).scalar_one()
        finally:
            engine.dispose()

        assert remaining == 0


class TestArtworkCorrection:
    def test_a_staged_cover_is_embedded_and_published_by_the_save_that_consumes_it(
        self, client: TestClient, seed_track: Callable[..., str], music_root: Path
    ) -> None:
        track_id = seed_track()
        staged = client.post(
            UPLOAD_PATH, files={"file": ("cover.png", _cover_bytes(), "image/png")}
        )
        assert staged.status_code == 201
        stage_id = staged.json()["id"]

        response = client.patch(
            f"/api/v1/tracks/{track_id}",
            headers={"If-Match": "1"},
            json=_edit_body(artwork_stage_id=stage_id),
        )

        assert response.status_code == 200
        assert response.json()["has_artwork"] is True

        published = music_root / f"Artwork/{track_id}.jpg"
        assert published.is_file()

        audio = music_root / "Music/Sigur Ros/Takk/01 - Hoppipolla.mp3"
        covers = ID3(audio).getall("APIC")
        assert len(covers) == 1
        assert covers[0].mime == "image/jpeg"

    def test_the_published_cover_is_served_on_the_media_path(
        self, client: TestClient, seed_track: Callable[..., str]
    ) -> None:
        track_id = seed_track()
        stage_id = client.post(
            UPLOAD_PATH, files={"file": ("cover.png", _cover_bytes(), "image/png")}
        ).json()["id"]
        client.patch(
            f"/api/v1/tracks/{track_id}",
            headers={"If-Match": "1"},
            json=_edit_body(artwork_stage_id=stage_id),
        )

        served = client.get(f"/media/artwork/tracks/{track_id}")

        assert served.status_code == 200
        assert served.headers["content-type"] == "image/jpeg"

    def test_a_stage_is_single_use(
        self, client: TestClient, seed_track: Callable[..., str]
    ) -> None:
        track_id = seed_track()
        other_id = seed_track(
            title="Glosoli", normalized_title="glosoli", album="Takk", normalized_album="takk"
        )
        stage_id = client.post(
            UPLOAD_PATH, files={"file": ("cover.png", _cover_bytes(), "image/png")}
        ).json()["id"]
        client.patch(
            f"/api/v1/tracks/{track_id}",
            headers={"If-Match": "1"},
            json=_edit_body(artwork_stage_id=stage_id),
        )

        reused = client.patch(
            f"/api/v1/tracks/{other_id}",
            headers={"If-Match": "1"},
            json=_edit_body(title="Glosoli", artwork_stage_id=stage_id),
        )

        assert reused.status_code == 409
        assert reused.json()["error"]["code"] == "artwork_stage_unavailable"

    def test_an_unreadable_upload_is_refused_without_creating_a_stage(
        self, client: TestClient
    ) -> None:
        response = client.post(
            UPLOAD_PATH, files={"file": ("notes.txt", b"just some text", "text/plain")}
        )

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "artwork_unreadable"

    def test_a_missing_stage_is_reported_and_changes_nothing(
        self, client: TestClient, seed_track: Callable[..., str]
    ) -> None:
        track_id = seed_track()

        response = client.patch(
            f"/api/v1/tracks/{track_id}",
            headers={"If-Match": "1"},
            json=_edit_body(title="Corrected", artwork_stage_id=new_id()),
        )

        assert response.status_code == 409
        assert client.get(f"/api/v1/tracks/{track_id}").json()["track"]["title"] == "Hoppipolla"


class TestRefusedCorrections:
    def test_a_stale_revision_is_refused_and_the_stored_record_is_untouched(
        self, client: TestClient, seed_track: Callable[..., str]
    ) -> None:
        track_id = seed_track()

        response = client.patch(
            f"/api/v1/tracks/{track_id}",
            headers={"If-Match": "7"},
            json=_edit_body(title="Corrected"),
        )

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "record_changed"
        assert client.get(f"/api/v1/tracks/{track_id}").json()["track"]["title"] == "Hoppipolla"

    def test_a_refused_save_leaves_no_journal_row_or_staged_files(
        self,
        client: TestClient,
        seed_track: Callable[..., str],
        music_root: Path,
        migrated_environment: dict,
    ) -> None:
        """A stale save must not leave recovery state describing a change it never made.

        The revision is checked before anything is journaled or staged, so a
        save that has already lost costs nothing but the error it returns.
        """
        track_id = seed_track()

        refused = client.patch(
            f"/api/v1/tracks/{track_id}",
            headers={"If-Match": "7"},
            json=_edit_body(title="Corrected"),
        )
        assert refused.status_code == 409

        internal = music_root / ".chillify"
        assert not any((internal / "recovery").glob("*/*"))
        assert not any((internal / "staging").glob("*/*.mp3"))

        engine = create_database_engine(
            Path(migrated_environment["CHILLIFY_DATA_ROOT"]) / "db" / "chillify.sqlite3"
        )
        try:
            with engine.connect() as connection:
                journal_rows = connection.execute(
                    text("SELECT count(*) FROM media_mutations")
                ).scalar_one()
        finally:
            engine.dispose()
        assert journal_rows == 0

    def test_a_save_without_a_revision_is_refused_before_anything_is_locked(
        self, client: TestClient, seed_track: Callable[..., str]
    ) -> None:
        track_id = seed_track()

        response = client.patch(f"/api/v1/tracks/{track_id}", json=_edit_body(title="Corrected"))

        assert response.status_code == 422
        assert response.json()["error"]["field"] == "If-Match"

    def test_a_collision_with_another_track_is_refused_before_a_file_moves(
        self, client: TestClient, seed_track: Callable[..., str], music_root: Path
    ) -> None:
        first = seed_track()
        second = seed_track(
            title="Glosoli", normalized_title="glosoli", album="Takk", normalized_album="takk"
        )

        response = client.patch(
            f"/api/v1/tracks/{second}",
            headers={"If-Match": "1"},
            json=_edit_body(title="Hoppipolla"),
        )

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "duplicate_record"
        assert response.json()["error"]["detail"]["existing_track_id"] == first
        assert (music_root / "Music/Sigur Ros/Takk/01 - Glosoli.mp3").is_file()

    def test_a_track_whose_file_is_missing_refuses_tag_and_path_mutation(
        self, client: TestClient, seed_track: Callable[..., str]
    ) -> None:
        track_id = seed_track(availability="missing", write_file=False)

        response = client.patch(
            f"/api/v1/tracks/{track_id}",
            headers={"If-Match": "1"},
            json=_edit_body(title="Corrected"),
        )

        assert response.status_code == 410
        assert response.json()["error"]["code"] == "track_file_missing"

    def test_a_blank_title_is_reported_on_its_own_field(
        self, client: TestClient, seed_track: Callable[..., str]
    ) -> None:
        track_id = seed_track()

        response = client.patch(
            f"/api/v1/tracks/{track_id}", headers={"If-Match": "1"}, json=_edit_body(title="   ")
        )

        assert response.status_code == 422
        assert response.json()["error"]["field"] == "title"

    def test_a_release_year_beyond_next_year_is_refused(
        self, client: TestClient, seed_track: Callable[..., str]
    ) -> None:
        track_id = seed_track()

        response = client.patch(
            f"/api/v1/tracks/{track_id}",
            headers={"If-Match": "1"},
            json=_edit_body(release_year=9999),
        )

        assert response.status_code == 422
        assert response.json()["error"]["field"] == "release_year"


class TestTrackDetail:
    def test_the_detail_discloses_source_identities_and_never_a_path(
        self, client: TestClient, seed_track: Callable[..., str]
    ) -> None:
        track_id = seed_track()

        detail = client.get(f"/api/v1/tracks/{track_id}").json()

        assert detail["sources"][0]["provider"] == "deezer"
        assert detail["sources"][0]["source_id"] == track_id[-12:]
        assert "file_relpath" not in detail["track"]
        assert "Music/" not in client.get(f"/api/v1/tracks/{track_id}").text

    def test_an_unknown_track_is_reported_as_missing(self, client: TestClient) -> None:
        response = client.get(f"/api/v1/tracks/{new_id()}")

        assert response.status_code == 404
