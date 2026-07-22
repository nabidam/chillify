"""Repositories translating between mapped rows and domain values.

Nothing above this module sees a `Row` type, and nothing below it sees a
domain entity. Third-party exceptions are translated into domain errors here,
once, at this boundary.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import Select, func, or_, select, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import InstrumentedAttribute, Session

from chillify.domain.errors import (
    ArtworkStageUnavailableError,
    DuplicateRecordError,
    RecordChangedError,
    RecordNotFoundError,
)
from chillify.domain.jobs import (
    DownloadJob,
    InvalidJobTransitionError,
    JobEvent,
    JobId,
    JobPhase,
    JobProvider,
    JobState,
    SourceType,
    assert_transition,
)
from chillify.domain.models import (
    AUDIO_MIME_TYPE,
    ArtworkOrigin,
    ArtworkStage,
    ArtworkStageId,
    Availability,
    LibrarySort,
    Page,
    Playlist,
    PlaylistDetail,
    PlaylistId,
    Profile,
    ProfileId,
    Track,
    TrackDetail,
    TrackId,
    TrackSource,
    from_rfc3339,
    normalize_metadata,
    to_rfc3339,
)
from chillify.domain.normalization import fold_name, normalize_key
from chillify.domain.ordering import decode_cursor, encode_cursor
from chillify.infrastructure.db.models import (
    ApiIdempotencyRow,
    ArtworkStageRow,
    DownloadJobRow,
    JobEventRow,
    MediaMutationRow,
    PlaylistRow,
    PlaylistTrackRow,
    ProfileRow,
    SettingsRow,
    TrackRow,
    TrackSourceRow,
)

LIBRARY_PAGE_LIMIT_MAX = 100
LIBRARY_PAGE_LIMIT_DEFAULT = 50
JOB_PAGE_LIMIT_MAX = 100
JOB_PAGE_LIMIT_DEFAULT = 50

# One replay burst after a reconnect. A browser that has been closed for a week
# gets the most recent window and a fresh snapshot, not a week of history.
JOB_EVENT_REPLAY_LIMIT = 500

# How long a claimed job stays leased without a heartbeat. Reconciliation
# (Task 7) treats an expired lease as an interrupted run.
JOB_LEASE_SECONDS = 120

IDEMPOTENCY_RETENTION_HOURS = 24

# The phase each terminal state commits with, so a finished job never keeps the
# phase it happened to be in when it stopped.
_TERMINAL_PHASE = {
    JobState.COMPLETED: JobPhase.COMPLETED,
    JobState.FAILED: JobPhase.FAILED,
    JobState.CANCELLED: JobPhase.CANCELLED,
}


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


def _to_source(row: TrackSourceRow) -> TrackSource:
    return TrackSource(
        provider=row.provider,
        source_id=row.source_id,
        source_url=row.source_url,
    )


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

    def find_duplicate(
        self,
        *,
        provider: str,
        source_id: str | None,
        isrc: str | None,
        normalized_artist: str,
        normalized_title: str,
    ) -> Track | None:
        """Resolve whether this candidate is already in the library.

        The order is exact before approximate — provider identity, then ISRC,
        then the normalized artist/title pair — so a track that carries a real
        identifier is never matched by a coincidental name.
        """
        if source_id:
            row = self._session.scalars(
                select(TrackRow)
                .join(TrackSourceRow, TrackSourceRow.track_id == TrackRow.id)
                .where(TrackSourceRow.provider == provider)
                .where(TrackSourceRow.source_id == source_id)
            ).first()
            if row is not None:
                return _to_track(row)

        if isrc:
            row = self._session.scalars(
                select(TrackRow).where(func.lower(TrackRow.isrc) == isrc.lower())
            ).first()
            if row is not None:
                return _to_track(row)

        row = self._session.scalars(
            select(TrackRow)
            .where(TrackRow.normalized_artist == normalized_artist)
            .where(TrackRow.normalized_title == normalized_title)
        ).first()
        return None if row is None else _to_track(row)

    def create(
        self,
        *,
        title: str,
        artist: str,
        album: str | None,
        release_year: int | None,
        disc_number: int | None,
        track_number: int | None,
        duration_ms: int | None,
        isrc: str | None,
        file_relpath: str,
        artwork_relpath: str | None,
        file_size_bytes: int,
        content_sha256: str,
        source_provider: str,
        source_id: str | None,
        source_url: str,
        raw_fingerprint: str | None,
        now: datetime,
    ) -> Track:
        """Insert one published track and the source identity it came from.

        Both rows are written here so the caller's single transaction is what
        makes a track and its provenance appear together, or not at all.
        """
        moment = to_rfc3339(now)
        normalized = normalize_metadata(artist=artist, title=title, album=album)
        row = TrackRow(
            id=new_id(),
            title=title,
            artist=artist,
            album=album,
            release_year=release_year,
            disc_number=disc_number,
            track_number=track_number,
            duration_ms=duration_ms,
            normalized_artist=normalized.normalized_artist,
            normalized_title=normalized.normalized_title,
            normalized_album=normalized.normalized_album,
            isrc=isrc,
            file_relpath=file_relpath,
            artwork_relpath=artwork_relpath,
            mime_type=AUDIO_MIME_TYPE,
            file_size_bytes=file_size_bytes,
            content_sha256=content_sha256,
            availability=str(Availability.AVAILABLE),
            revision=1,
            created_at=moment,
            updated_at=moment,
        )
        self._session.add(row)
        self._session.add(
            TrackSourceRow(
                id=new_id(),
                track_id=row.id,
                provider=source_provider,
                source_id=source_id,
                source_url=source_url,
                raw_fingerprint=raw_fingerprint,
                created_at=moment,
            )
        )
        try:
            self._session.flush()
        except IntegrityError as exc:
            self._session.rollback()
            raise DuplicateRecordError("That track is already in this library.") from exc
        return _to_track(row)

    def get_detail(self, track_id: TrackId) -> TrackDetail | None:
        """One track plus the provider identities it was acquired from."""
        row = self._session.get(TrackRow, str(track_id))
        if row is None:
            return None
        sources = self._session.scalars(
            select(TrackSourceRow)
            .where(TrackSourceRow.track_id == str(track_id))
            .order_by(TrackSourceRow.created_at, TrackSourceRow.id)
        ).all()
        return TrackDetail(track=_to_track(row), sources=tuple(_to_source(s) for s in sources))

    def find_conflict(
        self, *, track_id: TrackId, normalized_artist: str, normalized_title: str
    ) -> Track | None:
        """Another track already holding this edit's normalized identity.

        Checked before the mutation touches a file so a colliding rename is
        reported as the duplicate it is, rather than surfacing as an integrity
        error after the old file has already been moved.
        """
        row = self._session.scalars(
            select(TrackRow)
            .where(TrackRow.normalized_artist == normalized_artist)
            .where(TrackRow.normalized_title == normalized_title)
            .where(TrackRow.id != str(track_id))
        ).first()
        return None if row is None else _to_track(row)

    def begin_mutation(self, track_id: TrackId, *, expected_revision: int) -> Track:
        """Mark the track unplayable for the duration of one edit.

        The revision is deliberately not bumped: it is the value the caller
        already matched with `If-Match`, and the edit's own commit is what
        earns the next one.
        """
        row = self._require_track(track_id)
        if row.revision != expected_revision:
            raise RecordChangedError(
                "Somebody else saved this track first. Reload it and try again.",
                context={"current_revision": row.revision},
            )
        row.availability = str(Availability.MUTATING)
        self._session.flush()
        return _to_track(row)

    def end_mutation(self, track_id: TrackId) -> None:
        """Return a track to `available` after an edit rolled back."""
        row = self._session.get(TrackRow, str(track_id))
        if row is None or row.availability != str(Availability.MUTATING):
            return
        row.availability = str(Availability.AVAILABLE)
        self._session.flush()

    def apply_edit(
        self,
        track_id: TrackId,
        *,
        expected_revision: int,
        title: str,
        artist: str,
        album: str | None,
        release_year: int | None,
        disc_number: int | None,
        track_number: int | None,
        file_relpath: str,
        artwork_relpath: str | None,
        file_size_bytes: int,
        content_sha256: str,
        now: datetime,
    ) -> Track:
        """Write the complete corrected record in one statement.

        Every field is assigned, including the derived normalized columns: they
        are this normalizer's cache, so an edit that changed the title and left
        them alone would leave the track findable only under its old name.
        """
        row = self._require_track(track_id)
        if row.revision != expected_revision:
            raise RecordChangedError(
                "Somebody else saved this track first. Reload it and try again.",
                context={"current_revision": row.revision},
            )

        normalized = normalize_metadata(artist=artist, title=title, album=album)
        row.title = title
        row.artist = artist
        row.album = album
        row.release_year = release_year
        row.disc_number = disc_number
        row.track_number = track_number
        row.normalized_artist = normalized.normalized_artist
        row.normalized_title = normalized.normalized_title
        row.normalized_album = normalized.normalized_album
        row.file_relpath = file_relpath
        row.artwork_relpath = artwork_relpath
        row.file_size_bytes = file_size_bytes
        row.content_sha256 = content_sha256
        row.availability = str(Availability.AVAILABLE)
        row.revision += 1
        row.updated_at = to_rfc3339(now)
        try:
            self._session.flush()
        except IntegrityError as exc:
            self._session.rollback()
            raise DuplicateRecordError(
                "Another track in this library already has that artist and title."
            ) from exc
        return _to_track(row)

    def _require_track(self, track_id: TrackId) -> TrackRow:
        row = self._session.get(TrackRow, str(track_id))
        if row is None:
            raise RecordNotFoundError("That track is not in this library.")
        return row

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


def _to_playlist(row: PlaylistRow, track_count: int) -> Playlist:
    return Playlist(
        id=PlaylistId(row.id),
        profile_id=ProfileId(row.profile_id),
        name=row.name,
        name_folded=row.name_folded,
        track_count=track_count,
        revision=row.revision,
        created_at=from_rfc3339(row.created_at),
        updated_at=from_rfc3339(row.updated_at),
    )


class PlaylistRepository:
    """Reads and writes one profile's playlists and their saved order.

    A playlist belongs to exactly one profile. Every read is scoped by that
    profile, so one household member's list can never be addressed through
    another's — not as a permission check, which this app deliberately has
    none of, but because a playlist means nothing outside its owner.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_for_profile(self, profile_id: ProfileId) -> tuple[Playlist, ...]:
        """Every playlist of one profile, most recently changed first."""
        self._require_profile(profile_id)
        rows = self._session.scalars(
            select(PlaylistRow)
            .where(PlaylistRow.profile_id == str(profile_id))
            .order_by(PlaylistRow.updated_at.desc(), PlaylistRow.id.desc())
        ).all()
        counts = self._track_counts(tuple(row.id for row in rows))
        return tuple(_to_playlist(row, counts.get(row.id, 0)) for row in rows)

    def create(self, profile_id: ProfileId, name: str, *, now: datetime | None = None) -> Playlist:
        """Insert one playlist, or report the name this profile already uses.

        The `(profile_id, name_folded)` unique index is the race-safe guard, so
        two tabs pressing Create at once produce one playlist and one clear
        conflict rather than two identically named lists.
        """
        self._require_profile(profile_id)
        moment = to_rfc3339(now or datetime.now(UTC))
        row = PlaylistRow(
            id=new_id(),
            profile_id=str(profile_id),
            name=name,
            name_folded=fold_name(name),
            created_at=moment,
            updated_at=moment,
            revision=1,
        )
        self._session.add(row)
        try:
            self._session.flush()
        except IntegrityError as exc:
            self._session.rollback()
            raise DuplicateRecordError(
                "This profile already has a playlist with that name.", field="name"
            ) from exc
        return _to_playlist(row, 0)

    def get_detail(self, playlist_id: PlaylistId) -> PlaylistDetail:
        """One playlist and its tracks in saved order."""
        row = self._require(playlist_id)
        rows = self._session.execute(
            select(TrackRow)
            .join(PlaylistTrackRow, PlaylistTrackRow.track_id == TrackRow.id)
            .where(PlaylistTrackRow.playlist_id == str(playlist_id))
            .order_by(PlaylistTrackRow.position, TrackRow.id)
        ).scalars()
        tracks = tuple(_to_track(track_row) for track_row in rows)
        return PlaylistDetail(playlist=_to_playlist(row, len(tracks)), tracks=tracks)

    def rename(
        self,
        playlist_id: PlaylistId,
        *,
        name: str,
        expected_revision: int,
        now: datetime | None = None,
    ) -> Playlist:
        row = self._require(playlist_id)
        if row.revision != expected_revision:
            raise RecordChangedError(
                "Somebody else changed this playlist first. Reload it and try again.",
                context={"current_revision": row.revision},
            )
        row.name = name
        row.name_folded = fold_name(name)
        row.revision += 1
        row.updated_at = to_rfc3339(now or datetime.now(UTC))
        try:
            self._session.flush()
        except IntegrityError as exc:
            self._session.rollback()
            raise DuplicateRecordError(
                "This profile already has a playlist with that name.", field="name"
            ) from exc
        return _to_playlist(row, self._track_counts((row.id,)).get(row.id, 0))

    def add_track(
        self,
        playlist_id: PlaylistId,
        track_id: TrackId,
        *,
        expected_revision: int,
        now: datetime | None = None,
    ) -> PlaylistDetail:
        """Append one track to the end of the saved order.

        A track already in the playlist is a conflict rather than a silent
        no-op: the person pressed Add expecting a change, and reporting nothing
        happened is more honest than pretending something did.
        """
        row = self._require(playlist_id)
        if row.revision != expected_revision:
            raise RecordChangedError(
                "Somebody else changed this playlist first. Reload it and try again.",
                context={"current_revision": row.revision},
            )
        if self._session.get(TrackRow, str(track_id)) is None:
            raise RecordNotFoundError("That track is not in this library.")

        moment = to_rfc3339(now or datetime.now(UTC))
        highest = self._session.scalar(
            select(func.max(PlaylistTrackRow.position)).where(
                PlaylistTrackRow.playlist_id == str(playlist_id)
            )
        )
        position = 0 if highest is None else highest + 1
        self._session.add(
            PlaylistTrackRow(
                playlist_id=str(playlist_id),
                track_id=str(track_id),
                position=position,
                added_at=moment,
            )
        )
        row.revision += 1
        row.updated_at = moment
        try:
            self._session.flush()
        except IntegrityError as exc:
            self._session.rollback()
            raise DuplicateRecordError(
                "That track is already in this playlist.", field="track_id"
            ) from exc
        return self.get_detail(playlist_id)

    def _track_counts(self, playlist_ids: tuple[str, ...]) -> dict[str, int]:
        if not playlist_ids:
            return {}
        rows = self._session.execute(
            select(PlaylistTrackRow.playlist_id, func.count())
            .where(PlaylistTrackRow.playlist_id.in_(playlist_ids))
            .group_by(PlaylistTrackRow.playlist_id)
        ).all()
        return {str(playlist_id): int(count) for playlist_id, count in rows}

    def _require(self, playlist_id: PlaylistId) -> PlaylistRow:
        row = self._session.get(PlaylistRow, str(playlist_id))
        if row is None:
            raise RecordNotFoundError("That playlist does not exist.")
        return row

    def _require_profile(self, profile_id: ProfileId) -> ProfileRow:
        row = self._session.get(ProfileRow, str(profile_id))
        if row is None:
            raise RecordNotFoundError("That profile is not in this household.")
        return row


