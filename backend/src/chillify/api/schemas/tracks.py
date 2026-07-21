"""Track response shapes.

Responses never expose a relative or absolute path: a track is addressed by ID,
and its audio is reached only through the stream route.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from chillify.domain.models import ArtworkStageId, Track, TrackDetail, TrackEdit, TrackSource
from chillify.domain.normalization import (
    METADATA_TEXT_MAX_LENGTH,
    encode_album_key,
    encode_artist_key,
)


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


class TrackSourceModel(BaseModel):
    """One provider identity a track was acquired from.

    Disclosed on S13 because a person correcting metadata benefits from seeing
    where the file came from; it is never used to address the track.
    """

    provider: str
    source_id: str | None
    source_url: str

    @classmethod
    def of(cls, source: TrackSource) -> TrackSourceModel:
        return cls(
            provider=source.provider,
            source_id=source.source_id,
            source_url=source.source_url,
        )


class TrackDetailModel(BaseModel):
    """The complete editable record S13 loads before it enables its fields."""

    track: TrackSummaryModel
    has_artwork: bool = Field(
        description="Whether a managed cover exists. Its bytes are served by the artwork route."
    )
    sources: list[TrackSourceModel]

    @classmethod
    def of(cls, detail: TrackDetail) -> TrackDetailModel:
        return cls(
            track=TrackSummaryModel.of(detail.track),
            has_artwork=detail.track.artwork_relpath is not None,
            sources=[TrackSourceModel.of(source) for source in detail.sources],
        )


class UpdateTrackRequest(BaseModel):
    """The complete intended record for one save.

    Every editable field is required rather than optional: a partial patch
    would make "clear the album" and "leave the album alone" indistinguishable,
    and the save has to rewrite the file's tags either way.
    """

    title: str = Field(min_length=1, max_length=METADATA_TEXT_MAX_LENGTH)
    artist: str = Field(min_length=1, max_length=METADATA_TEXT_MAX_LENGTH)
    album: str | None = Field(default=None, max_length=METADATA_TEXT_MAX_LENGTH)
    release_year: int | None = Field(default=None)
    disc_number: int | None = Field(default=None)
    track_number: int | None = Field(default=None)
    artwork_stage_id: str | None = Field(
        default=None,
        description="A staged cover to consume atomically with this save.",
    )

    def to_edit(self) -> TrackEdit:
        return TrackEdit(
            title=self.title,
            artist=self.artist,
            album=self.album,
            release_year=self.release_year,
            disc_number=self.disc_number,
            track_number=self.track_number,
            artwork_stage_id=(
                None if self.artwork_stage_id is None else ArtworkStageId(self.artwork_stage_id)
            ),
        )
