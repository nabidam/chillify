"""Browse-context response shapes.

A context is addressed by a derived key, never by a path or a database ID: the
key encodes the normalized identity, and an equal album name under a different
artist therefore addresses a different context. Every detail response carries
its tracks already ordered, so the browser plays the exact order it renders.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from chillify.api.schemas.tracks import TrackSummaryModel
from chillify.application.library import AlbumContext, ArtistContext, YearContext
from chillify.domain.models import AlbumSummary, ArtistSummary, YearSummary
from chillify.domain.normalization import (
    encode_album_key,
    encode_artist_key,
    encode_year_key,
)


class ArtistSummaryModel(BaseModel):
    """One artist grouping as the S2 Artists tab renders it."""

    artist_key: str = Field(description="Derived key addressing this artist context.")
    artist: str = Field(description="Representative display name for the artist.")
    track_count: int

    @classmethod
    def of(cls, summary: ArtistSummary) -> ArtistSummaryModel:
        return cls(
            artist_key=encode_artist_key(summary.normalized_artist),
            artist=summary.display_name,
            track_count=summary.track_count,
        )


class AlbumSummaryModel(BaseModel):
    """One album grouping as the S2 Albums tab renders it."""

    album_key: str = Field(description="Derived key addressing this album context.")
    album: str | None = Field(description="Album name, or null for the Unknown Album context.")
    artist: str = Field(description="Representative display name for the album's artist.")
    track_count: int

    @classmethod
    def of(cls, summary: AlbumSummary) -> AlbumSummaryModel:
        return cls(
            album_key=encode_album_key(summary.normalized_artist, summary.normalized_album),
            album=summary.display_album,
            artist=summary.display_artist,
            track_count=summary.track_count,
        )


class YearSummaryModel(BaseModel):
    """One release-year grouping as the S2 Years tab renders it."""

    year_key: str = Field(description="Derived key addressing this year context.")
    release_year: int | None = Field(
        description="The release year, or null for the first-class Unknown Year grouping."
    )
    track_count: int

    @classmethod
    def of(cls, summary: YearSummary) -> YearSummaryModel:
        return cls(
            year_key=encode_year_key(summary.release_year),
            release_year=summary.release_year,
            track_count=summary.track_count,
        )


class ArtistContextModel(BaseModel):
    """The S6 artist view: identity and every local track in play order."""

    artist_key: str
    artist: str
    track_count: int
    tracks: list[TrackSummaryModel]

    @classmethod
    def of(cls, context: ArtistContext) -> ArtistContextModel:
        return cls(
            artist_key=encode_artist_key(context.normalized_artist),
            artist=context.display_name,
            track_count=len(context.tracks),
            tracks=[TrackSummaryModel.of(track) for track in context.tracks],
        )


class AlbumContextModel(BaseModel):
    """The S7 album view: identity and disc/track-ordered tracks."""

    album_key: str
    album: str | None
    artist: str
    track_count: int
    tracks: list[TrackSummaryModel]

    @classmethod
    def of(cls, context: AlbumContext) -> AlbumContextModel:
        return cls(
            album_key=encode_album_key(context.normalized_artist, context.normalized_album),
            album=context.display_album,
            artist=context.display_artist,
            track_count=len(context.tracks),
            tracks=[TrackSummaryModel.of(track) for track in context.tracks],
        )


class YearContextModel(BaseModel):
    """The S8 year view: identity and grouped-then-ordered tracks."""

    year_key: str
    release_year: int | None
    track_count: int
    tracks: list[TrackSummaryModel]

    @classmethod
    def of(cls, context: YearContext) -> YearContextModel:
        return cls(
            year_key=encode_year_key(context.release_year),
            release_year=context.release_year,
            track_count=len(context.tracks),
            tracks=[TrackSummaryModel.of(track) for track in context.tracks],
        )