def _to_artwork_stage(row: ArtworkStageRow) -> ArtworkStage:
    return ArtworkStage(
        id=ArtworkStageId(row.id),
        file_relpath=row.file_relpath,
        mime_type=row.mime_type,
        content_sha256=row.content_sha256,
        size_bytes=row.size_bytes,
        origin=ArtworkOrigin(row.origin),
        created_at=from_rfc3339(row.created_at),
        expires_at=from_rfc3339(row.expires_at),
        consumed_at=_optional_moment(row.consumed_at),
    )


class ArtworkStageRepository:
    """Short-lived, single-use cover images awaiting a save.

    A stage is not a track change. It exists so the browser can show the person
    the cover they picked before anything is committed, and so the save that
    finally commits has one already-validated file to consume.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def create(
        self,
        *,
        stage_id: str,
        file_relpath: str,
        mime_type: str,
        content_sha256: str,
        size_bytes: int,
        origin: ArtworkOrigin,
        now: datetime,
        lifetime: timedelta,
    ) -> ArtworkStage:
        row = ArtworkStageRow(
            id=stage_id,
            file_relpath=file_relpath,
            mime_type=mime_type,
            content_sha256=content_sha256,
            size_bytes=size_bytes,
            origin=str(origin),
            created_at=to_rfc3339(now),
            expires_at=to_rfc3339(now + lifetime),
            consumed_at=None,
        )
        self._session.add(row)
        self._session.flush()
        return _to_artwork_stage(row)

    def require_consumable(self, stage_id: ArtworkStageId, *, now: datetime) -> ArtworkStage:
        """The stage this save may consume, or the one failure all three cases share."""
        row = self._session.get(ArtworkStageRow, str(stage_id))
        if row is None:
            raise ArtworkStageUnavailableError(
                "That cover image is no longer available. Choose it again."
            )
        stage = _to_artwork_stage(row)
        if not stage.is_consumable(now=now):
            raise ArtworkStageUnavailableError(
                "That cover image is no longer available. Choose it again."
            )
        return stage

    def consume(self, stage_id: ArtworkStageId, *, now: datetime) -> None:
        """Mark the stage used, inside the same transaction as the save itself."""
        row = self._session.get(ArtworkStageRow, str(stage_id))
        if row is None or row.consumed_at is not None:
            raise ArtworkStageUnavailableError(
                "That cover image is no longer available. Choose it again."
            )
        row.consumed_at = to_rfc3339(now)
        self._session.flush()

    def expired(self, *, now: datetime) -> tuple[ArtworkStage, ...]:
        """Unconsumed stages past their hour, for opportunistic cleanup."""
        rows = self._session.scalars(
            select(ArtworkStageRow)
            .where(ArtworkStageRow.consumed_at.is_(None))
            .where(ArtworkStageRow.expires_at <= to_rfc3339(now))
        ).all()
        return tuple(_to_artwork_stage(row) for row in rows)

    def delete(self, stage_id: ArtworkStageId) -> None:
        row = self._session.get(ArtworkStageRow, str(stage_id))
        if row is not None:
            self._session.delete(row)
            self._session.flush()


class MediaMutationRepository:
    """The recovery journal for every change that moves managed media.

    A row here is written before the filesystem is touched and removed only
    after the change is complete, so an interrupted edit always leaves a record
    saying what was half-done and which files can undo it.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def open_edit(
        self,
        *,
        track_id: TrackId,
        old_record: dict[str, object],
        new_record: dict[str, object],
        now: datetime,
    ) -> str:
        mutation_id = new_id()
        moment = to_rfc3339(now)
        self._session.add(
            MediaMutationRow(
                id=mutation_id,
                track_id=str(track_id),
                operation="edit",
                state="prepared",
                old_record_json=json.dumps(old_record, separators=(",", ":"), sort_keys=True),
                new_record_json=json.dumps(new_record, separators=(",", ":"), sort_keys=True),
                recovery_json="{}",
                created_at=moment,
                updated_at=moment,
            )
        )
        self._session.flush()
        return mutation_id

    def advance(
        self,
        mutation_id: str,
        *,
        state: str,
        now: datetime,
        recovery: dict[str, str] | None = None,
        error_detail: str | None = None,
    ) -> None:
        row = self._session.get(MediaMutationRow, mutation_id)
        if row is None:
            raise RecordNotFoundError("That change is no longer being tracked.")
        row.state = state
        if recovery is not None:
            row.recovery_json = json.dumps(recovery, separators=(",", ":"), sort_keys=True)
        if error_detail is not None:
            row.error_detail = error_detail
        row.updated_at = to_rfc3339(now)
        self._session.flush()

    def close(self, mutation_id: str) -> None:
        """Remove a finished journal row; nothing is left to recover from it."""
        row = self._session.get(MediaMutationRow, mutation_id)
        if row is not None:
            self._session.delete(row)
            self._session.flush()


