"""Direct-link inspection route.

There is one route here and it commits nothing. It recognizes a submitted URL,
inspects its metadata, and reports a candidate the Add-by-Link and YouTube
Review screens use. Only `POST /downloads` turns that candidate into durable
work, so an unsupported, malformed, or bulk link fails here without a job.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from chillify.api.dependencies import get_link_inspection_service
from chillify.api.schemas.links import LinkInspectionModel, LinkInspectionRequest
from chillify.application.links import LinkInspectionService

router = APIRouter(tags=["links"])


@router.post(
    "/links/inspect",
    response_model=LinkInspectionModel,
    summary="Inspect one Spotify track or YouTube video link",
)
def inspect_link(
    submission: LinkInspectionRequest,
    links: Annotated[LinkInspectionService, Depends(get_link_inspection_service)],
) -> LinkInspectionModel:
    """Recognize and inspect one link, reporting its candidate and review need."""
    return LinkInspectionModel.of(links.inspect(submission.url))
