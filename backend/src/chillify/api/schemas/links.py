"""Direct-link inspection wire shapes.

Inspection is a read: it reports what a submitted link resolves to and whether
S5 review is required, but it commits nothing. The candidate it returns is the
same normalized shape a search result carries, so `POST /downloads` receives an
identical body whichever way the person reached it.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, cast

from pydantic import BaseModel, Field

from chillify.api.schemas.downloads import (
    RemoteResultModel,
    SourceTypeLiteral,
    TrackCandidateModel,
)
from chillify.application.inspection import InspectionAccepted
from chillify.application.links import LinkInspection
from chillify.application.spotify_links import SpotifyLinkMatches

InspectionPhaseLiteral = Literal[
    "reading_spotify",
    "matching_spotdl",
    "inspecting_youtube",
    "cancelled",
    "expired",
    "failed",
    "done",
]
InspectionProviderLiteral = Literal["deezer", "spotdl", "yt_dlp"]


class LinkInspectionRequest(BaseModel):
    """One submitted URL to recognize and inspect."""

    url: str = Field(min_length=1, max_length=2048, description="The submitted link.")


class SpotifyTrackReferenceModel(BaseModel):
    """The public fields Spotify exposes without an account."""

    spotify_id: str
    canonical_url: str
    title: str
    thumbnail_url: str | None


class SpotifyLinkMatchesModel(BaseModel):
    """A Spotify reference and independent catalog candidates for selection."""

    reference: SpotifyTrackReferenceModel
    items: list[RemoteResultModel]

    @classmethod
    def of(cls, result: SpotifyLinkMatches) -> SpotifyLinkMatchesModel:
        return cls(
            reference=SpotifyTrackReferenceModel(
                spotify_id=result.reference.spotify_id,
                canonical_url=result.reference.canonical_url,
                title=result.reference.title,
                thumbnail_url=result.reference.thumbnail_url,
            ),
            items=[RemoteResultModel.of(item) for item in result.matches],
        )


class LinkInspectionModel(BaseModel):
    """What one link resolves to, and how it should be queued.

    `source_type` is always `spotify_track` or `youtube_video` in practice —
    inspection only recognizes those two — and the wire literal is shared with
    the download request so the same candidate flows straight into it.
    """

    source_type: SourceTypeLiteral
    provider: InspectionProviderLiteral
    review_required: bool = Field(
        description="True when S5 metadata review must precede queueing, as for YouTube.",
    )
    candidate: TrackCandidateModel
    is_playable: Literal[False] = Field(
        default=False,
        description="Always false. A link resolves to something to acquire, never a local file.",
    )
    existing_track_id: str | None = Field(
        default=None,
        description="The local track this link already duplicates, if any.",
    )

    @classmethod
    def of(cls, inspection: LinkInspection) -> LinkInspectionModel:
        return cls(
            source_type=inspection.source_type.value,
            provider=cast(InspectionProviderLiteral, inspection.provider.value),
            review_required=inspection.review_required,
            candidate=TrackCandidateModel.of(inspection.candidate),
            existing_track_id=(
                None if inspection.existing_track_id is None else str(inspection.existing_track_id)
            ),
        )


class InspectionAcceptedModel(BaseModel):
    """The small acknowledgement returned before provider work finishes."""

    inspection_id: str
    phase: InspectionPhaseLiteral
    started_at: datetime

    @classmethod
    def of(cls, accepted: InspectionAccepted) -> InspectionAcceptedModel:
        return cls(
            inspection_id=accepted.id,
            phase=cast(InspectionPhaseLiteral, accepted.phase),
            started_at=accepted.started_at,
        )
