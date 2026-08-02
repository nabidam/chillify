"""Add Radio Javan provider and source identities to existing checks."""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0005_radio_javan"
down_revision: str | None = "0004_catalog_track_sources"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TRACK_SOURCE_PROVIDERS = "'deezer', 'spotify', 'youtube', 'apple', 'musicbrainz'"
_RADIO_TRACK_SOURCE_PROVIDERS = f"{_TRACK_SOURCE_PROVIDERS}, 'radiojavan'"
_JOB_PROVIDERS = "'deezer', 'spotdl', 'yt_dlp'"
_RADIO_JOB_PROVIDERS = f"{_JOB_PROVIDERS}, 'radiojavan'"
_SOURCE_TYPES = "'deezer_result', 'spotify_track', 'youtube_video'"
_RADIO_SOURCE_TYPES = "'deezer_result', 'radiojavan_track', 'spotify_track', 'youtube_video'"


def _create_track_sources(name: str, providers: str) -> None:
    connection = op.get_bind()
    connection.exec_driver_sql(
        f"""
        CREATE TABLE {name} (
            id TEXT PRIMARY KEY,
            track_id TEXT NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
            provider TEXT NOT NULL CHECK (provider IN ({providers})),
            source_id TEXT,
            source_url TEXT NOT NULL,
            raw_fingerprint TEXT,
            created_at TEXT NOT NULL
        )
        """
    )


def _rebuild_track_sources(providers: str) -> None:
    connection = op.get_bind()
    _create_track_sources("track_sources_radio_javan", providers)
    connection.exec_driver_sql(
        """
        INSERT INTO track_sources_radio_javan
            (id, track_id, provider, source_id, source_url, raw_fingerprint, created_at)
        SELECT id, track_id, provider, source_id, source_url, raw_fingerprint, created_at
        FROM track_sources
        """
    )
    connection.exec_driver_sql("DROP TABLE track_sources")
    connection.exec_driver_sql("ALTER TABLE track_sources_radio_javan RENAME TO track_sources")
    _create_track_source_indexes()


def _create_track_source_indexes() -> None:
    connection = op.get_bind()
    connection.exec_driver_sql(
        """
        CREATE UNIQUE INDEX uq_track_sources_identity
        ON track_sources(provider, source_id)
        WHERE source_id IS NOT NULL AND source_id <> ''
        """
    )
    connection.exec_driver_sql("CREATE INDEX ix_track_sources_track ON track_sources(track_id)")


def _create_download_jobs(name: str, providers: str, source_types: str) -> None:
    connection = op.get_bind()
    connection.exec_driver_sql(
        f"""
        CREATE TABLE {name} (
            id TEXT PRIMARY KEY,
            provider TEXT NOT NULL CHECK (provider IN ({providers})),
            source_type TEXT NOT NULL CHECK (source_type IN ({source_types})),
            source_ref TEXT NOT NULL,
            dedupe_key TEXT NOT NULL,
            request_json TEXT NOT NULL,
            candidate_json TEXT,
            state TEXT NOT NULL
                CHECK (state IN ('queued', 'running', 'completed', 'failed', 'cancelled')),
            phase TEXT NOT NULL
                CHECK (
                    phase IN (
                        'accepted', 'inspecting', 'queued', 'restarted', 'downloading',
                        'converting', 'enriching', 'tagging', 'organizing', 'completed',
                        'failed', 'cancelled'
                    )
                ),
            progress_percent REAL CHECK (
                progress_percent IS NULL OR
                (progress_percent >= 0.0 AND progress_percent <= 100.0)
            ),
            celery_task_id TEXT,
            lease_owner TEXT,
            lease_expires_at TEXT,
            heartbeat_at TEXT,
            parent_job_id TEXT REFERENCES {name}(id) ON DELETE SET NULL,
            restart_count INTEGER NOT NULL DEFAULT 0 CHECK (restart_count >= 0),
            cancel_requested_at TEXT,
            error_code TEXT,
            error_message TEXT,
            error_detail TEXT,
            result_track_id TEXT REFERENCES tracks(id) ON DELETE SET NULL,
            version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
            created_at TEXT NOT NULL,
            started_at TEXT,
            finished_at TEXT,
            updated_at TEXT NOT NULL
        )
        """
    )


