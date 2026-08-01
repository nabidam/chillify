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

EXPECTED_DOWNLOAD_JOB_INDEXES = {
    "ix_download_jobs_parent",
    "ix_download_jobs_queue",
    "ix_download_jobs_updated",
    "uq_download_jobs_active_dedupe",
}
EXPECTED_TRACK_SOURCE_INDEXES = {
    "ix_track_sources_track",
    "uq_track_sources_identity",
}
EXPECTED_JOB_EVENT_INDEXES = {
    "ix_job_events_cursor",
    "ix_job_events_job",
}


def _snapshot_rows(connection: sqlite3.Connection, table: str) -> list[tuple[object, ...]]:
    """Capture durable rows before a SQLite table rebuild changes their table."""
    return connection.execute(f"SELECT * FROM {table} ORDER BY id").fetchall()


def _named_indexes(connection: sqlite3.Connection, table: str) -> set[str]:
    return {
        str(row[1])
        for row in connection.execute(f"PRAGMA index_list({table})").fetchall()
        if not str(row[1]).startswith("sqlite_autoindex")
    }


def _foreign_keys(connection: sqlite3.Connection, table: str) -> set[tuple[str, str, str, str]]:
    return {
        (str(row[3]), str(row[2]), str(row[4]), str(row[6]))
        for row in connection.execute(f"PRAGMA foreign_key_list({table})").fetchall()
    }