def _to_job(row: DownloadJobRow) -> DownloadJob:
    return DownloadJob(
        id=JobId(row.id),
        provider=JobProvider(row.provider),
        source_type=SourceType(row.source_type),
        source_ref=row.source_ref,
        dedupe_key=row.dedupe_key,
        state=JobState(row.state),
        phase=JobPhase(row.phase),
        progress_percent=row.progress_percent,
        celery_task_id=row.celery_task_id,
        parent_job_id=None if row.parent_job_id is None else JobId(row.parent_job_id),
        restart_count=row.restart_count,
        cancel_requested_at=_optional_moment(row.cancel_requested_at),
        error_code=row.error_code,
        error_message=row.error_message,
        result_track_id=None if row.result_track_id is None else TrackId(row.result_track_id),
        version=row.version,
        created_at=from_rfc3339(row.created_at),
        started_at=_optional_moment(row.started_at),
        finished_at=_optional_moment(row.finished_at),
        updated_at=from_rfc3339(row.updated_at),
    )


def _to_event(row: JobEventRow) -> JobEvent:
    payload = json.loads(row.payload_json)
    return JobEvent(
        id=row.id,
        job_id=JobId(row.job_id),
        sequence=row.sequence,
        state=JobState(row.state),
        phase=JobPhase(row.phase),
        progress_percent=row.progress_percent,
        payload=payload if isinstance(payload, dict) else {},
        occurred_at=from_rfc3339(row.occurred_at),
    )


