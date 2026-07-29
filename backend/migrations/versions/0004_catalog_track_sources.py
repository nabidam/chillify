"""Allow catalog-discovery identities in track provenance.

Revision ID: 0004_catalog_track_sources
Revises: 0003_inspections
Create Date: 2026-07-29

MusicBrainz and Apple Music results are acquired through an existing adapter,
but the resulting library record must preserve the catalog that identified the
track. SQLite cannot widen this CHECK constraint in place, so rebuild the
small provenance table while preserving every existing row and index.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0004_catalog_track_sources"
down_revision: str | None = "0003_inspections"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ORIGINAL_PROVIDERS = "'deezer', 'spotify', 'youtube'"
_CATALOG_PROVIDERS = f"{_ORIGINAL_PROVIDERS}, 'apple', 'musicbrainz'"


def _create_track_sources_table(name: str, providers: str) -> str:
    return f"""
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


def _rebuild_track_sources(*, destination: str, providers: str) -> None:
    connection = op.get_bind()
    connection.exec_driver_sql(_create_track_sources_table(destination, providers))
    connection.exec_driver_sql(
        f"""
        INSERT INTO {destination} (id, track_id, provider, source_id, source_url,
                                   raw_fingerprint, created_at)
        SELECT id, track_id, provider, source_id, source_url, raw_fingerprint, created_at
        FROM track_sources
        """
    )
    connection.exec_driver_sql("DROP TABLE track_sources")
    connection.exec_driver_sql(f"ALTER TABLE {destination} RENAME TO track_sources")
    connection.exec_driver_sql(
        """
        CREATE UNIQUE INDEX uq_track_sources_identity
        ON track_sources(provider, source_id)
        WHERE source_id IS NOT NULL AND source_id <> ''
        """
    )
    connection.exec_driver_sql("CREATE INDEX ix_track_sources_track ON track_sources(track_id)")


def upgrade() -> None:
    _rebuild_track_sources(
        destination="track_sources_with_catalogs", providers=_CATALOG_PROVIDERS
    )


def downgrade() -> None:
    connection = op.get_bind()
    new_provider_count = connection.exec_driver_sql(
        "SELECT count(*) FROM track_sources WHERE provider IN ('apple', 'musicbrainz')"
    ).scalar_one()
    if new_provider_count:
        raise RuntimeError("Cannot downgrade while Apple Music or MusicBrainz provenance exists.")
    _rebuild_track_sources(
        destination="track_sources_without_catalogs", providers=_ORIGINAL_PROVIDERS
    )
