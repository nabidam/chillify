"""Explicit online discovery.

There is exactly one route here and it is never called implicitly. Typing in
the search box queries `GET /library/tracks`; only pressing Search Deezer
reaches this module, and therefore only that press reaches a provider.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from chillify.api.dependencies import get_search_service
from chillify.api.schemas.common import PageModel
from chillify.api.schemas.downloads import RemoteResultModel
from chillify.application.search import SearchService
from chillify.domain.protocols import DISCOVERY_LIMIT_DEFAULT, DISCOVERY_LIMIT_MAX

router = APIRouter(tags=["search"])


@router.get(
    "/search/deezer",
    response_model=PageModel[RemoteResultModel],
    summary="Search Deezer for matching tracks",
)
def search_deezer(
    search: Annotated[SearchService, Depends(get_search_service)],
    q: Annotated[str, Query(min_length=1, max_length=200, description="The submitted query.")],
    limit: Annotated[int, Query(ge=1, le=DISCOVERY_LIMIT_MAX)] = DISCOVERY_LIMIT_DEFAULT,
) -> PageModel[RemoteResultModel]:
    """Return normalized, non-playable candidates and their duplicate links.

    The page is deliberately single: ARCHITECTURE ignores Deezer pagination
    beyond the first page in v1, so `next_cursor` is always null rather than a
    cursor that cannot be honoured.
    """
    results = search.search_deezer(q, limit=limit)
    return PageModel(items=[RemoteResultModel.of(result) for result in results], next_cursor=None)
