"""Direct-link inspection route.

There is one route here and it commits nothing. It recognizes a submitted URL,
inspects its metadata, and reports a candidate the Add-by-Link and YouTube
Review screens use. Only `POST /downloads` turns that candidate into durable
work, so an unsupported, malformed, or bulk link fails here without a job.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from fastapi.responses import StreamingResponse

from chillify.api.dependencies import get_inspection_service, get_spotify_link_service
from chillify.api.schemas.links import (
    InspectionAcceptedModel,
    LinkInspectionRequest,
    SpotifyLinkMatchesModel,
)
from chillify.application.inspection import InspectionService
from chillify.application.spotify_links import SpotifyLinkService

router = APIRouter(tags=["links"])


@router.post(
    "/links/spotify/matches",
    response_model=SpotifyLinkMatchesModel,
    summary="Resolve one Spotify track and find independent catalog matches",
)
def match_spotify_link(
    submission: LinkInspectionRequest,
    spotify_links: Annotated[SpotifyLinkService, Depends(get_spotify_link_service)],
) -> SpotifyLinkMatchesModel:
    """Resolve public oEmbed data, then search keyless catalogs by title."""
    return SpotifyLinkMatchesModel.of(spotify_links.resolve(submission.url))


@router.post(
    "/links/inspect",
    response_model=InspectionAcceptedModel,
    status_code=202,
    summary="Inspect one Spotify track or YouTube video link",
)
def inspect_link(
    submission: LinkInspectionRequest,
    inspections: Annotated[InspectionService, Depends(get_inspection_service)],
) -> InspectionAcceptedModel:
    """Accept one link and return before provider work completes."""
    return InspectionAcceptedModel.of(inspections.start(submission.url))


@router.get(
    "/links/inspect/{inspection_id}/events",
    response_class=StreamingResponse,
    summary="Stream one link inspection",
    responses={200: {"content": {"text/event-stream": {"schema": {"type": "string"}}}}},
)
def stream_inspection(
    inspection_id: str,
    inspections: Annotated[InspectionService, Depends(get_inspection_service)],
) -> StreamingResponse:
    inspections.ensure_active(inspection_id)
    return StreamingResponse(
        inspections.event_frames(inspection_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.delete(
    "/links/inspect/{inspection_id}",
    status_code=204,
    summary="Cancel one link inspection",
)
def cancel_inspection(
    inspection_id: str,
    inspections: Annotated[InspectionService, Depends(get_inspection_service)],
) -> Response:
    inspections.cancel(inspection_id)
    return Response(status_code=204)
