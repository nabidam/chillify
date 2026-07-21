"""Playlist routes.

Playlists are the one resource scoped to a profile, so creation and listing are
addressed through the profile that owns them. Reading, renaming, and filling
one address the playlist directly, because a playlist already names its owner.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, status

from chillify.api.dependencies import get_playlist_service
from chillify.api.schemas.common import PageModel
from chillify.api.schemas.playlists import (
    AddPlaylistTrackRequest,
    CreatePlaylistRequest,
    PlaylistDetailModel,
    PlaylistModel,
    RenamePlaylistRequest,
)
from chillify.application.playlists import PlaylistService
from chillify.domain.models import PlaylistId, ProfileId, TrackId

router = APIRouter(tags=["playlists"])


@router.get(
    "/profiles/{profile_id}/playlists",
    response_model=PageModel[PlaylistModel],
    summary="List one profile's playlists",
)
def list_playlists(
    playlists: Annotated[PlaylistService, Depends(get_playlist_service)],
    profile_id: Annotated[str, Path(description="Profile ID.")],
) -> PageModel[PlaylistModel]:
    """Every playlist of one profile, most recently changed first.

    The list is bounded by household use, so it is served whole; the page
    envelope is present for shape consistency, never for paging.
    """
    items = playlists.list_playlists(ProfileId(profile_id))
    return PageModel(items=[PlaylistModel.of(playlist) for playlist in items])


@router.post(
    "/profiles/{profile_id}/playlists",
    response_model=PlaylistModel,
    status_code=status.HTTP_201_CREATED,
    summary="Create a playlist for one profile",
)
def create_playlist(
    request: CreatePlaylistRequest,
    playlists: Annotated[PlaylistService, Depends(get_playlist_service)],
    profile_id: Annotated[str, Path(description="Profile ID.")],
) -> PlaylistModel:
    return PlaylistModel.of(playlists.create_playlist(ProfileId(profile_id), request.name))


@router.get(
    "/playlists/{playlist_id}",
    response_model=PlaylistDetailModel,
    summary="Read one playlist and its tracks in saved order",
)
def read_playlist(
    playlists: Annotated[PlaylistService, Depends(get_playlist_service)],
    playlist_id: Annotated[str, Path(description="Playlist ID.")],
) -> PlaylistDetailModel:
    return PlaylistDetailModel.of(playlists.get_playlist(PlaylistId(playlist_id)))


@router.patch(
    "/playlists/{playlist_id}",
    response_model=PlaylistModel,
    summary="Rename one playlist",
)
def rename_playlist(
    request: RenamePlaylistRequest,
    playlists: Annotated[PlaylistService, Depends(get_playlist_service)],
    playlist_id: Annotated[str, Path(description="Playlist ID.")],
) -> PlaylistModel:
    """Rename under the submitted revision, so a concurrent rename is visible."""
    return PlaylistModel.of(
        playlists.rename_playlist(
            PlaylistId(playlist_id), raw_name=request.name, expected_revision=request.revision
        )
    )


@router.post(
    "/playlists/{playlist_id}/tracks",
    response_model=PlaylistDetailModel,
    summary="Add one track to the end of a playlist",
)
def add_playlist_track(
    request: AddPlaylistTrackRequest,
    playlists: Annotated[PlaylistService, Depends(get_playlist_service)],
    playlist_id: Annotated[str, Path(description="Playlist ID.")],
) -> PlaylistDetailModel:
    return PlaylistDetailModel.of(
        playlists.add_track(
            PlaylistId(playlist_id),
            TrackId(request.track_id),
            expected_revision=request.revision,
        )
    )
