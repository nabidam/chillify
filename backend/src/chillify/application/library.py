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
from chillify.domain.models import (
    AlbumSummary,
    ArtistSummary,
    Availability,
    LibrarySort,
    Page,
    Profile,
    Track,
    TrackId,
    YearSummary,
)
from chillify.domain.normalization import (
    decode_album_key,
    decode_artist_key,
    decode_year_key,
    validate_profile_name,
)
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


def _display_of(values: Iterator[str]) -> str | None:
    """The deterministic representative raw value for a context identity.

    The lexicographic minimum matches the `func.min` the browse grid uses, so
    a context card and the view it opens never disagree about the name. Absent
    when the context holds no tracks.
    """
    return min(values, default=None)


@dataclass(frozen=True, slots=True)
class ArtistContext:
    """The identity and server-ordered tracks the S6 artist view plays."""

    normalized_artist: str
    display_name: str
    tracks: tuple[Track, ...]


@dataclass(frozen=True, slots=True)
class AlbumContext:
    """The identity and disc/track-ordered tracks the S7 album view plays."""

    normalized_artist: str
    normalized_album: str
    display_album: str | None
    display_artist: str
    tracks: tuple[Track, ...]


@dataclass(frozen=True, slots=True)
class YearContext:
    """The identity and server-ordered tracks the S8 year view plays."""

    release_year: int | None
    tracks: tuple[Track, ...]


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

    # -- browse contexts --------------------------------------------------

    def list_artists(self, *, query: str | None = None) -> tuple[ArtistSummary, ...]:
        with self._transaction() as session:
            return TrackRepository(session).list_artists(query=query)

    def list_albums(self, *, query: str | None = None) -> tuple[AlbumSummary, ...]:
        with self._transaction() as session:
            return TrackRepository(session).list_albums(query=query)

    def list_years(self) -> tuple[YearSummary, ...]:
        with self._transaction() as session:
            return TrackRepository(session).list_years()

    def artist_context(self, artist_key: str) -> ArtistContext:
        """Resolve one artist key to its ordered tracks and display identity.

        A key that decodes canonically but names no local track is not an
        error: S6 shows an empty artist reached from stale metadata rather than
        a failure, so an empty context is returned with the decoded identity.
        """
        normalized_artist = decode_artist_key(artist_key)
        with self._transaction() as session:
            tracks = TrackRepository(session).tracks_for_artist(normalized_artist)
        return ArtistContext(
            normalized_artist=normalized_artist,
            display_name=_display_of(track.artist for track in tracks) or normalized_artist,
            tracks=tracks,
        )

    def album_context(self, album_key: str) -> AlbumContext:
        """Resolve one album key to its disc/track-ordered tracks and identity."""
        normalized_artist, normalized_album = decode_album_key(album_key)
        with self._transaction() as session:
            tracks = TrackRepository(session).tracks_for_album(normalized_artist, normalized_album)
        return AlbumContext(
            normalized_artist=normalized_artist,
            normalized_album=normalized_album,
            display_album=_display_of(track.album for track in tracks if track.album is not None),
            display_artist=_display_of(track.artist for track in tracks) or normalized_artist,
            tracks=tracks,
        )

    def year_context(self, year_key: str) -> YearContext:
        """Resolve one year key to its ordered tracks; `unknown` is first-class."""
        release_year = decode_year_key(year_key)
        with self._transaction() as session:
            tracks = TrackRepository(session).tracks_for_year(release_year)
        return YearContext(release_year=release_year, tracks=tracks)

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
