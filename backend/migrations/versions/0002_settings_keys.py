"""Add Spotify inspection settings.

SQLite cannot widen the settings key CHECK in place.  Rebuild the table inside
the migration transaction, preserving every pre-existing row byte-for-byte,
then seed the two cycle-002 rows.  The downgrade removes those rows before it
narrows the CHECK for the same reason.

Revision ID: 0002_settings_keys
Revises: 0001_core
Create Date: 2026-07-28
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0002_settings_keys"
down_revision: str | None = "0001_core"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ORIGINAL_KEYS = """
    'proxy', 'provider.deezer', 'provider.spotdl',
    'provider.yt_dlp', 'provider.lastfm'
"""
_EXTENDED_KEYS = f"""
    {_ORIGINAL_KEYS}, 'inspection', 'provider.spotify_api'
"""


def _create_settings_table(name: str, keys: str) -> str:
    return f"""
    CREATE TABLE {name} (
        key TEXT PRIMARY KEY CHECK (key IN ({keys})),
        public_json TEXT NOT NULL DEFAULT '{{}}',
        secret_ciphertext BLOB,
        revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
        updated_at TEXT NOT NULL
    )
    """


def _rebuild_settings(*, destination: str, keys: str) -> None:
    connection = op.get_bind()
    connection.exec_driver_sql(_create_settings_table(destination, keys))
    connection.exec_driver_sql(
        f"""
        INSERT INTO {destination} (key, public_json, secret_ciphertext, revision, updated_at)
        SELECT key, public_json, secret_ciphertext, revision, updated_at FROM settings
        """
    )
    connection.exec_driver_sql("DROP TABLE settings")
    connection.exec_driver_sql(f"ALTER TABLE {destination} RENAME TO settings")


def upgrade() -> None:
    _rebuild_settings(destination="settings_with_inspection", keys=_EXTENDED_KEYS)
    connection = op.get_bind()
    connection.exec_driver_sql(
        """
        INSERT INTO settings (key, public_json, secret_ciphertext, revision, updated_at) VALUES
            ('inspection',
             '{"mode":"fast","timeout_spotify_s":8,"timeout_spotdl_s":150,"timeout_ytdlp_s":60}',
             NULL, 1, strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
            ('provider.spotify_api', '{"configured":false}', NULL, 1,
             strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        """
    )


def downgrade() -> None:
    connection = op.get_bind()
    # These keys must go before the copy because the original CHECK rejects
    # them.  Keeping this explicit makes rollback safe for upgraded databases.
    connection.exec_driver_sql(
        "DELETE FROM settings WHERE key IN ('inspection', 'provider.spotify_api')"
    )
    _rebuild_settings(destination="settings_without_inspection", keys=_ORIGINAL_KEYS)
