"""Domain entities and value objects.

IDs are distinct types rather than interchangeable strings, so a profile ID can
never be passed where a track ID is expected. The entities are immutable: a
change produces a new value and a new stored revision.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Final, NewType

from chillify.domain.normalization import (
    normalize_album,
    normalize_artist,
    normalize_title,
)

ProfileId = NewType("ProfileId", str)
TrackId = NewType("TrackId", str)
PlaylistId = NewType("PlaylistId", str)
ArtworkStageId = NewType("ArtworkStageId", str)

AUDIO_MIME_TYPE: Final = "audio/mpeg"

# The stored timestamp form. It is defined here rather than in the persistence
# layer because keyset cursors compare against it as text: a cursor rendered
# any other way would silently order differently from the column it bounds.
TIMESTAMP_FORMAT: Final = "%Y-%m-%dT%H:%M:%S.%f"


def to_rfc3339(moment: datetime) -> str:
    """Render a timestamp as millisecond-precision RFC 3339 UTC text."""
    utc = moment.astimezone(UTC)
    return f"{utc.strftime(TIMESTAMP_FORMAT)[:-3]}Z"


def from_rfc3339(value: str) -> datetime:
    """Parse stored timestamp text back into an aware UTC datetime."""
    return datetime.strptime(value, f"{TIMESTAMP_FORMAT}Z").replace(tzinfo=UTC)


class Availability(StrEnum):
    """Whether a track's managed file can currently be served.

    `mutating` and `recovery` mean an edit or deletion owns the file right now;
    both are unplayable but neither is an error the person caused.
    """

    AVAILABLE = "available"
    MISSING = "missing"
    MUTATING = "mutating"
    RECOVERY = "recovery"


class LibrarySort(StrEnum):
    """The orderings `GET /library/tracks` accepts."""

    RECENT = "recent"
    TITLE = "title"
    ARTIST = "artist"


@dataclass(frozen=True, slots=True)
class Profile:
    """A name-only household profile. There is no authentication and no owner."""

    id: ProfileId
    name: str
    name_folded: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class Track:
    """One managed local MP3 and the metadata Chillify serves for it."""

    id: TrackId
    title: str
    artist: str
    album: str | None
    release_year: int | None
    disc_number: int | None
    track_number: int | None
    duration_ms: int | None
    normalized_artist: str
    normalized_title: str
    normalized_album: str
    isrc: str | None
    file_relpath: str
    artwork_relpath: str | None
    mime_type: str
    file_size_bytes: int
    content_sha256: str
    availability: Availability
    revision: int
    created_at: datetime
    updated_at: datetime

    @property
    def is_playable(self) -> bool:
        return self.availability is Availability.AVAILABLE


@dataclass(frozen=True, slots=True)
class TrackSource:
    """One provider identity a track was acquired from."""

    provider: str
    source_id: str | None
    source_url: str


@dataclass(frozen=True, slots=True)
class TrackDetail:
    """One track with everything S13 edits and everything it discloses."""

    track: Track
    sources: tuple[TrackSource, ...]


@dataclass(frozen=True, slots=True)
class TrackEdit:
    """The complete intended record one save applies.

    Every editable field is present rather than optional: a partial patch would
    make "clear the album" and "leave the album alone" the same request, and the
    edit has to rewrite the file's tags either way.
    """

    title: str
    artist: str
    album: str | None
    release_year: int | None
    disc_number: int | None
    track_number: int | None
    artwork_stage_id: ArtworkStageId | None = None


class ArtworkOrigin(StrEnum):
    """Where a staged cover image came from."""

    UPLOAD = "upload"
    URL = "url"
    LASTFM = "lastfm"


@dataclass(frozen=True, slots=True)
class ArtworkStage:
    """One validated, normalized JPEG waiting to be consumed by a save.

    A stage is single-use and expires: it holds an image the person chose but
    has not committed, so nothing about a track changes until the save that
    consumes it commits.
    """

    id: ArtworkStageId
    file_relpath: str
    mime_type: str
    content_sha256: str
    size_bytes: int
    origin: ArtworkOrigin
    created_at: datetime
    expires_at: datetime
    consumed_at: datetime | None

    def is_consumable(self, *, now: datetime) -> bool:
        return self.consumed_at is None and self.expires_at > now


@dataclass(frozen=True, slots=True)
class Playlist:
    """One profile's manually ordered collection of local tracks."""

    id: PlaylistId
    profile_id: ProfileId
    name: str
    name_folded: str
    track_count: int
    revision: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class PlaylistDetail:
    """One playlist together with its tracks in saved order."""

    playlist: Playlist
    tracks: tuple[Track, ...]


@dataclass(frozen=True, slots=True)
class MediaMutationJournal:
    """One recovery-journal row, parsed for startup recovery to act on.

    A journal row records a change that moves managed media — an edit or a
    deletion — and the files that can undo it. Startup recovery reads the rows
    that never reached `finalized` or `rolled_back` and finishes or reverses
    each from exactly this record, never from the browser's memory of it.
    """

    id: str
    track_id: str | None
    operation: str
    state: str
    old_record: dict[str, object]
    new_record: dict[str, object] | None
    recovery: dict[str, str]


@dataclass(frozen=True, slots=True)
class NormalizedMetadata:
    """The normalized projection of one track's identity fields."""

    normalized_artist: str
    normalized_title: str
    normalized_album: str


def normalize_metadata(*, artist: str, title: str, album: str | None) -> NormalizedMetadata:
    """Derive every normalized column from the displayed metadata at once."""
    return NormalizedMetadata(
        normalized_artist=normalize_artist(artist),
        normalized_title=normalize_title(title),
        normalized_album=normalize_album(album),
    )


@dataclass(frozen=True, slots=True)
class Page[Item]:
    """One keyset page. `next_cursor` is None exactly when the page is last."""

    items: tuple[Item, ...]
    next_cursor: str | None
