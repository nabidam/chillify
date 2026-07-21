"""Artwork staging use cases.

Staging exists so one save can change everything at once. The person picks a
cover, sees it, and nothing about their track has changed yet; the image waits
as a validated JPEG until the save that consumes it commits, or until it
expires unused.

A stage is therefore never a mutation. No method here touches a track, and the
only thing any of them writes is one file and one row that both belong to
nobody until a save claims them.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from chillify.domain.errors import ProviderDisabledError
from chillify.domain.models import ArtworkOrigin, ArtworkStage
from chillify.infrastructure.db.repositories import ArtworkStageRepository
from chillify.infrastructure.media.artwork import (
    ARTWORK_MIME_TYPE,
    normalize_cover,
    remove_stage,
    write_stage,
)
from chillify.infrastructure.media.mutations import (
    discard_mutation_workspace,
    staging_directory,
)
from chillify.infrastructure.providers.registry import ProviderRegistry

logger = logging.getLogger(__name__)

# One hour, as the artwork-stage contract fixes it. Long enough to finish an
# edit that was interrupted by a phone call, short enough that an abandoned
# staging directory is not a storage problem.
ARTWORK_STAGE_LIFETIME = timedelta(hours=1)


@dataclass(frozen=True, slots=True)
class ArtworkService:
    """Validating, normalizing, and staging one replacement cover image."""

    session_factory: sessionmaker[Session]
    music_root: Path
    registry: ProviderRegistry

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

    def stage_upload(self, data: bytes) -> ArtworkStage:
        """Stage a cover the person uploaded from their own device."""
        return self._stage(data, origin=ArtworkOrigin.UPLOAD)

    def stage_from_url(self, url: str) -> ArtworkStage:
        """Stage a cover fetched from a URL through the outbound policy.

        Fetching is a provider capability rather than a bare HTTP call so it
        goes through the same proxy, timeout, and retry rules as everything
        else Chillify reaches for. Until an adapter is bound, this is reported
        as unavailable rather than quietly bypassing that policy.
        """
        fetcher = self.registry.artwork.get("url")
        if fetcher is None:
            raise ProviderDisabledError(
                "Fetching cover art from a link is unavailable in this deployment.",
                context={"origin": str(ArtworkOrigin.URL)},
            )
        with self._workspace() as workspace:
            artifact = fetcher.fetch(url, str(workspace), None)
            data = Path(artifact.location).read_bytes()
        return self._stage(data, origin=ArtworkOrigin.URL)

    def stage_from_lastfm(self, *, artist: str, title: str, album: str | None) -> ArtworkStage:
        """Stage the best cover Last.fm has for one track, when it has any."""
        fetcher = self.registry.artwork.get("lastfm")
        if fetcher is None:
            raise ProviderDisabledError(
                "Last.fm cover lookup is not configured for this deployment.",
                context={"origin": str(ArtworkOrigin.LASTFM)},
            )
        query = " ".join(part for part in (artist, album, title) if part)
        with self._workspace() as workspace:
            artifact = fetcher.fetch(query, str(workspace), None)
            data = Path(artifact.location).read_bytes()
        return self._stage(data, origin=ArtworkOrigin.LASTFM)

    def prune_expired(self) -> int:
        """Remove unconsumed stages past their hour, and their files.

        Opportunistic: expiry is a retention rule rather than a scheduled job,
        so it runs when a stage is created and again at startup.
        """
        now = datetime.now(UTC)
        removed = 0
        with self._transaction() as session:
            repository = ArtworkStageRepository(session)
            for stage in repository.expired(now=now):
                remove_stage(self.music_root, stage.file_relpath)
                repository.delete(stage.id)
                removed += 1
        if removed:
            logger.info("expired artwork stages removed", extra={"removed": removed})
        return removed

    def _stage(self, data: bytes, *, origin: ArtworkOrigin) -> ArtworkStage:
        """Normalize, persist, and record one staged cover.

        The file is written before the row, and the row is what makes the file
        reachable, so an interrupted stage leaves at most an orphan file that
        cleanup removes.
        """
        cover = normalize_cover(data)
        stage_id = str(uuid.uuid7())
        relative = write_stage(self.music_root, stage_id, cover)
        now = datetime.now(UTC)
        try:
            with self._transaction() as session:
                stage = ArtworkStageRepository(session).create(
                    stage_id=stage_id,
                    file_relpath=relative,
                    mime_type=ARTWORK_MIME_TYPE,
                    content_sha256=cover.content_sha256,
                    size_bytes=cover.size_bytes,
                    origin=origin,
                    now=now,
                    lifetime=ARTWORK_STAGE_LIFETIME,
                )
        except Exception:
            remove_stage(self.music_root, relative)
            raise
        logger.info("artwork staged", extra={"stage_id": stage_id, "origin": str(origin)})
        # Opportunistic, and after the new stage is committed: expiry is a
        # retention rule rather than a scheduled job, and a cleanup failure must
        # never fail the staging the person actually asked for.
        try:
            self.prune_expired()
        except Exception:
            logger.exception("expired artwork stages could not be pruned")
        return stage

    @contextmanager
    def _workspace(self) -> Iterator[Path]:
        """A disposable directory for one outbound fetch."""
        fetch_id = str(uuid.uuid7())
        workspace = staging_directory(self.music_root, fetch_id)
        try:
            yield workspace
        finally:
            discard_mutation_workspace(self.music_root, fetch_id)
