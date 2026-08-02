"""Remote discovery use cases.

Local search is not here: it is `GET /library/tracks?q=`, served by the library
use cases against the database alone. That separation is the local-first rule
made structural — no code path from typing in the search box reaches a
provider, and only the explicit Deezer action does.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from sqlalchemy.orm import Session, sessionmaker

from chillify.domain.errors import ChillifyError
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
RADIO_JAVAN_PROVIDER = "radiojavan"
CATALOG_PROVIDERS = ("musicbrainz", "apple", DEEZER_PROVIDER)


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
    # Read at call time, never snapshotted: an operator who changes the saved
    # proxy must see it take effect on the very next search without a restart.
    proxy_provider: Callable[[], str | None] = lambda: None

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
        return self.search_catalog(query, provider=DEEZER_PROVIDER, limit=limit)

    def search_radio_javan(
        self, query: str, *, limit: int = DISCOVERY_LIMIT_DEFAULT
    ) -> tuple[RemoteResult, ...]:
        """Search only Radio Javan; it never joins the catalog search path."""
        return self.search_catalog(query, provider=RADIO_JAVAN_PROVIDER, limit=limit)

    def browse_radio_javan(self, section: str) -> tuple[RemoteResult, ...]:
        """Browse one explicit Radio Javan section without using catalog search."""
        candidates = self.registry.require_browse(RADIO_JAVAN_PROVIDER).browse(
            section, self.proxy_provider()
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

    def search_catalog(
        self,
        query: str,
        *,
        provider: str = "all",
        limit: int = DISCOVERY_LIMIT_DEFAULT,
    ) -> tuple[RemoteResult, ...]:
        """Search one catalog or all available catalogs.

        The ``all`` view is deliberately best-effort: a temporary failure in one
        remote catalog must not hide usable results from another. Selecting one
        provider remains strict and surfaces that provider's typed failure.
        """
        bounded = max(1, min(limit, DISCOVERY_LIMIT_MAX))
        names = CATALOG_PROVIDERS if provider == "all" else (provider,)
        candidates: list[TrackCandidate] = []
        failures: list[ChillifyError] = []
        successes = 0
        proxy = self.proxy_provider()

        for name in names:
            try:
                adapter = self.registry.require_discovery(name)
                candidates.extend(adapter.search(query, bounded, proxy))
                successes += 1
            except ChillifyError as exc:
                failures.append(exc)
                if provider != "all":
                    raise
                logger.warning(
                    "catalog search provider failed",
                    extra={"provider": name, "error_code": exc.code},
                )

        if successes == 0 and failures:
            raise failures[0]
        logger.info(
            "catalog search completed",
            extra={
                "provider": provider,
                "result_count": len(candidates),
                "requested_limit": bounded,
                "failed_provider_count": len(failures),
            },
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
