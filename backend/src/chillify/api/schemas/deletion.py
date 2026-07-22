"""Deletion response shapes.

Deleting a track returns no body; only its impact has a shape, and that shape
discloses a count, never a path or a playlist name.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from chillify.application.deletion import DeleteImpact


class DeleteImpactModel(BaseModel):
    """The server-owned references S15 warns about before a permanent deletion.

    The browser adds the current-track and session-queue occurrences it reads
    from its own store; the server only knows the durable playlist references.
    """

    playlist_count: int = Field(
        description="How many playlists across every profile hold this track.",
    )

    @classmethod
    def of(cls, impact: DeleteImpact) -> DeleteImpactModel:
        return cls(playlist_count=impact.playlist_count)
