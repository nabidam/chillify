"""Playlist routes.

Playlists are the one resource scoped to a profile, so creation and listing are
addressed through the profile that owns them. Reading, renaming, and filling
one address the playlist directly, because a playlist already names its owner.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Path, status

from chillify.api.dependencies import get_playlist_service
from chillify.api.schemas.common import PageModel
from chillify.api.schemas.playlists import (
    AddPlaylistTrackRequest,
    CreatePlaylistRequest,
    PlaylistDetailModel,
    PlaylistModel,
    RenamePlaylistRequest,
    ReorderPlaylistRequest,
)
from chillify.application.playlists import PlaylistService
from chillify.domain.errors import ValidationFailedError
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


@router.delete(
    "/playlists/{playlist_id}/tracks/{track_id}",
    response_model=PlaylistDetailModel,
    summary="Remove one track from a playlist without deleting the track",
)
def remove_playlist_track(
    playlists: Annotated[PlaylistService, Depends(get_playlist_service)],
    playlist_id: Annotated[str, Path(description="Playlist ID.")],
    track_id: Annotated[str, Path(description="Track ID.")],
    if_match: Annotated[
        str | None,
        Header(alias="If-Match", description="The playlist's current `revision`."),
    ] = None,
) -> PlaylistDetailModel:
    """Drop the track from this playlist's saved order; the shared track stays.

    `If-Match` carries the revision so a removal made against a stale view is
    refused rather than silently reordering somebody else's change away.
    """
    return PlaylistDetailModel.of(
        playlists.remove_track(
            PlaylistId(playlist_id),
            TrackId(track_id),
            expected_revision=_revision_from(if_match),
        )
    )


@router.put(
    "/playlists/{playlist_id}/order",
    response_model=PlaylistDetailModel,
    summary="Rewrite a playlist's saved order",
)
def reorder_playlist(
    request: ReorderPlaylistRequest,
    playlists: Annotated[PlaylistService, Depends(get_playlist_service)],
    playlist_id: Annotated[str, Path(description="Playlist ID.")],
) -> PlaylistDetailModel:
    """Apply the whole submitted order under its revision, all or nothing."""
    return PlaylistDetailModel.of(
        playlists.reorder(
            PlaylistId(playlist_id),
            tuple(TrackId(track_id) for track_id in request.track_ids),
            expected_revision=request.revision,
        )
    )


def _revision_from(if_match: str | None) -> int:
    """Parse the `If-Match` header into the revision the change must match."""
    if if_match is None:
        raise ValidationFailedError(
            "This change needs the playlist's current revision in an If-Match header.",
            field="If-Match",
        )
    candidate = if_match.strip().strip('"').removeprefix("W/").strip('"')
    if not candidate.isdigit():
        raise ValidationFailedError(
            "The If-Match header must carry the playlist's numeric revision.",
            field="If-Match",
        )
    return int(candidate)
