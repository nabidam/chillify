"""Recovery of a metadata edit a crash left half-applied.

The in-request edit path already rolls itself back when a step fails while the
process lives (see `test_track_edit.py`). This suite covers the other failure:
the process is killed between two committed steps, leaving a `media_mutations`
row open. Startup recovery must drive every such row to one authoritative,
playable state — finishing the ones whose database transaction committed and
reversing the ones whose did not — and it must do so when the real application
boots, not only when a test calls it.
"""

from __future__ import annotations

import hashlib
import shutil
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from chillify.application.metadata import MetadataService
from chillify.domain.models import TrackEdit, TrackId, to_rfc3339
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

OLD_RELPATH = "Music/Sigur Ros/Takk/01 - Hoppipolla.mp3"
NEW_RELPATH = "Music/Sigur Ros/Takk/01 - Corrected.mp3"


@pytest.fixture
def music_root(migrated_environment: dict[str, str]) -> Path:
    return Path(migrated_environment["CHILLIFY_MUSIC_ROOT"])


@pytest.fixture
def database_path(migrated_environment: dict[str, str]) -> Path:
    return Path(migrated_environment["CHILLIFY_DATA_ROOT"]) / "db" / "chillify.sqlite3"


@pytest.fixture
def session_factory(database_path: Path) -> Iterator[sessionmaker[Session]]:
    engine = create_database_engine(database_path)
    try:
        yield create_session_factory(engine)
    finally:
        engine.dispose()


@pytest.fixture
def seed_track(database_path: Path, music_root: Path) -> str:
    """Insert one track and write its real MP3 at the old managed path."""
    engine = create_database_engine(database_path)
    track_id = new_id()
    content = FIXTURE_AUDIO.read_bytes()
    audio = music_root / OLD_RELPATH
    audio.parent.mkdir(parents=True, exist_ok=True)
    audio.write_bytes(content)
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
                    "relpath": OLD_RELPATH,
                    "size": len(content),
                    "digest": hashlib.sha256(content).hexdigest(),
                    "moment": moment,
                },
            )
    finally:
        engine.dispose()
    return track_id


def _old_record(track_id: str) -> dict[str, object]:
    content = FIXTURE_AUDIO.read_bytes()
    return {
        "title": "Hoppipolla",
        "artist": "Sigur Ros",
        "album": "Takk",
        "file_relpath": OLD_RELPATH,
        "artwork_relpath": None,
        "file_size_bytes": len(content),
        "content_sha256": hashlib.sha256(content).hexdigest(),
        "revision": 1,
    }


