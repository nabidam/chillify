"""Local library browsing routes.

Everything here reads the local database only. No route in this module can
reach a provider, so a degraded internet or an unavailable proxy never makes
the library unreadable.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from chillify.api.dependencies import get_library_service
from chillify.api.schemas.common import PageModel
from chillify.api.schemas.tracks import TrackSummaryModel
from chillify.application.library import LibraryService
from chillify.domain.models import LibrarySort
from chillify.infrastructure.db.repositories import (
    LIBRARY_PAGE_LIMIT_DEFAULT,
    LIBRARY_PAGE_LIMIT_MAX,
)

router = APIRouter(tags=["library"])


@router.get(
    "/library/tracks",
    response_model=PageModel[TrackSummaryModel],
    summary="List local tracks",
)
def list_library_tracks(
    library: Annotated[LibraryService, Depends(get_library_service)],
    q: Annotated[
        str | None,
        Query(description="Match against normalized artist, title, and album.", max_length=200),
    ] = None,
    sort: Annotated[LibrarySort, Query(description="Ordering for this listing.")] = (
        LibrarySort.RECENT
    ),
    cursor: Annotated[str | None, Query(description="Cursor from a previous page.")] = None,
    limit: Annotated[int, Query(ge=1, le=LIBRARY_PAGE_LIMIT_MAX)] = LIBRARY_PAGE_LIMIT_DEFAULT,
) -> PageModel[TrackSummaryModel]:
    page = library.list_tracks(query=q, sort=sort, cursor=cursor, limit=limit)
    return PageModel(
        items=[TrackSummaryModel.of(track) for track in page.items],
        next_cursor=page.next_cursor,
    )
