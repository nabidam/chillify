"""Track media routes.

Byte-range delivery is delegated to Starlette's `FileResponse`, which already
implements `206`, `416`, and multi-part refusal correctly. Chillify's own work
is resolving the ID to a contained, available file and stamping an ETag that
changes whenever the bytes or the metadata do.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path
from fastapi.responses import FileResponse

from chillify.api.dependencies import get_library_service
from chillify.application.library import LibraryService
from chillify.domain.models import TrackId

router = APIRouter(tags=["tracks"])


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