def _copy_download_jobs(destination: str) -> None:
    connection = op.get_bind()
    connection.exec_driver_sql(
        f"""
        INSERT INTO {destination} (
            id, provider, source_type, source_ref, dedupe_key, request_json, candidate_json,
            state, phase, progress_percent, celery_task_id, lease_owner, lease_expires_at,
            heartbeat_at, parent_job_id, restart_count, cancel_requested_at, error_code,
            error_message, error_detail, result_track_id, version, created_at, started_at,
            finished_at, updated_at
        )
        SELECT id, provider, source_type, source_ref, dedupe_key, request_json, candidate_json,
            state, phase, progress_percent, celery_task_id, lease_owner, lease_expires_at,
            heartbeat_at, parent_job_id, restart_count, cancel_requested_at, error_code,
            error_message, error_detail, result_track_id, version, created_at, started_at,
            finished_at, updated_at
        FROM download_jobs
        """
    )


def _create_download_job_indexes() -> None:
    connection = op.get_bind()
    connection.exec_driver_sql(
        """
        CREATE UNIQUE INDEX uq_download_jobs_active_dedupe
        ON download_jobs(dedupe_key)
        WHERE state IN ('queued', 'running')
        """
    )
    connection.exec_driver_sql(
        "CREATE INDEX ix_download_jobs_queue ON download_jobs(state, created_at)"
    )
    connection.exec_driver_sql(
        "CREATE INDEX ix_download_jobs_updated ON download_jobs(updated_at DESC)"
    )
    connection.exec_driver_sql(
        "CREATE INDEX ix_download_jobs_parent ON download_jobs(parent_job_id)"
    )


def _create_job_events(name: str, job_table: str) -> None:
    connection = op.get_bind()
    connection.exec_driver_sql(
        f"""
        CREATE TABLE {name} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL REFERENCES {job_table}(id) ON DELETE CASCADE,
            sequence INTEGER NOT NULL CHECK (sequence >= 1),
            state TEXT NOT NULL,
            phase TEXT NOT NULL,
            progress_percent REAL,
            payload_json TEXT NOT NULL DEFAULT '{{}}',
            occurred_at TEXT NOT NULL,
            UNIQUE (job_id, sequence)
        )
        """
    )


def _copy_job_events(destination: str) -> None:
    connection = op.get_bind()
    connection.exec_driver_sql(
        f"""
        INSERT INTO {destination}
            (id, job_id, sequence, state, phase, progress_percent, payload_json, occurred_at)
        SELECT id, job_id, sequence, state, phase, progress_percent, payload_json, occurred_at
        FROM job_events
        """
    )


def _create_job_event_indexes() -> None:
    connection = op.get_bind()
    connection.exec_driver_sql("CREATE INDEX ix_job_events_cursor ON job_events(id)")
    connection.exec_driver_sql("CREATE INDEX ix_job_events_job ON job_events(job_id, sequence)")


def _rebuild_download_jobs(providers: str, source_types: str) -> None:
    connection = op.get_bind()
    _create_download_jobs("download_jobs_radio_javan", providers, source_types)
    _copy_download_jobs("download_jobs_radio_javan")
    _create_job_events("job_events_radio_javan", "download_jobs_radio_javan")
    _copy_job_events("job_events_radio_javan")
    connection.exec_driver_sql("DROP TABLE job_events")
    connection.exec_driver_sql("DROP TABLE download_jobs")
    connection.exec_driver_sql("ALTER TABLE download_jobs_radio_javan RENAME TO download_jobs")
    connection.exec_driver_sql("ALTER TABLE job_events_radio_javan RENAME TO job_events")
    _create_download_job_indexes()
    _create_job_event_indexes()


def upgrade() -> None:
    _rebuild_track_sources(_RADIO_TRACK_SOURCE_PROVIDERS)
    _rebuild_download_jobs(_RADIO_JOB_PROVIDERS, _RADIO_SOURCE_TYPES)


def downgrade() -> None:
    connection = op.get_bind()
    if connection.exec_driver_sql(
        "SELECT count(*) FROM track_sources WHERE provider = 'radiojavan'"
    ).scalar_one():
        raise RuntimeError("Cannot downgrade while Radio Javan provenance exists.")
    if connection.exec_driver_sql(
        """
        SELECT count(*) FROM download_jobs
        WHERE provider = 'radiojavan' OR source_type = 'radiojavan_track'
        """
    ).scalar_one():
        raise RuntimeError("Cannot downgrade while Radio Javan jobs exist.")
    _rebuild_download_jobs(_JOB_PROVIDERS, _SOURCE_TYPES)
    _rebuild_track_sources(_TRACK_SOURCE_PROVIDERS)
