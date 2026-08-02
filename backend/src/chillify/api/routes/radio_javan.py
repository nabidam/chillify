"""Dedicated Radio Javan discovery."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query

from chillify.api.dependencies import get_search_service
from chillify.api.schemas.common import PageModel
from chillify.api.schemas.downloads import RemoteResultModel
from chillify.application.search import SearchService
from chillify.domain.protocols import DISCOVERY_LIMIT_DEFAULT, DISCOVERY_LIMIT_MAX

router = APIRouter(prefix="/radio-javan", tags=["radio-javan"])


@router.get(
    "/search",
    response_model=PageModel[RemoteResultModel],
    summary="Search Radio Javan for MP3 tracks",
)
def search_radio_javan(
    search: Annotated[SearchService, Depends(get_search_service)],
    q: Annotated[str, Query(min_length=1, max_length=200, description="The submitted query.")],
    limit: Annotated[int, Query(ge=1, le=DISCOVERY_LIMIT_MAX)] = DISCOVERY_LIMIT_DEFAULT,
) -> PageModel[RemoteResultModel]:
    results = search.search_radio_javan(q, limit=limit)
    return PageModel(items=[RemoteResultModel.of(result) for result in results], next_cursor=None)


@router.get(
    "/tracks",
    response_model=PageModel[RemoteResultModel],
    summary="Browse first-page Radio Javan tracks",
)
def browse_radio_javan(
    search: Annotated[SearchService, Depends(get_search_service)],
    section: Annotated[
        Literal["featured", "trending"],
        Query(description="The Radio Javan section to browse."),
    ],
) -> PageModel[RemoteResultModel]:
    results = search.browse_radio_javan(section)
    return PageModel(items=[RemoteResultModel.of(result) for result in results], next_cursor=None)
