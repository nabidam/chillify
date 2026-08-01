"""Real Alembic migrations against a disposable SQLite file.

The round trip is up, down, up. Rollback always means the down migration: a
reverted commit would leave the schema changed underneath code that no longer
expects it.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from chillify.infrastructure.db.engine import create_database_engine, read_pragma

pytestmark = pytest.mark.integration

BACKEND_ROOT = Path(__file__).resolve().parents[2]

EXPECTED_TABLES = {
    "profiles",
    "tracks",
    "track_sources",
    "playlists",
    "playlist_tracks",
    "download_jobs",
    "job_events",
    "settings",
    "artwork_stages",
    "api_idempotency",
    "media_mutations",
    "inspections",
}

EXPECTED_SETTINGS_KEYS = {
    "proxy",
    "inspection",
    "provider.deezer",
    "provider.spotdl",
    "provider.yt_dlp",
    "provider.lastfm",
    "provider.spotify_api",
}


@pytest.fixture
def alembic_config(tmp_path: Path) -> tuple[Config, Path]:
    database_path = tmp_path / "chillify.sqlite3"
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database_path}")
    return config, database_path


def _schema(database_path: Path) -> set[str]:
    with closing(sqlite3.connect(database_path)) as connection:
        rows = connection.execute(
            "SELECT type, name, sql FROM sqlite_master "
            "WHERE name NOT LIKE 'sqlite_%' AND name <> 'alembic_version'"
        ).fetchall()
    return {f"{kind}:{name}:{sql}" for kind, name, sql in rows}


def _tables(database_path: Path) -> set[str]:
    with closing(sqlite3.connect(database_path)) as connection:
        rows = connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {name for (name,) in rows}


def test_upgrade_creates_the_complete_documented_schema(
    alembic_config: tuple[Config, Path],
) -> None:
    config, database_path = alembic_config

    command.upgrade(config, "head")

    assert _tables(database_path) >= EXPECTED_TABLES


def test_upgrade_seeds_provider_and_proxy_settings(
    alembic_config: tuple[Config, Path],
) -> None:
    config, database_path = alembic_config

    command.upgrade(config, "head")

    with closing(sqlite3.connect(database_path)) as connection:
        rows = dict(connection.execute("SELECT key, public_json FROM settings").fetchall())
    assert set(rows) == EXPECTED_SETTINGS_KEYS
    assert '"enabled":true' in rows["provider.deezer"]
    assert '"mode":"fast"' in rows["inspection"]
    assert '"configured":false' in rows["provider.spotify_api"]
    # Last.fm stays disabled until the operator configures a key.
    assert '"enabled":false' in rows["provider.lastfm"]


def test_round_trip_restores_an_identical_schema_and_preserves_prior_data(
    alembic_config: tuple[Config, Path],
) -> None:
    config, database_path = alembic_config

    # Data that exists before the first upgrade must survive the whole cycle.
    with closing(sqlite3.connect(database_path)) as connection:
        connection.execute("CREATE TABLE operator_notes (id INTEGER PRIMARY KEY, note TEXT)")
        connection.execute("INSERT INTO operator_notes (id, note) VALUES (1, 'pre-upgrade')")
        connection.commit()

    command.upgrade(config, "head")
    after_first_upgrade = _schema(database_path)

    command.downgrade(config, "base")
    assert not EXPECTED_TABLES & _tables(database_path)

    command.upgrade(config, "head")

    assert _schema(database_path) == after_first_upgrade
    with closing(sqlite3.connect(database_path)) as connection:
        surviving = connection.execute("SELECT note FROM operator_notes").fetchall()
    assert surviving == [("pre-upgrade",)]


def test_radio_javan_migration_preserves_legacy_jobs_and_events(
    alembic_config: tuple[Config, Path],
) -> None:
    config, database_path = alembic_config

    command.upgrade(config, "0004_catalog_track_sources")
    with closing(sqlite3.connect(database_path)) as connection:
        connection.execute(
            """
            INSERT INTO download_jobs (
                id, provider, source_type, source_ref, dedupe_key, request_json,
                state, phase, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "legacy-job",
                "deezer",
                "deezer_result",
                "legacy-source",
                "legacy-dedupe",
                "{}",
                "completed",
                "completed",
                "2026-08-01T00:00:00Z",
                "2026-08-01T00:00:00Z",
            ),
        )
        connection.execute(
            """
            INSERT INTO job_events (
                job_id, sequence, state, phase, progress_percent, payload_json, occurred_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "legacy-job",
                1,
                "completed",
                "completed",
                100.0,
                '{"origin":"legacy"}',
                "2026-08-01T00:00:00Z",
            ),
        )
        connection.commit()

    command.upgrade(config, "head")
    with closing(sqlite3.connect(database_path)) as connection:
        connection.execute(
            """
            INSERT INTO tracks (
                id, title, artist, normalized_artist, normalized_title, normalized_album,
                file_relpath, file_size_bytes, content_sha256, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "radiojavan-track",
                "Radio Javan migration fixture",
                "Fixture Artist",
                "fixture artist",
                "radio javan migration fixture",
                "",
                "music/fixture.mp3",
                1,
                "a" * 64,
                "2026-08-01T00:00:00Z",
                "2026-08-01T00:00:00Z",
            ),
        )
        connection.execute(
            """
            INSERT INTO track_sources (id, track_id, provider, source_id, source_url, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "radiojavan-source",
                "radiojavan-track",
                "radiojavan",
                "rj-source",
                "https://play.radiojavan.com/song/rj-source",
                "2026-08-01T00:00:00Z",
            ),
        )
        connection.execute(
            """
            INSERT INTO download_jobs (
                id, provider, source_type, source_ref, dedupe_key, request_json,
                state, phase, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "radiojavan-job",
                "radiojavan",
                "radiojavan_track",
                "rj-source",
                "radiojavan-dedupe",
                "{}",
                "completed",
                "completed",
                "2026-08-01T00:00:00Z",
                "2026-08-01T00:00:00Z",
            ),
        )
        connection.commit()

    with pytest.raises(RuntimeError, match="Radio Javan provenance"):
        command.downgrade(config, "0004_catalog_track_sources")
    with closing(sqlite3.connect(database_path)) as connection:
        connection.execute("DELETE FROM track_sources WHERE id = 'radiojavan-source'")
        connection.commit()
    with pytest.raises(RuntimeError, match="Radio Javan jobs"):
        command.downgrade(config, "0004_catalog_track_sources")
    with closing(sqlite3.connect(database_path)) as connection:
        connection.execute("DELETE FROM download_jobs WHERE id = 'radiojavan-job'")
        connection.commit()

    command.downgrade(config, "0004_catalog_track_sources")
    command.upgrade(config, "head")
    with closing(sqlite3.connect(database_path)) as connection:
        assert connection.execute(
            "SELECT id, provider, source_type FROM download_jobs WHERE id = 'legacy-job'"
        ).fetchall() == [("legacy-job", "deezer", "deezer_result")]
        assert connection.execute(
            "SELECT job_id, sequence, payload_json FROM job_events WHERE job_id = 'legacy-job'"
        ).fetchall() == [("legacy-job", 1, '{"origin":"legacy"}')]
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_engine_applies_the_documented_pragmas(alembic_config: tuple[Config, Path]) -> None:
    config, database_path = alembic_config
    command.upgrade(config, "head")

    engine = create_database_engine(database_path)
    try:
        assert read_pragma(engine, "journal_mode").lower() == "wal"
        assert read_pragma(engine, "foreign_keys") == "1"
        assert read_pragma(engine, "synchronous") == "2"
        assert read_pragma(engine, "busy_timeout") == "5000"
    finally:
        engine.dispose()


def test_foreign_keys_and_check_constraints_are_enforced(
    alembic_config: tuple[Config, Path],
) -> None:
    config, database_path = alembic_config
    command.upgrade(config, "head")

    with closing(sqlite3.connect(database_path)) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO playlists (id, profile_id, name, name_folded, "
                "created_at, updated_at) VALUES ('p1', 'absent', 'Mix', 'mix', "
                "'2026-07-20T00:00:00Z', '2026-07-20T00:00:00Z')"
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO profiles (id, name, name_folded, created_at, updated_at) "
                "VALUES ('x', '', '', '2026-07-20T00:00:00Z', '2026-07-20T00:00:00Z')"
            )
