"""Permanent deletion and its recovery from an interrupted mutation.

Every claim here is durable-state behavior: what remains on the mounted
filesystem and in SQLite after a deletion, after an *interrupted* deletion is
recovered, and after a Compose restart. A completed deletion must leave one
authoritative state — the media gone, every reference removed, and only an
anonymous job-history shell behind — and an interrupted one must recover to one
authoritative state too, never a file without a record or a record without a
file.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from chillify.domain.models import TrackId, to_rfc3339
from chillify.infrastructure.db.engine import create_database_engine, create_session_factory
from chillify.infrastructure.db.repositories import (
    MediaMutationRepository,
    TrackRepository,
    new_id,
)
from chillify.infrastructure.media import mutations
from chillify.infrastructure.media.recovery import MediaRecoveryService

pytestmark = pytest.mark.integration

FIXTURE_AUDIO = Path(__file__).resolve().parents[1] / "fixtures" / "media" / "gate-tone.mp3"


@pytest.fixture
def music_root(migrated_environment: dict[str, str]) -> Path:
    return Path(migrated_environment["CHILLIFY_MUSIC_ROOT"])


@pytest.fixture
def database_path(migrated_environment: dict[str, str]) -> Path:
    return Path(migrated_environment["CHILLIFY_DATA_ROOT"]) / "db" / "chillify.sqlite3"


@pytest.fixture
def seed_track(migrated_environment: dict[str, str]) -> Iterator[Callable[..., str]]:
    """Insert one track and its real MP3, optionally with a cover and a job."""
    music_root = Path(migrated_environment["CHILLIFY_MUSIC_ROOT"])
    database_path = Path(migrated_environment["CHILLIFY_DATA_ROOT"]) / "db" / "chillify.sqlite3"
    engine = create_database_engine(database_path)

    def seed(*, with_artwork: bool = True) -> str:
        track_id = new_id()
        relative_path = "Music/Sigur Ros/Takk/01 - Hoppipolla.mp3"
        artwork_relpath = f"Artwork/{track_id}.jpg" if with_artwork else None
        content = FIXTURE_AUDIO.read_bytes()
        audio = music_root / relative_path
        audio.parent.mkdir(parents=True, exist_ok=True)
        audio.write_bytes(content)
        if artwork_relpath is not None:
            cover = music_root / artwork_relpath
            cover.parent.mkdir(parents=True, exist_ok=True)
            cover.write_bytes(b"\xff\xd8\xff\xe0jpeg-bytes")

        moment = to_rfc3339(datetime.now(UTC))
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO tracks (id, title, artist, album, release_year, disc_number,"
                    " track_number, duration_ms, normalized_artist, normalized_title,"
                    " normalized_album, file_relpath, artwork_relpath, mime_type, file_size_bytes,"
                    " content_sha256, availability, revision, created_at, updated_at)"
                    " VALUES (:id, 'Hoppipolla', 'Sigur Ros', 'Takk', 2005, 1, 1, 180000,"
                    " 'sigur ros', 'hoppipolla', 'takk', :relpath, :artwork, 'audio/mpeg', :size,"
                    " :digest, 'available', 1, :moment, :moment)"
                ),
                {
                    "id": track_id,
                    "relpath": relative_path,
                    "artwork": artwork_relpath,
                    "size": len(content),
                    "digest": hashlib.sha256(content).hexdigest(),
                    "moment": moment,
                },
            )
            connection.execute(
                text(
                    "INSERT INTO track_sources (id, track_id, provider, source_id, source_url,"
                    " created_at) VALUES (:id, :track_id, 'deezer', :source_id, :url, :moment)"
                ),
                {
                    "id": new_id(),
                    "track_id": track_id,
                    "source_id": track_id[-12:],
                    "url": f"https://www.deezer.com/track/{track_id[-12:]}",
                    "moment": moment,
                },
            )
        return track_id

    yield seed
    engine.dispose()


def _seed_playlist_with_track(database_path: Path, track_id: str) -> str:
    engine = create_database_engine(database_path)
    playlist_id = new_id()
    moment = to_rfc3339(datetime.now(UTC))
    try:
        with engine.begin() as connection:
            profile_id = new_id()
            connection.execute(
                text(
                    "INSERT INTO profiles (id, name, name_folded, created_at, updated_at)"
                    " VALUES (:id, 'Household', 'household', :moment, :moment)"
                ),
                {"id": profile_id, "moment": moment},
            )
            connection.execute(
                text(
                    "INSERT INTO playlists (id, profile_id, name, name_folded, created_at,"
                    " updated_at, revision) VALUES (:id, :profile, 'Sunday', 'sunday', :moment,"
                    " :moment, 1)"
                ),
                {"id": playlist_id, "profile": profile_id, "moment": moment},
            )
            connection.execute(
                text(
                    "INSERT INTO playlist_tracks (playlist_id, track_id, position, added_at)"
                    " VALUES (:playlist, :track, 0, :moment)"
                ),
                {"playlist": playlist_id, "track": track_id, "moment": moment},
            )
    finally:
        engine.dispose()
    return playlist_id


def _seed_completed_job(database_path: Path, track_id: str) -> str:
    """One completed job that produced the track, carrying identifying history."""
    engine = create_database_engine(database_path)
    job_id = new_id()
    moment = to_rfc3339(datetime.now(UTC))
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO download_jobs (id, provider, source_type, source_ref, dedupe_key,"
                    " request_json, candidate_json, state, phase, result_track_id, error_detail,"
                    " restart_count, version, created_at, started_at, finished_at, updated_at)"
                    " VALUES (:id, 'deezer', 'deezer_result', :source_ref, :dedupe,"
                    " :request, :candidate, 'completed', 'completed', :track, :error, 0, 1,"
                    " :moment, :moment, :moment, :moment)"
                ),
                {
                    "id": job_id,
                    "source_ref": "deezer:track:98237",
                    "dedupe": "deezer:98237",
                    "request": json.dumps({"deezer_id": 98237, "title": "Hoppipolla"}),
                    "candidate": json.dumps({"artist": "Sigur Ros", "url": "https://deezer/98237"}),
                    "error": "downloaded https://deezer/98237",
                    "track": track_id,
                    "moment": moment,
                },
            )
            connection.execute(
                text(
                    "INSERT INTO job_events (job_id, sequence, state, phase, payload_json,"
                    " occurred_at) VALUES (:job, 1, 'completed', 'completed', :payload, :moment)"
                ),
                {
                    "job": job_id,
                    "payload": json.dumps({"track_title": "Hoppipolla", "deezer_id": 98237}),
                    "moment": moment,
                },
            )
    finally:
        engine.dispose()
    return job_id


@pytest.fixture
def client(start_api: Callable[[], TestClient]) -> TestClient:
    return start_api()


@pytest.fixture
def session_factory(database_path: Path) -> Iterator[sessionmaker[Session]]:
    """A disposable session factory over the migrated disposable database."""
    engine = create_database_engine(database_path)
    try:
        yield create_session_factory(engine)
    finally:
        engine.dispose()


class TestSuccessfulDeletion:
    def test_a_deletion_removes_the_files_and_every_owned_record(
        self,
        client: TestClient,
        seed_track: Callable[..., str],
        music_root: Path,
        database_path: Path,
    ) -> None:
        track_id = seed_track()
        playlist_id = _seed_playlist_with_track(database_path, track_id)

        response = client.delete(f"/api/v1/tracks/{track_id}", headers={"If-Match": "1"})

        assert response.status_code == 204
        assert response.content == b""
        assert not (music_root / "Music/Sigur Ros/Takk/01 - Hoppipolla.mp3").exists()
        assert not (music_root / f"Artwork/{track_id}.jpg").exists()

        engine = create_database_engine(database_path)
        try:
            with engine.connect() as connection:
                assert (
                    connection.execute(
                        text("SELECT count(*) FROM tracks WHERE id = :id"), {"id": track_id}
                    ).scalar_one()
                    == 0
                )
                assert (
                    connection.execute(
                        text("SELECT count(*) FROM track_sources WHERE track_id = :id"),
                        {"id": track_id},
                    ).scalar_one()
                    == 0
                )
                assert (
                    connection.execute(
                        text("SELECT count(*) FROM playlist_tracks WHERE playlist_id = :id"),
                        {"id": playlist_id},
                    ).scalar_one()
                    == 0
                )
                assert (
                    connection.execute(text("SELECT count(*) FROM media_mutations")).scalar_one()
                    == 0
                )
        finally:
            engine.dispose()

    def test_a_deletion_reduces_the_completed_job_to_an_anonymous_shell(
        self,
        client: TestClient,
        seed_track: Callable[..., str],
        database_path: Path,
    ) -> None:
        track_id = seed_track()
        job_id = _seed_completed_job(database_path, track_id)

        client.delete(f"/api/v1/tracks/{track_id}", headers={"If-Match": "1"})

        engine = create_database_engine(database_path)
        try:
            with engine.connect() as connection:
                job = (
                    connection.execute(
                        text(
                            "SELECT provider, state, phase, source_ref, dedupe_key,"
                            " request_json, candidate_json, error_detail, result_track_id,"
                            " created_at, finished_at FROM download_jobs WHERE id = :id"
                        ),
                        {"id": job_id},
                    )
                    .mappings()
                    .one()
                )
                event = connection.execute(
                    text("SELECT payload_json FROM job_events WHERE job_id = :id"),
                    {"id": job_id},
                ).scalar_one()
        finally:
            engine.dispose()

        # The shell keeps provider, state, phase, and timestamps.
        assert job["provider"] == "deezer"
        assert job["state"] == "completed"
        assert job["phase"] == "completed"
        assert job["created_at"] and job["finished_at"]
        # It keeps nothing that identifies the deleted track.
        assert job["result_track_id"] is None
        assert job["source_ref"] == "deleted"
        assert job["dedupe_key"] == "deleted"
        assert job["request_json"] == "{}"
        assert job["candidate_json"] is None
        assert job["error_detail"] is None
        assert event == "{}"
        assert "Hoppipolla" not in json.dumps(dict(job))

    def test_a_deletion_survives_a_restart(
        self,
        start_api: Callable[[], TestClient],
        seed_track: Callable[..., str],
        music_root: Path,
        database_path: Path,
    ) -> None:
        track_id = seed_track()
        first = start_api()
        first.delete(f"/api/v1/tracks/{track_id}", headers={"If-Match": "1"})

        restarted = start_api()
        assert restarted.get(f"/api/v1/tracks/{track_id}").status_code == 404
        assert not (music_root / "Music/Sigur Ros/Takk/01 - Hoppipolla.mp3").exists()

    def test_a_stale_revision_is_refused_and_the_track_is_untouched(
        self, client: TestClient, seed_track: Callable[..., str], music_root: Path
    ) -> None:
        track_id = seed_track()

        response = client.delete(f"/api/v1/tracks/{track_id}", headers={"If-Match": "9"})

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "record_changed"
        assert client.get(f"/api/v1/tracks/{track_id}").status_code == 200
        assert (music_root / "Music/Sigur Ros/Takk/01 - Hoppipolla.mp3").exists()


class TestInterruptedDeletionRecovery:
    def test_a_deletion_stranded_before_commit_recovers_the_track(
        self,
        seed_track: Callable[..., str],
        music_root: Path,
        session_factory: sessionmaker[Session],
    ) -> None:
        """A crash after the files were removed but before the row was deleted.

        The recovery links still hold the file, so recovery restores it and
        returns the track to a playable state — the person's delete simply did
        not happen.
        """
        track_id = seed_track(with_artwork=False)
        relative_path = "Music/Sigur Ros/Takk/01 - Hoppipolla.mp3"
        factory = session_factory

        # Reproduce the on-disk and journal state a kill at `active_files_removed`
        # leaves, in the real order: the journal opens first, its own id names the
        # recovery workspace, the links are made, the active file is unlinked, and
        # the track row is left marked `recovery`.
        with factory() as session:
            journal = MediaMutationRepository(session)
            row_id = journal.open_delete(
                track_id=TrackId(track_id),
                old_record={"file_relpath": relative_path, "artwork_relpath": None, "revision": 1},
                now=datetime.now(UTC),
            )
            TrackRepository(session).begin_deletion(TrackId(track_id), expected_revision=1)
            session.commit()

        recovery = mutations.preserve_recovery(
            music_root, mutation_id=row_id, relpaths=[relative_path]
        )
        mutations.discard_paths(music_root, [relative_path])
        assert not (music_root / relative_path).exists()

        with factory() as session:
            journal = MediaMutationRepository(session)
            journal.advance(row_id, state="prepared", now=datetime.now(UTC), recovery=recovery)
            journal.advance(row_id, state="active_files_removed", now=datetime.now(UTC))
            session.commit()

        outcome = MediaRecoveryService(session_factory=factory, music_root=music_root).recover()

        assert row_id in outcome.rolled_back
        # The file is back and the track is playable and authoritative again.
        assert (music_root / relative_path).is_file()
        with factory() as session:
            track = TrackRepository(session).get(TrackId(track_id))
            assert track is not None
            assert track.is_playable
            # The journal row is now the terminal `rolled_back` record and is no
            # longer recoverable, so a second pass leaves it alone.
            assert MediaMutationRepository(session).list_recoverable() == ()
            assert (
                session.execute(
                    text("SELECT state FROM media_mutations WHERE id = :id"), {"id": row_id}
                ).scalar_one()
                == "rolled_back"
            )

    def test_a_deletion_stranded_after_commit_is_finished(
        self,
        seed_track: Callable[..., str],
        music_root: Path,
        session_factory: sessionmaker[Session],
    ) -> None:
        """A crash after the row was deleted but before the journal was closed.

        The authoritative state is already the deleted one, so recovery only
        finishes cleanup: it drops the recovery links and closes the journal.
        """
        track_id = seed_track(with_artwork=False)
        relative_path = "Music/Sigur Ros/Takk/01 - Hoppipolla.mp3"
        factory = session_factory

        with factory() as session:
            journal = MediaMutationRepository(session)
            row = journal.open_delete(
                track_id=TrackId(track_id),
                old_record={"file_relpath": relative_path, "artwork_relpath": None, "revision": 1},
                now=datetime.now(UTC),
            )
            session.commit()

        recovery = mutations.preserve_recovery(
            music_root, mutation_id=row, relpaths=[relative_path]
        )
        mutations.discard_paths(music_root, [relative_path])

        with factory() as session:
            journal = MediaMutationRepository(session)
            journal.advance(row, state="prepared", now=datetime.now(UTC), recovery=recovery)
            # The committing transaction happened: the track row is gone.
            TrackRepository(session).delete(TrackId(track_id))
            journal.advance(row, state="db_committed", now=datetime.now(UTC))
            session.commit()

        outcome = MediaRecoveryService(session_factory=factory, music_root=music_root).recover()

        assert row in outcome.finalized
        assert not (music_root / relative_path).exists()
        recovery_dir = music_root / ".chillify" / "recovery" / row
        assert not recovery_dir.exists()
        with factory() as session:
            assert TrackRepository(session).get(TrackId(track_id)) is None
            assert session.execute(text("SELECT count(*) FROM media_mutations")).scalar_one() == 0