class TestFinalizeAfterCommit:
    def test_a_committed_edit_left_uncleaned_is_finalized(
        self,
        seed_track: str,
        music_root: Path,
        session_factory: sessionmaker[Session],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A crash after the row was rewritten but before the old file was dropped.

        The new record already plays; recovery only has to remove the superseded
        file and close the journal, leaving exactly one copy of the track.
        """
        service = MetadataService(session_factory=session_factory, music_root=music_root)

        # Simulate the process dying at the last step: the database transaction
        # committed the new record and the journal reached `db_committed`, then
        # cleanup never ran.
        def die(*_: object, **__: object) -> None:
            raise RuntimeError("process killed before finalize")

        monkeypatch.setattr(MetadataService, "_finalize", die)
        with pytest.raises(RuntimeError):
            service.update_track(
                TrackId(seed_track),
                TrackEdit(
                    title="Corrected",
                    artist="Sigur Ros",
                    album="Takk",
                    release_year=2005,
                    disc_number=1,
                    track_number=1,
                ),
                expected_revision=1,
            )

        # The committed state: new file present, old file still there, journal open.
        assert (music_root / NEW_RELPATH).is_file()
        assert (music_root / OLD_RELPATH).is_file()
        with session_factory() as session:
            assert len(MediaMutationRepository(session).list_recoverable()) == 1

        outcome = MediaRecoveryService(
            session_factory=session_factory, music_root=music_root
        ).recover()

        assert len(outcome.finalized) == 1
        # One authoritative, playable copy remains: the new file, at the new path.
        assert (music_root / NEW_RELPATH).is_file()
        assert not (music_root / OLD_RELPATH).exists()
        with session_factory() as session:
            track = TrackRepository(session).get(TrackId(seed_track))
            assert track is not None
            assert track.revision == 2
            assert track.is_playable
            assert track.file_relpath == NEW_RELPATH
            assert session.execute(text("SELECT count(*) FROM media_mutations")).scalar_one() == 0


class TestRollbackBeforeCommit:
    def test_an_edit_stranded_after_placement_restores_the_old_version(
        self, seed_track: str, music_root: Path, session_factory: sessionmaker[Session]
    ) -> None:
        """A crash after the new file was placed but before the row was rewritten.

        Both files exist on disk and the database still holds the old record, so
        recovery removes the stray new file and returns the track to its old,
        playable path — the edit simply did not happen.
        """
        # Reproduce that state in the real journal order: open the journal, its
        # own id names the recovery workspace, snapshot the live file, place a new
        # file, mark the track `mutating`, and leave the row at `files_staged`.
        with session_factory() as session:
            journal = MediaMutationRepository(session)
            mutation_id = journal.open_edit(
                track_id=TrackId(seed_track),
                old_record=_old_record(seed_track),
                new_record={
                    "title": "Corrected",
                    "artist": "Sigur Ros",
                    "album": "Takk",
                    "release_year": 2005,
                    "disc_number": 1,
                    "track_number": 1,
                    "file_relpath": NEW_RELPATH,
                    "artwork_relpath": None,
                },
                now=datetime.now(UTC),
            )
            TrackRepository(session).begin_mutation(TrackId(seed_track), expected_revision=1)
            session.commit()

        recovery = mutations.preserve_recovery(
            music_root, mutation_id=mutation_id, relpaths=[OLD_RELPATH]
        )
        # The new file was placed before the crash: a second copy now exists.
        shutil.copy2(FIXTURE_AUDIO, music_root / NEW_RELPATH)
        with session_factory() as session:
            MediaMutationRepository(session).advance(
                mutation_id, state="files_staged", now=datetime.now(UTC), recovery=recovery
            )
            session.commit()

        outcome = MediaRecoveryService(
            session_factory=session_factory, music_root=music_root
        ).recover()

        assert mutation_id in outcome.rolled_back
        # The stray new file is gone and the old, unchanged track plays again.
        assert not (music_root / NEW_RELPATH).exists()
        assert (music_root / OLD_RELPATH).is_file()
        with session_factory() as session:
            track = TrackRepository(session).get(TrackId(seed_track))
            assert track is not None
            assert track.revision == 1
            assert track.file_relpath == OLD_RELPATH
            assert track.is_playable
            assert MediaMutationRepository(session).list_recoverable() == ()


class TestRecoveryRunsOnBoot:
    def test_starting_the_api_finishes_an_interrupted_edit(
        self,
        seed_track: str,
        music_root: Path,
        session_factory: sessionmaker[Session],
        start_api: Callable[[], TestClient],
    ) -> None:
        """The real application boot resolves an open journal before serving.

        This is what makes recovery restart-safe rather than a method a test has
        to remember to call.
        """
        with session_factory() as session:
            journal = MediaMutationRepository(session)
            mutation_id = journal.open_edit(
                track_id=TrackId(seed_track),
                old_record=_old_record(seed_track),
                new_record={
                    "title": "Corrected",
                    "artist": "Sigur Ros",
                    "album": "Takk",
                    "release_year": 2005,
                    "disc_number": 1,
                    "track_number": 1,
                    "file_relpath": NEW_RELPATH,
                    "artwork_relpath": None,
                },
                now=datetime.now(UTC),
            )
            session.commit()
        recovery = mutations.preserve_recovery(
            music_root, mutation_id=mutation_id, relpaths=[OLD_RELPATH]
        )
        shutil.copy2(FIXTURE_AUDIO, music_root / NEW_RELPATH)
        # A committed edit awaiting cleanup: the new record is authoritative.
        with session_factory() as session:
            TrackRepository(session).apply_edit(
                TrackId(seed_track),
                expected_revision=1,
                title="Corrected",
                artist="Sigur Ros",
                album="Takk",
                release_year=2005,
                disc_number=1,
                track_number=1,
                file_relpath=NEW_RELPATH,
                artwork_relpath=None,
                file_size_bytes=(music_root / NEW_RELPATH).stat().st_size,
                content_sha256=hashlib.sha256((music_root / NEW_RELPATH).read_bytes()).hexdigest(),
                now=datetime.now(UTC),
            )
            MediaMutationRepository(session).advance(
                mutation_id, state="db_committed", now=datetime.now(UTC), recovery=recovery
            )
            session.commit()

        # Booting the app runs recovery in its lifespan before it answers.
        client = start_api()

        assert client.get(f"/api/v1/tracks/{seed_track}").status_code == 200
        assert (music_root / NEW_RELPATH).is_file()
        assert not (music_root / OLD_RELPATH).exists()
        with session_factory() as session:
            assert session.execute(text("SELECT count(*) FROM media_mutations")).scalar_one() == 0
