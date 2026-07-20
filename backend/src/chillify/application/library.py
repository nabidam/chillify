"""Profile, library, and stream use cases.

Each public method owns one transaction boundary. Routes call these; they never
open a session or touch a repository themselves.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from chillify.domain.errors import RecordNotFoundError, TrackFileMissingError
from chillify.domain.models import Availability, LibrarySort, Page, Profile, Track, TrackId
from chillify.domain.normalization import validate_profile_name
from chillify.infrastructure.db.repositories import (
    LIBRARY_PAGE_LIMIT_DEFAULT,
    ProfileRepository,
    TrackRepository,
)
from chillify.infrastructure.media.storage import resolve_managed_path

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class StreamTarget:
    """Everything the transport layer needs to serve one managed MP3."""

    track_id: TrackId
    path: Path
    media_type: str
    etag: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class LibraryService:
    """Use cases over profiles, local tracks, and their managed files."""

    session_factory: sessionmaker[Session]
    music_root: Path

    @contextmanager
    def _transaction(self) -> Iterator[Session]:
        session = self.session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # -- profiles ---------------------------------------------------------

    def list_profiles(self) -> tuple[Profile, ...]:
        with self._transaction() as session:
            return ProfileRepository(session).list_profiles()

    def create_profile(self, raw_name: str) -> Profile:
        """Validate and store one household profile.

        Validation happens before the transaction opens so a rejected name never
        holds a write lock on the shared SQLite file.
        """
        name = validate_profile_name(raw_name)
        with self._transaction() as session:
            profile = ProfileRepository(session).create(name)
        logger.info("profile created", extra={"profile_id": str(profile.id)})
        return profile

    # -- library ----------------------------------------------------------

    def list_tracks(
        self,
        *,
        query: str | None = None,
        sort: LibrarySort = LibrarySort.RECENT,
        cursor: str | None = None,
        limit: int = LIBRARY_PAGE_LIMIT_DEFAULT,
    ) -> Page[Track]:
        with self._transaction() as session:
            return TrackRepository(session).list_tracks(
                query=query, sort=sort, cursor=cursor, limit=limit
            )

    def get_track(self, track_id: TrackId) -> Track:
        with self._transaction() as session:
            track = TrackRepository(session).get(track_id)
        if track is None:
            raise RecordNotFoundError("That track is not in this library.")
        return track

    # -- streaming --------------------------------------------------------

    def open_stream(self, track_id: TrackId) -> StreamTarget:
        """Resolve one track to a servable file beneath the music root.

        A row whose file has vanished is marked `missing` in its own committed
        transaction before the failure is raised, so the very next library read
        already shows the row as unplayable rather than repeating the surprise.
        """
        track = self.get_track(track_id)
        if track.availability is not Availability.AVAILABLE:
            raise TrackFileMissingError(
                "That track's file is not currently playable.",
                context={"availability": str(track.availability)},
            )

        path = resolve_managed_path(self.music_root, track.file_relpath)
        if not path.is_file():
            self._mark_missing(track_id)
            raise TrackFileMissingError("That track's file is no longer on disk.")

        stat_result = path.stat()
        return StreamTarget(
            track_id=track.id,
            path=path,
            media_type=track.mime_type,
            # Revision covers metadata edits that rewrite tags in place; size
            # and mtime cover any change the database did not author.
            etag=f'"{track.revision}-{stat_result.st_size}-{int(stat_result.st_mtime)}"',
            size_bytes=stat_result.st_size,
        )

    def _mark_missing(self, track_id: TrackId) -> None:
        with self._transaction() as session:
            TrackRepository(session).mark_missing(track_id, now=datetime.now(UTC))
        logger.warning("managed file absent; track marked missing", extra={"track_id": track_id})
