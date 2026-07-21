"""Artwork-stage request and response shapes.

A stage response carries an ID and nothing that locates the file: the browser
hands the ID back to the save that consumes it, and the staged path stays an
internal detail of the managed root.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from chillify.domain.models import ArtworkStage


class ArtworkStageModel(BaseModel):
    """One staged cover image, waiting to be consumed by a save."""

    id: str
    mime_type: Literal["image/jpeg"]
    size_bytes: int
    origin: Literal["upload", "url", "lastfm"]
    created_at: datetime
    expires_at: datetime = Field(
        description="After this moment the stage is gone and the image must be chosen again."
    )

    @classmethod
    def of(cls, stage: ArtworkStage) -> ArtworkStageModel:
        return cls(
            id=str(stage.id),
            mime_type="image/jpeg",
            size_bytes=stage.size_bytes,
            origin=stage.origin.value,
            created_at=stage.created_at,
            expires_at=stage.expires_at,
        )


class ArtworkUrlRequest(BaseModel):
    """Stage the image at one submitted link."""

    url: str = Field(min_length=1, max_length=2048)


class ArtworkLastfmRequest(BaseModel):
    """Stage Last.fm's best cover for one track's identity."""

    artist: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=200)
    album: str | None = Field(default=None, max_length=200)
