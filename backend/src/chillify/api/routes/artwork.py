"""Artwork staging routes, and the media routes that serve cover bytes.

Staging and serving are deliberately separate surfaces. `/api/v1/artwork/...`
validates and stores an image the person picked and changes nothing else;
`/media/artwork/...` serves bytes that already exist, on the path nginx passes
through unbuffered.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, UploadFile, status
from fastapi import Path as PathParam
from fastapi.responses import FileResponse

from chillify.api.dependencies import get_artwork_service, get_metadata_service
from chillify.api.schemas.artwork import (
    ArtworkLastfmRequest,
    ArtworkStageModel,
    ArtworkUrlRequest,
    LastfmArtworkStageModel,
    LastfmMetadataModel,
)
from chillify.application.artwork import ArtworkService
from chillify.application.metadata import MetadataService
from chillify.domain.errors import ArtworkTooLargeError, RecordNotFoundError
from chillify.domain.models import ArtworkStageId, TrackId
from chillify.infrastructure.media.artwork import ARTWORK_MAX_BYTES

router = APIRouter(tags=["artwork"])
media_router = APIRouter(tags=["media"])

# Covers are small and revalidated by ETag; the household LAN makes a long
# cache pointless and a stale cover after a correction actively misleading.
_ARTWORK_CACHE_CONTROL = "private, max-age=0, must-revalidate"


@router.post(
    "/artwork/stages/upload",
    response_model=ArtworkStageModel,
    status_code=status.HTTP_201_CREATED,
    summary="Stage an uploaded cover image",
)
async def stage_uploaded_artwork(
    artwork: Annotated[ArtworkService, Depends(get_artwork_service)],
    file: Annotated[UploadFile, File(description="The cover image to stage.")],
) -> ArtworkStageModel:
    """Validate and normalize one uploaded image into a single-use stage.

    The upload is bounded before it is read whole: an oversized file is refused
    from its declared size rather than after the server has buffered it.
    """
    if file.size is not None and file.size > ARTWORK_MAX_BYTES:
        raise ArtworkTooLargeError(
            "That cover image is larger than 10 MB.",
            context={"max_bytes": ARTWORK_MAX_BYTES},
        )
    payload = await file.read(ARTWORK_MAX_BYTES + 1)
    return ArtworkStageModel.of(artwork.stage_upload(payload))


@router.post(
    "/artwork/stages/url",
    response_model=ArtworkStageModel,
    status_code=status.HTTP_201_CREATED,
    summary="Stage a cover image from a link",
)
def stage_artwork_from_url(
    request: ArtworkUrlRequest,
    artwork: Annotated[ArtworkService, Depends(get_artwork_service)],
) -> ArtworkStageModel:
    return ArtworkStageModel.of(artwork.stage_from_url(request.url))


@router.post(
    "/artwork/stages/lastfm",
    response_model=LastfmArtworkStageModel,
    status_code=status.HTTP_201_CREATED,
    summary="Stage Last.fm's best cover for one track",
)
def stage_artwork_from_lastfm(
    request: ArtworkLastfmRequest,
    artwork: Annotated[ArtworkService, Depends(get_artwork_service)],
) -> LastfmArtworkStageModel:
    result = artwork.stage_from_lastfm(
        artist=request.artist, title=request.title, album=request.album
    )
    return LastfmArtworkStageModel(
        stage=ArtworkStageModel.of(result.stage),
        metadata=LastfmMetadataModel(
            title=result.metadata.title,
            artist=result.metadata.artist,
            album=result.metadata.album,
            duration_ms=result.metadata.duration_ms,
        ),
    )


@media_router.get(
    "/media/artwork/tracks/{track_id}",
    summary="Serve one track's managed cover",
    response_class=FileResponse,
    responses={200: {"content": {"image/jpeg": {}}, "description": "The cover image."}},
)
def read_track_artwork(
    metadata: Annotated[MetadataService, Depends(get_metadata_service)],
    track_id: Annotated[str, PathParam(description="Track ID.")],
) -> FileResponse:
    """The cover for one track, resolved through the same containment rules as audio."""
    target = metadata.open_artwork(TrackId(track_id))
    if target is None:
        raise RecordNotFoundError("That track has no cover image.")
    return FileResponse(
        target,
        media_type="image/jpeg",
        headers={"Cache-Control": _ARTWORK_CACHE_CONTROL},
        content_disposition_type="inline",
    )


@media_router.get(
    "/media/artwork/stages/{stage_id}",
    summary="Serve one staged cover for preview",
    response_class=FileResponse,
    responses={200: {"content": {"image/jpeg": {}}, "description": "The staged image."}},
)
def read_staged_artwork(
    metadata: Annotated[MetadataService, Depends(get_metadata_service)],
    stage_id: Annotated[str, PathParam(description="Artwork stage ID.")],
) -> FileResponse:
    """The image the person picked, so S13 can show it before anything is saved."""
    target = metadata.open_artwork_stage(ArtworkStageId(stage_id))
    return FileResponse(
        target,
        media_type="image/jpeg",
        headers={"Cache-Control": _ARTWORK_CACHE_CONTROL},
        content_disposition_type="inline",
    )
