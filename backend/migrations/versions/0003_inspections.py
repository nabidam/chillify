"""Track cancellable link inspections.

Revision ID: 0003_inspections
Revises: 0002_settings_keys
Create Date: 2026-07-28
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0003_inspections"
down_revision: str | None = "0002_settings_keys"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    connection.exec_driver_sql(
        """
        CREATE TABLE inspections (
            id TEXT PRIMARY KEY,
            url TEXT NOT NULL,
            mode TEXT NOT NULL CHECK (mode IN ('fast', 'thorough')),
            phase TEXT NOT NULL CHECK (phase IN (
                'reading_spotify', 'matching_spotdl', 'inspecting_youtube',
                'cancelled', 'expired', 'failed', 'done'
            )),
            provider TEXT,
            started_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            cancel_requested_at TEXT,
            result_json TEXT,
            error_json TEXT
        )
        """
    )
    connection.exec_driver_sql("CREATE INDEX ix_inspections_expiry ON inspections(expires_at)")


def downgrade() -> None:
    op.get_bind().exec_driver_sql("DROP TABLE inspections")
