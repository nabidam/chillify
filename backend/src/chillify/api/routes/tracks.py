"""Track media routes.

Byte-range delivery is delegated to Starlette's `FileResponse`, which already
implements `206`, `416`, and multi-part refusal correctly. Chillify's own work
is resolving the ID to a contained, available file and stamping an ETag that
changes whenever the bytes or the metadata do.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Path, Response, status
from fastapi.responses import FileResponse

from chillify.api.dependencies import (
    get_deletion_service,
    get_library_service,
    get_metadata_service,
)
from chillify.api.schemas.deletion import DeleteImpactModel
from chillify.api.schemas.tracks import TrackDetailModel, UpdateTrackRequest
from chillify.application.deletion import DeletionService
from chillify.application.library import LibraryService
from chillify.application.metadata import MetadataService
from chillify.domain.errors import ValidationFailedError
from chillify.domain.models import TrackId

router = APIRouter(tags=["tracks"])


@router.get(
    "/tracks/{track_id}",
    response_model=TrackDetailModel,
    summary="Read one complete editable track",
)
def read_track(
    metadata: Annotated[MetadataService, Depends(get_metadata_service)],
    track_id: Annotated[str, Path(description="Track ID.")],
) -> TrackDetailModel:
    """Everything S13 needs before it enables its fields."""
    return TrackDetailModel.of(metadata.get_track_detail(TrackId(track_id)))


@router.patch(
    "/tracks/{track_id}",
    response_model=TrackDetailModel,
    summary="Correct one track atomically",
)
def update_track(
    request: UpdateTrackRequest,
    metadata: Annotated[MetadataService, Depends(get_metadata_service)],
    track_id: Annotated[str, Path(description="Track ID.")],
    if_match: Annotated[
        str | None,
        Header(alias="If-Match", description="The track's current `revision`."),
    ] = None,
) -> TrackDetailModel:
    """Apply the complete corrected record — tags, art, path, and row — as one change.

    `If-Match` is required rather than optional: without it a save would
    silently overwrite whatever the other browser tab in the house just wrote,
    and this is the one mutation that also rewrites a file on disk.
    """
    return TrackDetailModel.of(
        metadata.update_track(
            TrackId(track_id),
            request.to_edit(),
            expected_revision=_revision_from(if_match),
        )
    )


@router.get(
    "/tracks/{track_id}/delete-impact",
    response_model=DeleteImpactModel,
    summary="Count what a permanent deletion would remove",
)
def read_delete_impact(
    deletion: Annotated[DeletionService, Depends(get_deletion_service)],
    track_id: Annotated[str, Path(description="Track ID.")],
) -> DeleteImpactModel:
    """The server-owned playlist references S15 discloses before confirming.

    S15 combines this with the current-track and session-queue occurrences from
    the browser's own store, which the server never sees.
    """
    return DeleteImpactModel.of(deletion.delete_impact(TrackId(track_id)))


@router.delete(
    "/tracks/{track_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Permanently delete one shared track",
)
def delete_track(
    deletion: Annotated[DeletionService, Depends(get_deletion_service)],
    track_id: Annotated[str, Path(description="Track ID.")],
    if_match: Annotated[
        str | None,
        Header(alias="If-Match", description="The track's current `revision`."),
    ] = None,
) -> Response:
    """Remove the track's media and every reference to it, atomically.

    `If-Match` is required for the same reason the correction route requires it:
    this is destructive and rewrites the mounted filesystem, so it must refuse to
    run against a revision the browser has not seen.
    """
    deletion.delete_track(TrackId(track_id), expected_revision=_revision_from(if_match))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _revision_from(if_match: str | None) -> int:
    """Parse the `If-Match` header into the revision the save must match."""
    if if_match is None:
        raise ValidationFailedError(
            "This save needs the track's current revision in an If-Match header.",
            field="If-Match",
        )
    candidate = if_match.strip().strip('"').removeprefix("W/").strip('"')
    if not candidate.isdigit():
        raise ValidationFailedError(
            "The If-Match header must carry the track's numeric revision.",
            field="If-Match",
        )
    return int(candidate)


@router.get(
    "/tracks/{track_id}/stream",
    summary="Stream one local track",
    response_class=FileResponse,
    responses={
        200: {"content": {"audio/mpeg": {}}, "description": "The complete audio file."},
        206: {"content": {"audio/mpeg": {}}, "description": "The requested byte range."},
    },
)
def stream_track(
    library: Annotated[LibraryService, Depends(get_library_service)],
    track_id: Annotated[str, Path(description="Track ID.")],
) -> FileResponse:
    target = library.open_stream(TrackId(track_id))
    return FileResponse(
        target.path,
        media_type=target.media_type,
        headers={
            "ETag": target.etag,
            "Accept-Ranges": "bytes",
            # Household media on a LAN: revalidate rather than serve a stale
            # body after a metadata edit rewrote the file's tags.
            "Cache-Control": "private, max-age=0, must-revalidate",
        },
        # The stored filename is never disclosed; the browser plays the stream
        # rather than downloading it.
        content_disposition_type="inline",
    )