def _optional_moment(value: str | None) -> datetime | None:
    return None if value is None else from_rfc3339(value)


class DownloadJobRepository:
    """Reads and writes durable acquisition jobs and their replayable events.

    Every write that changes a job also appends the event describing it, in the
    same transaction. A state the browser was told about but the database never
    committed is the one failure this design exists to prevent.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    # -- reads ------------------------------------------------------------

    def get(self, job_id: JobId) -> DownloadJob | None:
        row = self._session.get(DownloadJobRow, str(job_id))
        return None if row is None else _to_job(row)

    def list_jobs(
        self,
        *,
        states: tuple[JobState, ...] | None = None,
        cursor: str | None = None,
        limit: int = JOB_PAGE_LIMIT_DEFAULT,
    ) -> Page[DownloadJob]:
        """One keyset page of jobs, newest first.

        The cursor is the last job's ID rather than an encoded column pair:
        IDs are UUIDv7, so their descending order is the descending creation
        order the listing already uses.
        """
        bounded = max(1, min(limit, JOB_PAGE_LIMIT_MAX))
        statement = select(DownloadJobRow).order_by(DownloadJobRow.id.desc())
        if states:
            statement = statement.where(DownloadJobRow.state.in_([str(state) for state in states]))
        if cursor is not None:
            statement = statement.where(DownloadJobRow.id < cursor)

        rows = self._session.scalars(statement.limit(bounded + 1)).all()
        jobs = [_to_job(row) for row in rows[:bounded]]
        next_cursor = str(jobs[-1].id) if len(rows) > bounded and jobs else None
        return Page(items=tuple(jobs), next_cursor=next_cursor)

    def list_events(self, job_id: JobId) -> tuple[JobEvent, ...]:
        rows = self._session.scalars(
            select(JobEventRow)
            .where(JobEventRow.job_id == str(job_id))
            .order_by(JobEventRow.sequence)
        ).all()
        return tuple(_to_event(row) for row in rows)

    def events_after(
        self, event_id: int, *, limit: int = JOB_EVENT_REPLAY_LIMIT
    ) -> tuple[JobEvent, ...]:
        """Durable events after an SSE cursor, oldest first.

        This is what makes a reconnect lossless: the browser sends the last ID
        it rendered and receives exactly what it missed.
        """
        rows = self._session.scalars(
            select(JobEventRow)
            .where(JobEventRow.id > event_id)
            .order_by(JobEventRow.id)
            .limit(limit)
        ).all()
        return tuple(_to_event(row) for row in rows)

    def latest_event_id(self) -> int:
        return self._session.scalar(select(func.max(JobEventRow.id))) or 0

    def find_active_by_dedupe_key(self, dedupe_key: str) -> DownloadJob | None:
        row = self._session.scalars(
            select(DownloadJobRow)
            .where(DownloadJobRow.dedupe_key == dedupe_key)
            .where(DownloadJobRow.state.in_([str(JobState.QUEUED), str(JobState.RUNNING)]))
        ).first()
        return None if row is None else _to_job(row)

    # -- writes -----------------------------------------------------------

    def create(
        self,
        *,
        provider: JobProvider,
        source_type: SourceType,
        source_ref: str,
        dedupe_key: str,
        request: dict[str, object],
        candidate: dict[str, object] | None,
        now: datetime,
    ) -> DownloadJob:
        """Insert one queued job and its first event.

        The partial unique index is the race-safe guard: a pre-check would
        still lose to the other browser tab in the house pressing Download at
        the same moment.
        """
        moment = to_rfc3339(now)
        row = DownloadJobRow(
            id=new_id(),
            provider=str(provider),
            source_type=str(source_type),
            source_ref=source_ref,
            dedupe_key=dedupe_key,
            request_json=json.dumps(request, separators=(",", ":"), sort_keys=True),
            candidate_json=(
                None
                if candidate is None
                else json.dumps(candidate, separators=(",", ":"), sort_keys=True)
            ),
            state=str(JobState.QUEUED),
            phase=str(JobPhase.ACCEPTED),
            progress_percent=None,
            restart_count=0,
            version=1,
            created_at=moment,
            updated_at=moment,
        )
        self._session.add(row)
        try:
            self._session.flush()
        except IntegrityError as exc:
            self._session.rollback()
            raise DuplicateRecordError(
                "That track is already queued or downloading.", field="source_ref"
            ) from exc

        self._append_event(
            job_id=JobId(row.id),
            state=JobState.QUEUED,
            phase=JobPhase.ACCEPTED,
            progress_percent=None,
            payload={},
            now=now,
        )
        return _to_job(row)

    def read_request(self, job_id: JobId) -> dict[str, object]:
        """The immutable submitted request. The worker reconstructs input from this."""
        row = self._require(job_id)
        payload = json.loads(row.request_json)
        return payload if isinstance(payload, dict) else {}

    def read_candidate(self, job_id: JobId) -> dict[str, object] | None:
        row = self._require(job_id)
        if row.candidate_json is None:
            return None
        payload = json.loads(row.candidate_json)
        return payload if isinstance(payload, dict) else None

    def claim(
        self, job_id: JobId, *, owner: str, now: datetime, lease_seconds: int
    ) -> DownloadJob | None:
        """Take the per-job lease by a version-and-state transition.

        Returns None when the job is not claimable — already running elsewhere,
        already finished, or cancelled while it waited. The caller then does
        nothing, which is the correct response to a duplicate delivery.
        """
        row = self._require(job_id)
        if row.state != str(JobState.QUEUED) or row.cancel_requested_at is not None:
            return None

        assert_transition(JobState(row.state), JobState.RUNNING)
        moment = to_rfc3339(now)
        row.state = str(JobState.RUNNING)
        row.phase = str(JobPhase.DOWNLOADING)
        row.lease_owner = owner
        row.lease_expires_at = to_rfc3339(now + timedelta(seconds=lease_seconds))
        row.heartbeat_at = moment
        row.started_at = row.started_at or moment
        row.version += 1
        row.updated_at = moment
        self._session.flush()

        self._append_event(
            job_id=job_id,
            state=JobState.RUNNING,
            phase=JobPhase.DOWNLOADING,
            progress_percent=None,
            payload={},
            now=now,
        )
        return _to_job(row)

    def record_phase(
        self,
        job_id: JobId,
        *,
        phase: JobPhase,
        progress_percent: float | None,
        now: datetime,
        payload: dict[str, str | int | float | bool] | None = None,
        lease_seconds: int = JOB_LEASE_SECONDS,
    ) -> JobEvent:
        """Advance a running job's phase and append the matching event.

        Progress is monotonic within a phase: a provider that reports a smaller
        percentage than it already did keeps the larger one, because a bar that
        walks backwards reads as a fault the person did not cause.
        """
        row = self._require(job_id)
        moment = to_rfc3339(now)
        if phase != JobPhase(row.phase):
            row.progress_percent = progress_percent
        elif progress_percent is not None:
            row.progress_percent = max(progress_percent, row.progress_percent or 0.0)

        row.phase = str(phase)
        row.heartbeat_at = moment
        row.lease_expires_at = to_rfc3339(now + timedelta(seconds=lease_seconds))
        row.version += 1
        row.updated_at = moment
        self._session.flush()

        return self._append_event(
            job_id=job_id,
            state=JobState(row.state),
            phase=phase,
            progress_percent=row.progress_percent,
            payload=payload or {},
            now=now,
        )

    def finish(
        self,
        job_id: JobId,
        *,
        state: JobState,
        now: datetime,
        result_track_id: TrackId | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        error_detail: str | None = None,
        payload: dict[str, str | int | float | bool] | None = None,
    ) -> DownloadJob:
        """Commit one terminal transition and its event together."""
        row = self._require(job_id)
        assert_transition(JobState(row.state), state)
        moment = to_rfc3339(now)
        phase = _TERMINAL_PHASE[state]

        row.state = str(state)
        row.phase = str(phase)
        row.result_track_id = None if result_track_id is None else str(result_track_id)
        row.error_code = error_code
        row.error_message = error_message
        row.error_detail = error_detail
        row.lease_owner = None
        row.lease_expires_at = None
        row.progress_percent = 100.0 if state is JobState.COMPLETED else row.progress_percent
        row.finished_at = moment
        row.version += 1
        row.updated_at = moment
        self._session.flush()

        self._append_event(
            job_id=job_id,
            state=state,
            phase=phase,
            progress_percent=row.progress_percent,
            payload=payload or {},
            now=now,
        )
        return _to_job(row)

    # -- reconciliation ---------------------------------------------------

    def list_stale_running(self, *, now: datetime) -> tuple[DownloadJob, ...]:
        """Running jobs whose worker lease has lapsed, oldest first.

        A live worker refreshes `lease_expires_at` on every phase; a lapsed or
        absent lease therefore means the run stopped without committing a
        terminal state — an interrupted job recovery must resume.
        """
        moment = to_rfc3339(now)
        rows = self._session.scalars(
            select(DownloadJobRow)
            .where(DownloadJobRow.state == str(JobState.RUNNING))
            .where(
                or_(
                    DownloadJobRow.lease_expires_at.is_(None),
                    DownloadJobRow.lease_expires_at <= moment,
                )
            )
            .order_by(DownloadJobRow.id)
        ).all()
        return tuple(_to_job(row) for row in rows)

    def list_queued(self) -> tuple[DownloadJob, ...]:
        """Every queued job, oldest first, for republication in submit order."""
        rows = self._session.scalars(
            select(DownloadJobRow)
            .where(DownloadJobRow.state == str(JobState.QUEUED))
            .order_by(DownloadJobRow.id)
        ).all()
        return tuple(_to_job(row) for row in rows)

    def active_job_ids(self) -> set[str]:
        """IDs of jobs still queued or running — the workspaces worth keeping."""
        rows = self._session.scalars(
            select(DownloadJobRow.id).where(
                DownloadJobRow.state.in_([str(JobState.QUEUED), str(JobState.RUNNING)])
            )
        ).all()
        return {str(job_id) for job_id in rows}

    def restart(self, job_id: JobId, *, now: datetime) -> DownloadJob:
        """Return an interrupted running job to the queue as a restart.

        The lease is cleared, `restart_count` increments, and the phase becomes
        `restarted` so the browser can tell a recovered job from a first
        attempt. Progress is dropped: the next run reports its own.
        """
        row = self._require(job_id)
        assert_transition(JobState(row.state), JobState.QUEUED)
        moment = to_rfc3339(now)
        row.state = str(JobState.QUEUED)
        row.phase = str(JobPhase.RESTARTED)
        row.progress_percent = None
        row.lease_owner = None
        row.lease_expires_at = None
        row.heartbeat_at = None
        row.restart_count += 1
        row.version += 1
        row.updated_at = moment
        self._session.flush()

        self._append_event(
            job_id=job_id,
            state=JobState.QUEUED,
            phase=JobPhase.RESTARTED,
            progress_percent=None,
            payload={"restart_count": row.restart_count},
            now=now,
        )
        return _to_job(row)

    # -- cancel and retry -------------------------------------------------

    def request_cancel(self, job_id: JobId, *, expected_version: int, now: datetime) -> DownloadJob:
        """Cancel a queued job outright, or ask a running one to stop.

        A finished job cannot be cancelled, and a stale `version` means the
        caller acted on an out-of-date view; both are refused before anything
        changes. A queued job commits `cancelled` here because there is no run
        to interrupt; a running job only records `cancel_requested_at`, and the
        worker commits the terminal state when it next checks.
        """
        row = self._require(job_id)
        if JobState(row.state) in (JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED):
            raise InvalidJobTransitionError(
                "That download has already finished and cannot be cancelled.",
                context={"from_state": row.state, "to_state": str(JobState.CANCELLED)},
            )
        if row.version != expected_version:
            raise RecordChangedError(
                "That download changed since you last saw it. Reload and try again.",
                context={"current_version": row.version},
            )
        if JobState(row.state) is JobState.QUEUED:
            return self.finish(job_id, state=JobState.CANCELLED, now=now)

        moment = to_rfc3339(now)
        row.cancel_requested_at = moment
        row.version += 1
        row.updated_at = moment
        self._session.flush()
        return _to_job(row)

    def retry(self, job_id: JobId, *, now: datetime) -> DownloadJob:
        """Queue a fresh attempt linked to a finished failed or cancelled job.

        The original chronology is immutable, so this never reopens it: a new
        job carries the same immutable request and candidate, points back at its
        parent, and starts its own history. A completed job has nothing to
        retry and is refused.
        """
        parent = self._require(job_id)
        if JobState(parent.state) not in (JobState.FAILED, JobState.CANCELLED):
            raise InvalidJobTransitionError(
                "Only a failed or cancelled download can be retried.",
                context={"from_state": parent.state, "to_state": str(JobState.QUEUED)},
            )
        moment = to_rfc3339(now)
        row = DownloadJobRow(
            id=new_id(),
            provider=parent.provider,
            source_type=parent.source_type,
            source_ref=parent.source_ref,
            dedupe_key=parent.dedupe_key,
            request_json=parent.request_json,
            candidate_json=parent.candidate_json,
            state=str(JobState.QUEUED),
            phase=str(JobPhase.ACCEPTED),
            progress_percent=None,
            parent_job_id=parent.id,
            restart_count=0,
            version=1,
            created_at=moment,
            updated_at=moment,
        )
        self._session.add(row)
        try:
            self._session.flush()
        except IntegrityError as exc:
            self._session.rollback()
            raise DuplicateRecordError(
                "That track is already queued or downloading.", field="source_ref"
            ) from exc

        self._append_event(
            job_id=JobId(row.id),
            state=JobState.QUEUED,
            phase=JobPhase.ACCEPTED,
            progress_percent=None,
            payload={"parent_job_id": parent.id},
            now=now,
        )
        return _to_job(row)

    def record_dispatch(self, job_id: JobId, *, celery_task_id: str, now: datetime) -> None:
        """Remember which Celery delivery carries this job.

        Recorded after the durable insert commits: a broker that never accepts
        the message leaves a queued job for reconciliation, not a lost one.
        """
        row = self._require(job_id)
        row.celery_task_id = celery_task_id
        row.updated_at = to_rfc3339(now)
        self._session.flush()

    def _append_event(
        self,
        *,
        job_id: JobId,
        state: JobState,
        phase: JobPhase,
        progress_percent: float | None,
        payload: dict[str, str | int | float | bool],
        now: datetime,
    ) -> JobEvent:
        next_sequence = (
            self._session.scalar(
                select(func.max(JobEventRow.sequence)).where(JobEventRow.job_id == str(job_id))
            )
            or 0
        ) + 1
        row = JobEventRow(
            job_id=str(job_id),
            sequence=next_sequence,
            state=str(state),
            phase=str(phase),
            progress_percent=progress_percent,
            payload_json=json.dumps(payload, separators=(",", ":"), sort_keys=True),
            occurred_at=to_rfc3339(now),
        )
        self._session.add(row)
        self._session.flush()
        return _to_event(row)

    def _require(self, job_id: JobId) -> DownloadJobRow:
        row = self._session.get(DownloadJobRow, str(job_id))
        if row is None:
            raise RecordNotFoundError("That download is not in this queue.")
        return row


class IdempotencyRepository:
    """Stored responses for mutations that carry an `Idempotency-Key`.

    Reusing a key with a different body is a conflict rather than a second
    mutation: the request hash is what stops one key from authorizing work the
    person never submitted.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def find(self, *, scope: str, key: str, request_sha256: str, now: datetime) -> str | None:
        row = self._session.get(ApiIdempotencyRow, {"scope": scope, "key": key})
        if row is None:
            return None
        if from_rfc3339(row.expires_at) <= now:
            self._session.delete(row)
            self._session.flush()
            return None
        if row.request_sha256 != request_sha256:
            raise DuplicateRecordError(
                "That idempotency key was already used for a different request."
            )
        return row.response_json

    def remember(
        self,
        *,
        scope: str,
        key: str,
        request_sha256: str,
        status_code: int,
        response_json: str,
        now: datetime,
    ) -> None:
        self._session.merge(
            ApiIdempotencyRow(
                scope=scope,
                key=key,
                request_sha256=request_sha256,
                status_code=status_code,
                response_json=response_json,
                created_at=to_rfc3339(now),
                expires_at=to_rfc3339(now + timedelta(hours=IDEMPOTENCY_RETENTION_HOURS)),
            )
        )
        self._session.flush()

    def prune(self, *, now: datetime) -> None:
        """Opportunistic cleanup of expired entries."""
        self._session.query(ApiIdempotencyRow).filter(
            ApiIdempotencyRow.expires_at <= to_rfc3339(now)
        ).delete(synchronize_session=False)


