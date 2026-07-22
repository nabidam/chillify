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
from chillify.api.schemas.library import (
    AlbumContextModel,
    AlbumSummaryModel,
    ArtistContextModel,
    ArtistSummaryModel,
    YearContextModel,
    YearSummaryModel,
)
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


@router.get(
    "/library/artists",
    response_model=PageModel[ArtistSummaryModel],
    summary="List local artists",
)
def list_library_artists(
    library: Annotated[LibraryService, Depends(get_library_service)],
    q: Annotated[
        str | None,
        Query(description="Match against the normalized artist.", max_length=200),
    ] = None,
) -> PageModel[ArtistSummaryModel]:
    """Every artist grouping in normalized order.

    Bounded by household use and served whole, the same decision `/profiles`
    makes: the page envelope is present for shape consistency, never paging.
    """
    artists = library.list_artists(query=q)
    return PageModel(items=[ArtistSummaryModel.of(artist) for artist in artists])


@router.get(
    "/library/artists/{artist_key}",
    response_model=ArtistContextModel,
    summary="One artist's local tracks in play order",
)
def get_library_artist(
    artist_key: str,
    library: Annotated[LibraryService, Depends(get_library_service)],
) -> ArtistContextModel:
    return ArtistContextModel.of(library.artist_context(artist_key))


@router.get(
    "/library/albums",
    response_model=PageModel[AlbumSummaryModel],
    summary="List local albums",
)
def list_library_albums(
    library: Annotated[LibraryService, Depends(get_library_service)],
    q: Annotated[
        str | None,
        Query(description="Match against the normalized artist and album.", max_length=200),
    ] = None,
) -> PageModel[AlbumSummaryModel]:
    """Every album grouping; same-named albums by different artists stay apart."""
    albums = library.list_albums(query=q)
    return PageModel(items=[AlbumSummaryModel.of(album) for album in albums])


@router.get(
    "/library/albums/{album_key}",
    response_model=AlbumContextModel,
    summary="One album's tracks in disc/track order",
)
def get_library_album(
    album_key: str,
    library: Annotated[LibraryService, Depends(get_library_service)],
) -> AlbumContextModel:
    return AlbumContextModel.of(library.album_context(album_key))


@router.get(
    "/library/years",
    response_model=PageModel[YearSummaryModel],
    summary="List local release years",
)
def list_library_years(
    library: Annotated[LibraryService, Depends(get_library_service)],
) -> PageModel[YearSummaryModel]:
    """Every release-year grouping, real years first and Unknown Year last."""
    years = library.list_years()
    return PageModel(items=[YearSummaryModel.of(year) for year in years])


@router.get(
    "/library/years/{year_key}",
    response_model=YearContextModel,
    summary="One release year's tracks in play order",
)
def get_library_year(
    year_key: str,
    library: Annotated[LibraryService, Depends(get_library_service)],
) -> YearContextModel:
    return YearContextModel.of(library.year_context(year_key))
