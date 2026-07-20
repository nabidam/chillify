"""Track response shapes.

Responses never expose a relative or absolute path: a track is addressed by ID,
and its audio is reached only through the stream route.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from chillify.domain.models import Track
from chillify.domain.normalization import encode_album_key, encode_artist_key


class TrackSummaryModel(BaseModel):
    """One local track as the library, search, and context views render it."""

    id: str
    title: str
    artist: str
    album: str | None
    release_year: int | None
    disc_number: int | None
    track_number: int | None
    duration_ms: int | None
    artist_key: str = Field(description="Derived key addressing this track's artist context.")
    album_key: str = Field(description="Derived key addressing this track's album context.")
    availability: Literal["available", "missing", "mutating", "recovery"]
    is_playable: bool = Field(
        description="Whether the managed file can be streamed right now. False disables Play."
    )
    revision: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def of(cls, track: Track) -> TrackSummaryModel:
        return cls(
            id=str(track.id),
            title=track.title,
            artist=track.artist,
            album=track.album,
            release_year=track.release_year,
            disc_number=track.disc_number,
            track_number=track.track_number,
            duration_ms=track.duration_ms,
            artist_key=encode_artist_key(track.normalized_artist),
            album_key=encode_album_key(track.normalized_artist, track.normalized_album),
            availability=track.availability.value,
            is_playable=track.is_playable,
            revision=track.revision,
            created_at=track.created_at,
            updated_at=track.updated_at,
        )
