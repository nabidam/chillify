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
