"""Repositories translating between mapped rows and domain values.

Nothing above this module sees a `Row` type, and nothing below it sees a
domain entity. Third-party exceptions are translated into domain errors here,
once, at this boundary.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import Select, or_, select, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import InstrumentedAttribute, Session

from chillify.domain.errors import DuplicateRecordError
from chillify.domain.models import (
    Availability,
    LibrarySort,
    Page,
    Profile,
    ProfileId,
    Track,
    TrackId,
    from_rfc3339,
    to_rfc3339,
)
from chillify.domain.normalization import fold_name, normalize_key
from chillify.domain.ordering import decode_cursor, encode_cursor
from chillify.infrastructure.db.models import ProfileRow, TrackRow

LIBRARY_PAGE_LIMIT_MAX = 100
LIBRARY_PAGE_LIMIT_DEFAULT = 50


def new_id() -> str:
    """UUIDv7: time-ordered, so primary keys and insertion order agree."""
    return str(uuid.uuid7())


def _to_profile(row: ProfileRow) -> Profile:
    return Profile(
        id=ProfileId(row.id),
        name=row.name,
        name_folded=row.name_folded,
        created_at=from_rfc3339(row.created_at),
        updated_at=from_rfc3339(row.updated_at),
    )


def _to_track(row: TrackRow) -> Track:
    return Track(
        id=TrackId(row.id),
        title=row.title,
        artist=row.artist,
        album=row.album,
        release_year=row.release_year,
        disc_number=row.disc_number,
        track_number=row.track_number,
        duration_ms=row.duration_ms,
        normalized_artist=row.normalized_artist,
        normalized_title=row.normalized_title,
        normalized_album=row.normalized_album,
        isrc=row.isrc,
        file_relpath=row.file_relpath,
        artwork_relpath=row.artwork_relpath,
        mime_type=row.mime_type,
        file_size_bytes=row.file_size_bytes,
        content_sha256=row.content_sha256,
        availability=Availability(row.availability),
        revision=row.revision,
        created_at=from_rfc3339(row.created_at),
        updated_at=from_rfc3339(row.updated_at),
    )


class ProfileRepository:
    """Reads and writes household profiles.

    Profiles have no rename or delete endpoint by design, so this repository
    deliberately offers neither.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_profiles(self) -> tuple[Profile, ...]:
        rows = self._session.scalars(select(ProfileRow).order_by(ProfileRow.name_folded)).all()
        return tuple(_to_profile(row) for row in rows)

    def create(self, name: str, *, now: datetime | None = None) -> Profile:
        """Insert one profile, or report the existing household name.

        The unique index is the race-safe guard: a pre-check would still lose to
        a concurrent insert from the other browser tab in the house.
        """
        moment = to_rfc3339(now or datetime.now(UTC))
        row = ProfileRow(
            id=new_id(),
            name=name,
            name_folded=fold_name(name),
            created_at=moment,
            updated_at=moment,
        )
        self._session.add(row)
        try:
            self._session.flush()
        except IntegrityError as exc:
            self._session.rollback()
            raise DuplicateRecordError(
                "A profile with that name already exists in this household.", field="name"
            ) from exc
        return _to_profile(row)


class TrackRepository:
    """Reads local tracks and records the one state the API may change alone."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, track_id: TrackId) -> Track | None:
        row = self._session.get(TrackRow, str(track_id))
        return None if row is None else _to_track(row)

    def mark_missing(self, track_id: TrackId, *, now: datetime | None = None) -> None:
        """Record that a managed file has vanished from under a live row.

        This is the one track mutation with no media step: the file is already
        gone, so there is nothing to stage, move, or roll back.
        """
        row = self._session.get(TrackRow, str(track_id))
        if row is None or row.availability == Availability.MISSING:
            return
        row.availability = Availability.MISSING
        row.revision += 1
        row.updated_at = to_rfc3339(now or datetime.now(UTC))
        self._session.flush()

    def list_tracks(
        self,
        *,
        query: str | None = None,
        sort: LibrarySort = LibrarySort.RECENT,
        cursor: str | None = None,
        limit: int = LIBRARY_PAGE_LIMIT_DEFAULT,
    ) -> Page[Track]:
        """One keyset page of local tracks in the requested order.

        Keyset rather than offset paging: the library changes underneath a
        reader whenever a download completes, and an offset page would then
        repeat or skip rows.
        """
        bounded = max(1, min(limit, LIBRARY_PAGE_LIMIT_MAX))
        statement = self._apply_search(select(TrackRow), query)
        statement = self._apply_order(statement, sort)
        if cursor is not None:
            statement = self._apply_cursor(statement, sort, cursor)

        # One extra row answers "is there a next page" without a second query.
        rows = self._session.scalars(statement.limit(bounded + 1)).all()
        tracks = [_to_track(row) for row in rows[:bounded]]
        next_cursor = encode_cursor(tracks[-1], sort) if len(rows) > bounded and tracks else None
        return Page(items=tuple(tracks), next_cursor=next_cursor)

    def _apply_search(
        self, statement: Select[tuple[TrackRow]], query: str | None
    ) -> Select[tuple[TrackRow]]:
        """Match the normalized query against the normalized columns.

        Searching the stored normalized columns is what makes "bjork" find
        "Björk"; matching the displayed columns would not.
        """
        if query is None:
            return statement
        normalized = normalize_key(query, fallback="")
        if not normalized:
            return statement
        pattern = f"%{normalized}%"
        return statement.where(
            or_(
                TrackRow.normalized_artist.like(pattern),
                TrackRow.normalized_title.like(pattern),
                TrackRow.normalized_album.like(pattern),
            )
        )

    def _sort_column(self, sort: LibrarySort) -> InstrumentedAttribute[str]:
        match sort:
            case LibrarySort.RECENT:
                return TrackRow.created_at
            case LibrarySort.TITLE:
                return TrackRow.normalized_title
            case LibrarySort.ARTIST:
                return TrackRow.normalized_artist

    def _apply_order(
        self, statement: Select[tuple[TrackRow]], sort: LibrarySort
    ) -> Select[tuple[TrackRow]]:
        column = self._sort_column(sort)
        if sort is LibrarySort.RECENT:
            # Newest first: the landing view answers "what did we just add".
            return statement.order_by(column.desc(), TrackRow.id.desc())
        return statement.order_by(column.asc(), TrackRow.id.asc())

    def _apply_cursor(
        self, statement: Select[tuple[TrackRow]], sort: LibrarySort, cursor: str
    ) -> Select[tuple[TrackRow]]:
        key, track_id = decode_cursor(cursor, sort)
        column = self._sort_column(sort)
        pair = tuple_(column, TrackRow.id)
        bound = (key, track_id)
        if sort is LibrarySort.RECENT:
            return statement.where(pair < bound)
        return statement.where(pair > bound)
