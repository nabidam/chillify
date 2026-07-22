"""Playlist request and response shapes."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from chillify.api.schemas.tracks import TrackSummaryModel
from chillify.domain.models import Playlist, PlaylistDetail
from chillify.domain.normalization import PLAYLIST_NAME_MAX_LENGTH


class PlaylistModel(BaseModel):
    """One playlist as the sidebar and S9 render it."""

    id: str
    profile_id: str
    name: str
    track_count: int
    revision: int = Field(description="Supply as `revision` on the next change to this playlist.")
    created_at: datetime
    updated_at: datetime

    @classmethod
    def of(cls, playlist: Playlist) -> PlaylistModel:
        return cls(
            id=str(playlist.id),
            profile_id=str(playlist.profile_id),
            name=playlist.name,
            track_count=playlist.track_count,
            revision=playlist.revision,
            created_at=playlist.created_at,
            updated_at=playlist.updated_at,
        )


class PlaylistDetailModel(BaseModel):
    """One playlist and its tracks in saved order."""

    playlist: PlaylistModel
    tracks: list[TrackSummaryModel]

    @classmethod
    def of(cls, detail: PlaylistDetail) -> PlaylistDetailModel:
        return cls(
            playlist=PlaylistModel.of(detail.playlist),
            tracks=[TrackSummaryModel.of(track) for track in detail.tracks],
        )


class CreatePlaylistRequest(BaseModel):
    """S16, creating. Only the name is editable."""

    name: str = Field(min_length=1, max_length=PLAYLIST_NAME_MAX_LENGTH)


class RenamePlaylistRequest(BaseModel):
    """S16, renaming. The revision is what makes a concurrent rename visible."""

    name: str = Field(min_length=1, max_length=PLAYLIST_NAME_MAX_LENGTH)
    revision: int = Field(ge=1)


class AddPlaylistTrackRequest(BaseModel):
    """One row action: append a local track to the end of the saved order."""

    track_id: str = Field(min_length=1)
    revision: int = Field(ge=1)


class ReorderPlaylistRequest(BaseModel):
    """S10 drag-reorder: the complete saved order, most-first, under a revision.

    The list is the whole membership rewritten, never a delta, so a concurrent
    change is caught by the revision before the order is applied.
    """

    track_ids: list[str] = Field(min_length=1)
    revision: int = Field(ge=1)
