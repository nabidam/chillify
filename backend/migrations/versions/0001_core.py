"""Core Chillify schema.

Owns the complete architecture DDL: profiles, tracks and sources, playlists,
the durable download queue and its event log, settings with seeded provider
defaults, artwork staging, API idempotency, and the media mutation journal.

Revision ID: 0001_core
Revises:
Create Date: 2026-07-20
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0001_core"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


UPGRADE_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE profiles (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL CHECK (length(name) BETWEEN 1 AND 40),
        name_folded TEXT NOT NULL UNIQUE,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE tracks (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL CHECK (length(title) BETWEEN 1 AND 200),
        artist TEXT NOT NULL CHECK (length(artist) BETWEEN 1 AND 200),
        album TEXT CHECK (album IS NULL OR length(album) BETWEEN 1 AND 200),
        release_year INTEGER CHECK (release_year IS NULL OR release_year BETWEEN 1000 AND 9999),
        disc_number INTEGER CHECK (disc_number IS NULL OR disc_number BETWEEN 1 AND 999),
        track_number INTEGER CHECK (track_number IS NULL OR track_number BETWEEN 1 AND 999),
        duration_ms INTEGER CHECK (duration_ms IS NULL OR duration_ms >= 0),
        normalized_artist TEXT NOT NULL,
        normalized_title TEXT NOT NULL,
        normalized_album TEXT NOT NULL,
        isrc TEXT,
        file_relpath TEXT NOT NULL UNIQUE,
        artwork_relpath TEXT,
        mime_type TEXT NOT NULL DEFAULT 'audio/mpeg' CHECK (mime_type = 'audio/mpeg'),
        file_size_bytes INTEGER NOT NULL CHECK (file_size_bytes >= 0),
        content_sha256 TEXT NOT NULL CHECK (length(content_sha256) = 64),
        availability TEXT NOT NULL DEFAULT 'available'
            CHECK (availability IN ('available', 'missing', 'mutating', 'recovery')),
        revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE (normalized_artist, normalized_title)
    )
    """,
    """
    CREATE UNIQUE INDEX uq_tracks_isrc
        ON tracks(lower(isrc)) WHERE isrc IS NOT NULL AND isrc <> ''
    """,
    "CREATE INDEX ix_tracks_artist ON tracks(normalized_artist)",
    "CREATE INDEX ix_tracks_title ON tracks(normalized_title)",
    "CREATE INDEX ix_tracks_album ON tracks(normalized_artist, normalized_album)",
    "CREATE INDEX ix_tracks_year ON tracks(release_year)",
    "CREATE INDEX ix_tracks_created ON tracks(created_at DESC)",
    """
    CREATE TABLE track_sources (
        id TEXT PRIMARY KEY,
        track_id TEXT NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
        provider TEXT NOT NULL CHECK (provider IN ('deezer', 'spotify', 'youtube')),
        source_id TEXT,
        source_url TEXT NOT NULL,
        raw_fingerprint TEXT,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE UNIQUE INDEX uq_track_sources_identity
        ON track_sources(provider, source_id)
        WHERE source_id IS NOT NULL AND source_id <> ''
    """,
    "CREATE INDEX ix_track_sources_track ON track_sources(track_id)",
    """
    CREATE TABLE playlists (
        id TEXT PRIMARY KEY,
        profile_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
        name TEXT NOT NULL CHECK (length(name) BETWEEN 1 AND 100),
        name_folded TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
        UNIQUE (profile_id, name_folded)
    )
    """,
    "CREATE INDEX ix_playlists_profile ON playlists(profile_id, updated_at DESC)",
    """
    CREATE TABLE playlist_tracks (
        playlist_id TEXT NOT NULL REFERENCES playlists(id) ON DELETE CASCADE,
        track_id TEXT NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
        position INTEGER NOT NULL CHECK (position >= 0),
        added_at TEXT NOT NULL,
        PRIMARY KEY (playlist_id, track_id),
        UNIQUE (playlist_id, position)
    )
    """,
    "CREATE INDEX ix_playlist_tracks_track ON playlist_tracks(track_id)",
    """
    CREATE TABLE download_jobs (
        id TEXT PRIMARY KEY,
        provider TEXT NOT NULL CHECK (provider IN ('deezer', 'spotdl', 'yt_dlp')),
        source_type TEXT NOT NULL
            CHECK (source_type IN ('deezer_result', 'spotify_track', 'youtube_video')),
        source_ref TEXT NOT NULL,
        dedupe_key TEXT NOT NULL,
        request_json TEXT NOT NULL,
        candidate_json TEXT,
        state TEXT NOT NULL
            CHECK (state IN ('queued', 'running', 'completed', 'failed', 'cancelled')),
        phase TEXT NOT NULL
            CHECK (phase IN (
                'accepted', 'inspecting', 'queued', 'restarted', 'downloading',
                'converting', 'enriching', 'tagging', 'organizing', 'completed',
                'failed', 'cancelled'
            )),
        progress_percent REAL CHECK (
            progress_percent IS NULL OR
            (progress_percent >= 0.0 AND progress_percent <= 100.0)
        ),
        celery_task_id TEXT,
        lease_owner TEXT,
        lease_expires_at TEXT,
        heartbeat_at TEXT,
        parent_job_id TEXT REFERENCES download_jobs(id) ON DELETE SET NULL,
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
    """,
    """
    CREATE UNIQUE INDEX uq_download_jobs_active_dedupe
        ON download_jobs(dedupe_key)
        WHERE state IN ('queued', 'running')
    """,
    "CREATE INDEX ix_download_jobs_queue ON download_jobs(state, created_at)",
    "CREATE INDEX ix_download_jobs_updated ON download_jobs(updated_at DESC)",
    "CREATE INDEX ix_download_jobs_parent ON download_jobs(parent_job_id)",
    """
    CREATE TABLE job_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        job_id TEXT NOT NULL REFERENCES download_jobs(id) ON DELETE CASCADE,
        sequence INTEGER NOT NULL CHECK (sequence >= 1),
        state TEXT NOT NULL,
        phase TEXT NOT NULL,
        progress_percent REAL,
        payload_json TEXT NOT NULL DEFAULT '{}',
        occurred_at TEXT NOT NULL,
        UNIQUE (job_id, sequence)
    )
    """,
    "CREATE INDEX ix_job_events_cursor ON job_events(id)",
    "CREATE INDEX ix_job_events_job ON job_events(job_id, sequence)",
    """
    CREATE TABLE settings (
        key TEXT PRIMARY KEY CHECK (
            key IN (
                'proxy', 'provider.deezer', 'provider.spotdl',
                'provider.yt_dlp', 'provider.lastfm'
            )
        ),
        public_json TEXT NOT NULL DEFAULT '{}',
        secret_ciphertext BLOB,
        revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
        updated_at TEXT NOT NULL
    )
    """,
    """
    INSERT INTO settings (key, public_json, secret_ciphertext, revision, updated_at) VALUES
        ('proxy', '{"configured":false}', NULL, 1,
            strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
        ('provider.deezer', '{"enabled":true}', NULL, 1,
            strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
        ('provider.spotdl', '{"enabled":true}', NULL, 1,
            strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
        ('provider.yt_dlp', '{"enabled":true}', NULL, 1,
            strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
        ('provider.lastfm', '{"enabled":false,"configured":false}', NULL, 1,
            strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
    """,
    """
    CREATE TABLE artwork_stages (
        id TEXT PRIMARY KEY,
        file_relpath TEXT NOT NULL UNIQUE,
        mime_type TEXT NOT NULL CHECK (mime_type = 'image/jpeg'),
        content_sha256 TEXT NOT NULL CHECK (length(content_sha256) = 64),
        size_bytes INTEGER NOT NULL CHECK (size_bytes BETWEEN 1 AND 10485760),
        origin TEXT NOT NULL CHECK (origin IN ('upload', 'url', 'lastfm')),
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        consumed_at TEXT
    )
    """,
    "CREATE INDEX ix_artwork_stages_expiry ON artwork_stages(expires_at, consumed_at)",
    """
    CREATE TABLE api_idempotency (
        scope TEXT NOT NULL,
        key TEXT NOT NULL,
        request_sha256 TEXT NOT NULL CHECK (length(request_sha256) = 64),
        status_code INTEGER NOT NULL,
        response_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        PRIMARY KEY (scope, key)
    )
    """,
    "CREATE INDEX ix_api_idempotency_expiry ON api_idempotency(expires_at)",
    """
    CREATE TABLE media_mutations (
        id TEXT PRIMARY KEY,
        track_id TEXT,
        operation TEXT NOT NULL CHECK (operation IN ('publish', 'edit', 'delete')),
        state TEXT NOT NULL CHECK (
            state IN (
                'prepared', 'files_staged', 'active_files_removed',
                'db_committed', 'finalized', 'rolled_back', 'recovery_required'
            )
        ),
        old_record_json TEXT NOT NULL,
        new_record_json TEXT,
        recovery_json TEXT NOT NULL,
        error_detail TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX ix_media_mutations_recovery
        ON media_mutations(state, updated_at)
        WHERE state NOT IN ('finalized', 'rolled_back')
    """,
)

# Dropped children before parents. SQLite drops a table's own indexes with it.
DOWNGRADE_TABLES: tuple[str, ...] = (
    "media_mutations",
    "api_idempotency",
    "artwork_stages",
    "settings",
    "job_events",
    "download_jobs",
    "playlist_tracks",
    "playlists",
    "track_sources",
    "tracks",
    "profiles",
)


def upgrade() -> None:
    # exec_driver_sql sends the DDL verbatim. op.execute would parse `:false`
    # inside the seeded JSON literals as a bind parameter.
    connection = op.get_bind()
    for statement in UPGRADE_STATEMENTS:
        connection.exec_driver_sql(statement)


def downgrade() -> None:
    connection = op.get_bind()
    for table in DOWNGRADE_TABLES:
        connection.exec_driver_sql(f"DROP TABLE IF EXISTS {table}")
