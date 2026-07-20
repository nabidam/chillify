"""Remote discovery use cases.

Local search is not here: it is `GET /library/tracks?q=`, served by the library
use cases against the database alone. That separation is the local-first rule
made structural — no code path from typing in the search box reaches a
provider, and only the explicit Deezer action does.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from sqlalchemy.orm import Session, sessionmaker

from chillify.domain.models import TrackId, normalize_metadata
from chillify.domain.protocols import (
    DISCOVERY_LIMIT_DEFAULT,
    DISCOVERY_LIMIT_MAX,
    TrackCandidate,
)
from chillify.infrastructure.db.repositories import TrackRepository
from chillify.infrastructure.providers.registry import ProviderRegistry

logger = logging.getLogger(__name__)

DEEZER_PROVIDER = "deezer"


@dataclass(frozen=True, slots=True)
class RemoteResult:
    """One remote candidate and whether the library already holds it.

    The duplicate link is resolved server-side because the browser cannot run
    the ordered identity rules — provider ID, then ISRC, then normalized
    artist/title — without downloading the whole library first.
    """

    candidate: TrackCandidate
    existing_track_id: TrackId | None

    @property
    def is_duplicate(self) -> bool:
        return self.existing_track_id is not None


@dataclass(frozen=True, slots=True)
class SearchService:
    """Explicit online discovery, and nothing else."""

    session_factory: sessionmaker[Session]
    registry: ProviderRegistry
    proxy_url: str | None = None

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

    def search_deezer(
        self, query: str, *, limit: int = DISCOVERY_LIMIT_DEFAULT
    ) -> tuple[RemoteResult, ...]:
        """Search Deezer, then mark every candidate the library already holds.

        The provider call happens outside the database transaction: an outbound
        request that hangs must not hold a write lock on the shared SQLite file
        while the household is trying to play music.
        """
        bounded = max(1, min(limit, DISCOVERY_LIMIT_MAX))
        provider = self.registry.require_discovery(DEEZER_PROVIDER)
        candidates = provider.search(query, bounded, self.proxy_url)
        logger.info(
            "deezer search completed",
            extra={"result_count": len(candidates), "requested_limit": bounded},
        )

        with self._transaction() as session:
            tracks = TrackRepository(session)
            return tuple(
                RemoteResult(
                    candidate=candidate,
                    existing_track_id=_existing_track_id(tracks, candidate),
                )
                for candidate in candidates
            )


def _existing_track_id(tracks: TrackRepository, candidate: TrackCandidate) -> TrackId | None:
    normalized = normalize_metadata(
        artist=candidate.artist, title=candidate.title, album=candidate.album
    )
    existing = tracks.find_duplicate(
        provider=candidate.provider,
        source_id=candidate.source_id,
        isrc=candidate.isrc,
        normalized_artist=normalized.normalized_artist,
        normalized_title=normalized.normalized_title,
    )
    return None if existing is None else existing.id