@dataclass(frozen=True, slots=True)
class SettingRecord:
    """One stored setting, with its ciphertext kept apart from its public part.

    The public part is what `GET /settings` may return; the ciphertext never is.
    Keeping them separate here means no caller can accidentally serialize the
    encrypted credential into a response.
    """

    key: str
    public: dict[str, object]
    secret_ciphertext: bytes | None
    revision: int

    @property
    def has_secret(self) -> bool:
        return self.secret_ciphertext is not None


class SettingsRepository:
    """Reads and writes the seeded proxy and provider settings rows.

    A missing row is configuration corruption — the migration seeds every key —
    so it is reported as a not-found rather than silently created with a guessed
    default. Every write is revision-guarded so a second browser tab cannot
    clobber an edit it never saw.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_all(self) -> tuple[SettingRecord, ...]:
        rows = self._session.scalars(select(SettingsRow).order_by(SettingsRow.key)).all()
        return tuple(_to_setting(row) for row in rows)

    def get(self, key: str) -> SettingRecord:
        row = self._require(key)
        return _to_setting(row)

    def update(
        self,
        key: str,
        *,
        expected_revision: int,
        public: dict[str, object],
        secret_ciphertext: bytes | None,
        now: datetime | None = None,
    ) -> SettingRecord:
        """Replace one setting's public and secret parts, guarding the revision.

        A stale revision is refused rather than overwritten: the other tab in
        the house already saved, and silently discarding that edit is exactly
        the surprise optimistic concurrency exists to prevent.
        """
        row = self._require(key)
        if row.revision != expected_revision:
            raise RecordChangedError(
                "This setting was changed elsewhere. Reload and try again.",
                field="revision",
                context={"current_revision": row.revision},
            )
        row.public_json = json.dumps(public, separators=(",", ":"), sort_keys=True)
        row.secret_ciphertext = secret_ciphertext
        row.revision += 1
        row.updated_at = to_rfc3339(now or datetime.now(UTC))
        self._session.flush()
        return _to_setting(row)

    def _require(self, key: str) -> SettingsRow:
        row = self._session.get(SettingsRow, key)
        if row is None:
            raise RecordNotFoundError(
                "That setting does not exist in this deployment.",
                context={"key": key},
            )
        return row


def _to_setting(row: SettingsRow) -> SettingRecord:
    try:
        public = json.loads(row.public_json)
    except json.JSONDecodeError:
        public = {}
    if not isinstance(public, dict):
        public = {}
    return SettingRecord(
        key=row.key,
        public=public,
        secret_ciphertext=row.secret_ciphertext,
        revision=row.revision,
    )
