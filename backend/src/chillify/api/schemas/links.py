"""Direct-link inspection wire shapes.

Inspection is a read: it reports what a submitted link resolves to and whether
S5 review is required, but it commits nothing. The candidate it returns is the
same normalized shape a search result carries, so `POST /downloads` receives an
identical body whichever way the person reached it.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from chillify.api.schemas.downloads import SourceTypeLiteral, TrackCandidateModel
from chillify.application.links import LinkInspection


class LinkInspectionRequest(BaseModel):
    """One submitted URL to recognize and inspect."""

    url: str = Field(min_length=1, max_length=2048, description="The submitted link.")


class LinkInspectionModel(BaseModel):
    """What one link resolves to, and how it should be queued.

    `source_type` is always `spotify_track` or `youtube_video` in practice —
    inspection only recognizes those two — and the wire literal is shared with
    the download request so the same candidate flows straight into it.
    """

    source_type: SourceTypeLiteral
    provider: Literal["deezer", "spotdl", "yt_dlp"]
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
            provider=inspection.provider.value,
            review_required=inspection.review_required,
            candidate=TrackCandidateModel.of(inspection.candidate),
            existing_track_id=(
                None if inspection.existing_track_id is None else str(inspection.existing_track_id)
            ),
        )