def _assert_radio_javan_rebuild_integrity(connection: sqlite3.Connection) -> None:
    """Check the relationships and indexes a constrained-table rebuild must retain."""
    assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    assert _named_indexes(connection, "track_sources") == EXPECTED_TRACK_SOURCE_INDEXES
    assert _named_indexes(connection, "download_jobs") == EXPECTED_DOWNLOAD_JOB_INDEXES
    assert _named_indexes(connection, "job_events") == EXPECTED_JOB_EVENT_INDEXES
    assert _foreign_keys(connection, "track_sources") == {
        ("track_id", "tracks", "id", "CASCADE"),
    }
    assert _foreign_keys(connection, "download_jobs") == {
        ("parent_job_id", "download_jobs", "id", "SET NULL"),
        ("result_track_id", "tracks", "id", "SET NULL"),
    }
    assert _foreign_keys(connection, "job_events") == {
        ("job_id", "download_jobs", "id", "CASCADE"),
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


def test_radio_javan_migration_rehearses_provenance_and_all_legacy_job_values(
    alembic_config: tuple[Config, Path],
) -> None:
    config, database_path = alembic_config

    command.upgrade(config, "0004_catalog_track_sources")
    with closing(sqlite3.connect(database_path)) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.executemany(
            """
            INSERT INTO tracks (
                id, title, artist, normalized_artist, normalized_title, normalized_album,
                file_relpath, file_size_bytes, content_sha256, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    f"legacy-track-{provider}",
                    f"Legacy {provider}",
                    "Fixture Artist",
                    "fixture artist",
                    f"legacy {provider}",
                    "",
                    f"music/{provider}.mp3",
                    1,
                    "a" * 64,
                    "2026-08-01T00:00:00Z",
                    "2026-08-01T00:00:00Z",
                )
                for provider in ("deezer", "spotdl", "yt_dlp")
            ],
        )
        connection.executemany(
            """
            INSERT INTO track_sources (
                id, track_id, provider, source_id, source_url, raw_fingerprint, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    f"legacy-source-{provider}",
                    "legacy-track-deezer",
                    provider,
                    f"{provider}-source",
                    f"https://example.test/{provider}",
                    f"{provider}-fingerprint",
                    "2026-08-01T00:00:00Z",
                )
                for provider in ("deezer", "spotify", "youtube", "apple", "musicbrainz")
            ],
        )
        connection.executemany(
            """
            INSERT INTO download_jobs (
                id, provider, source_type, source_ref, dedupe_key, request_json, candidate_json,
                state, phase, progress_percent, celery_task_id, lease_owner, lease_expires_at,
                heartbeat_at, parent_job_id, restart_count, cancel_requested_at, error_code,
                error_message, error_detail, result_track_id, version, created_at, started_at,
                finished_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "legacy-deezer-job",
                    "deezer",
                    "deezer_result",
                    "deezer-source",
                    "legacy-deezer-dedupe",
                    '{"origin":"legacy"}',
                    '{"candidate":"deezer"}',
                    "completed",
                    "completed",
                    100.0,
                    "celery-deezer",
                    "worker-a",
                    "2026-08-01T00:10:00Z",
                    "2026-08-01T00:05:00Z",
                    None,
                    0,
                    None,
                    None,
                    None,
                    None,
                    "legacy-track-deezer",
                    2,
                    "2026-08-01T00:00:00Z",
                    "2026-08-01T00:01:00Z",
                    "2026-08-01T00:02:00Z",
                    "2026-08-01T00:02:00Z",
                ),
                (
                    "legacy-spotdl-job",
                    "spotdl",
                    "spotify_track",
                    "spotify-source",
                    "legacy-spotdl-dedupe",
                    '{"origin":"legacy"}',
                    '{"candidate":"spotdl"}',
                    "completed",
                    "completed",
                    100.0,
                    "celery-spotdl",
                    "worker-b",
                    "2026-08-01T00:20:00Z",
                    "2026-08-01T00:15:00Z",
                    "legacy-deezer-job",
                    1,
                    "2026-08-01T00:14:00Z",
                    None,
                    None,
                    None,
                    "legacy-track-spotdl",
                    3,
                    "2026-08-01T00:10:00Z",
                    "2026-08-01T00:11:00Z",
                    "2026-08-01T00:12:00Z",
                    "2026-08-01T00:12:00Z",
                ),
                (
                    "legacy-ytdlp-job",
                    "yt_dlp",
                    "youtube_video",
                    "youtube-source",
                    "legacy-ytdlp-dedupe",
                    '{"origin":"legacy"}',
                    '{"candidate":"yt-dlp"}',
                    "completed",
                    "completed",
                    100.0,
                    "celery-ytdlp",
                    "worker-c",
                    "2026-08-01T00:30:00Z",
                    "2026-08-01T00:25:00Z",
                    "legacy-spotdl-job",
                    2,
                    "2026-08-01T00:24:00Z",
                    "previous_failure",
                    "Recovered after retry.",
                    "safe legacy detail",
                    "legacy-track-yt_dlp",
                    4,
                    "2026-08-01T00:20:00Z",
                    "2026-08-01T00:21:00Z",
                    "2026-08-01T00:22:00Z",
                    "2026-08-01T00:22:00Z",
                ),
            ],
        )
        connection.executemany(
            """
            INSERT INTO job_events (
                job_id, sequence, state, phase, progress_percent, payload_json, occurred_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "legacy-deezer-job",
                    1,
                    "completed",
                    "completed",
                    100.0,
                    '{"step":1}',
                    "2026-08-01T00:02:00Z",
                ),
                (
                    "legacy-spotdl-job",
                    1,
                    "completed",
                    "completed",
                    100.0,
                    '{"step":2}',
                    "2026-08-01T00:12:00Z",
                ),
                (
                    "legacy-ytdlp-job",
                    1,
                    "queued",
                    "queued",
                    0.0,
                    '{"step":3}',
                    "2026-08-01T00:20:00Z",
                ),
                (
                    "legacy-ytdlp-job",
                    2,
                    "completed",
                    "completed",
                    100.0,
                    '{"step":4}',
                    "2026-08-01T00:22:00Z",
                ),
            ],
        )
        connection.commit()
        legacy_jobs = _snapshot_rows(connection, "download_jobs")
        legacy_events = _snapshot_rows(connection, "job_events")
        legacy_sources = _snapshot_rows(connection, "track_sources")

    command.upgrade(config, "head")
    with closing(sqlite3.connect(database_path)) as connection:
        assert _snapshot_rows(connection, "download_jobs") == legacy_jobs
        assert _snapshot_rows(connection, "job_events") == legacy_events
        assert _snapshot_rows(connection, "track_sources") == legacy_sources
        _assert_radio_javan_rebuild_integrity(connection)
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
            INSERT INTO track_sources (
                id, track_id, provider, source_id, source_url, raw_fingerprint, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "radiojavan-source",
                "radiojavan-track",
                "radiojavan",
                "rj-source",
                "https://play.radiojavan.com/song/rj-source",
                "radiojavan-fingerprint",
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
        connection.execute(
            """
            INSERT INTO download_jobs (
                id, provider, source_type, source_ref, dedupe_key, request_json,
                state, phase, parent_job_id, result_track_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "radiojavan-child-job",
                "radiojavan",
                "radiojavan_track",
                "rj-source-child",
                "radiojavan-child-dedupe",
                "{}",
                "completed",
                "completed",
                "radiojavan-job",
                "radiojavan-track",
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
        connection.execute("DELETE FROM download_jobs WHERE id = 'radiojavan-child-job'")
        connection.commit()

    command.downgrade(config, "0004_catalog_track_sources")
    with closing(sqlite3.connect(database_path)) as connection:
        assert _snapshot_rows(connection, "download_jobs") == legacy_jobs
        assert _snapshot_rows(connection, "job_events") == legacy_events
        assert _snapshot_rows(connection, "track_sources") == legacy_sources
        _assert_radio_javan_rebuild_integrity(connection)
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO track_sources (
                    id, track_id, provider, source_id, source_url, created_at
                )
                VALUES ('radiojavan-after-down', 'legacy-track-deezer', 'radiojavan',
                        'rj-after-down', 'https://play.radiojavan.com/song/rj-after-down',
                        '2026-08-01T00:00:00Z')
                """
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO download_jobs (
                    id, provider, source_type, source_ref, dedupe_key, request_json,
                    state, phase, created_at, updated_at
                ) VALUES ('radiojavan-job-after-down', 'radiojavan', 'radiojavan_track',
                          'rj-after-down', 'radiojavan-after-down', '{}', 'completed',
                          'completed', '2026-08-01T00:00:00Z', '2026-08-01T00:00:00Z')
                """
            )

    command.upgrade(config, "head")
    with closing(sqlite3.connect(database_path)) as connection:
        assert _snapshot_rows(connection, "download_jobs") == legacy_jobs
        assert _snapshot_rows(connection, "job_events") == legacy_events
        assert _snapshot_rows(connection, "track_sources") == legacy_sources
        _assert_radio_javan_rebuild_integrity(connection)


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
