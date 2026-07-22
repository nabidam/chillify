"""Playlist use cases.

A playlist is the one piece of state that belongs to a profile rather than to
the household: the library, the downloads, and the settings are shared, and the
playlists are not. Every use case here therefore starts from a profile or from
a playlist that already names one.

Each public method owns one transaction boundary. Routes call these; they never
open a session or touch a repository themselves.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from sqlalchemy.orm import Session, sessionmaker

from chillify.domain.models import (
    Playlist,
    PlaylistDetail,
    PlaylistId,
    ProfileId,
    TrackId,
)
from chillify.domain.normalization import validate_playlist_name
from chillify.infrastructure.db.repositories import PlaylistRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PlaylistService:
    """Creating, reading, renaming, and filling one profile's playlists."""

    session_factory: sessionmaker[Session]

    @contextmanager
    def _transaction(self) -> Iterator[Session]:
        session = self.session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def list_playlists(self, profile_id: ProfileId) -> tuple[Playlist, ...]:
        with self._transaction() as session:
            return PlaylistRepository(session).list_for_profile(profile_id)

    def create_playlist(self, profile_id: ProfileId, raw_name: str) -> Playlist:
        """Validate and store one playlist for this profile.

        Validation happens before the transaction opens so a rejected name never
        holds a write lock on the shared SQLite file.
        """
        name = validate_playlist_name(raw_name)
        with self._transaction() as session:
            playlist = PlaylistRepository(session).create(profile_id, name)
        logger.info(
            "playlist created",
            extra={"playlist_id": str(playlist.id), "profile_id": str(profile_id)},
        )
        return playlist

    def get_playlist(self, playlist_id: PlaylistId) -> PlaylistDetail:
        with self._transaction() as session:
            return PlaylistRepository(session).get_detail(playlist_id)

    def rename_playlist(
        self, playlist_id: PlaylistId, *, raw_name: str, expected_revision: int
    ) -> Playlist:
        name = validate_playlist_name(raw_name)
        with self._transaction() as session:
            return PlaylistRepository(session).rename(
                playlist_id, name=name, expected_revision=expected_revision
            )

    def add_track(
        self, playlist_id: PlaylistId, track_id: TrackId, *, expected_revision: int
    ) -> PlaylistDetail:
        with self._transaction() as session:
            return PlaylistRepository(session).add_track(
                playlist_id, track_id, expected_revision=expected_revision
            )

    def remove_track(
        self, playlist_id: PlaylistId, track_id: TrackId, *, expected_revision: int
    ) -> PlaylistDetail:
        """Drop one track from the saved order, leaving the shared track alone."""
        with self._transaction() as session:
            return PlaylistRepository(session).remove_track(
                playlist_id, track_id, expected_revision=expected_revision
            )

    def reorder(
        self,
        playlist_id: PlaylistId,
        track_ids: tuple[TrackId, ...],
        *,
        expected_revision: int,
    ) -> PlaylistDetail:
        """Rewrite the whole saved order under the submitted revision."""
        with self._transaction() as session:
            return PlaylistRepository(session).reorder(
                playlist_id, track_ids, expected_revision=expected_revision
            )
