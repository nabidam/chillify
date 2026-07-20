"""SQLAlchemy mappings for the tables the Alembic migration owns.

The migration is authoritative for DDL; these mappings describe the same
columns so the ORM can read and write them. They deliberately declare no
`create_all` path — a table that appears without a migration is a bug.

Timestamps are stored as RFC 3339 UTC text exactly as the migration writes
them, so a value inserted by SQL and a value inserted by the ORM sort
identically as strings.
"""

from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for every mapped table."""


class ProfileRow(Base):
    __tablename__ = "profiles"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    name_folded: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)


class TrackRow(Base):
    __tablename__ = "tracks"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    artist: Mapped[str] = mapped_column(String, nullable=False)
    album: Mapped[str | None] = mapped_column(String)
    release_year: Mapped[int | None] = mapped_column(Integer)
    disc_number: Mapped[int | None] = mapped_column(Integer)
    track_number: Mapped[int | None] = mapped_column(Integer)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    normalized_artist: Mapped[str] = mapped_column(String, nullable=False)
    normalized_title: Mapped[str] = mapped_column(String, nullable=False)
    normalized_album: Mapped[str] = mapped_column(String, nullable=False)
    isrc: Mapped[str | None] = mapped_column(String)
    file_relpath: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    artwork_relpath: Mapped[str | None] = mapped_column(Text)
    mime_type: Mapped[str] = mapped_column(String, nullable=False, default="audio/mpeg")
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String, nullable=False)
    availability: Mapped[str] = mapped_column(String, nullable=False, default="available")
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)


class TrackSourceRow(Base):
    __tablename__ = "track_sources"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    track_id: Mapped[str] = mapped_column(
        String, ForeignKey("tracks.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String, nullable=False)
    source_id: Mapped[str | None] = mapped_column(String)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    raw_fingerprint: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
