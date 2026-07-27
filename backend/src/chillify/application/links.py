"""Direct-link inspection use case.

`POST /links/inspect` recognizes one submitted URL, inspects its metadata, and
reports a normalized candidate plus whether it needs S5 review before queueing.
It never creates a job: inspection is a read, and only `POST /downloads` commits
durable work. An unsupported, malformed, or bulk link therefore fails here with
a typed error and nothing durable happens.

Recognition and metadata inspection both live in the provider adapters behind
`LinkInspector`. This use case owns only the routing — pick the adapter whose
host matches — and the local-duplicate resolution the browser cannot do.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from urllib.parse import urlsplit

from sqlalchemy.orm import Session, sessionmaker

from chillify.domain.errors import UnsupportedEntityError, ValidationFailedError
from chillify.domain.jobs import JobProvider, SourceType
from chillify.domain.models import TrackId, normalize_metadata
from chillify.domain.protocols import LinkInspector, TrackCandidate
from chillify.infrastructure.db.repositories import TrackRepository

logger = logging.getLogger(__name__)

# Longer than any real track or video URL, short enough to refuse a paste that
# is plainly not a link before it reaches an adapter.
MAX_URL_LENGTH = 2048

# Which source each acquisition provider inspects, and whether a person must
# review the extracted metadata before it is queued. YouTube metadata is
# unreliable, so it goes through S5; Spotify metadata is authoritative.
_PROVIDER_POLICY: dict[JobProvider, tuple[SourceType, bool]] = {
    JobProvider.YT_DLP: (SourceType.YOUTUBE_VIDEO, True),
    JobProvider.SPOTDL: (SourceType.SPOTIFY_TRACK, False),
}


@dataclass(frozen=True, slots=True)
class RegisteredInspector:
    """One bound inspector together with the provider identity it serves."""

    provider: JobProvider
    inspector: LinkInspector


@dataclass(frozen=True, slots=True)
class LinkInspection:
    """The result of inspecting one link: what to queue, and how."""

    source_type: SourceType
    provider: JobProvider
    review_required: bool
    candidate: TrackCandidate
    existing_track_id: TrackId | None

    @property
    def is_duplicate(self) -> bool:
        return self.existing_track_id is not None


@dataclass(frozen=True, slots=True)
class LinkInspectionService:
    """Recognize, inspect, and duplicate-check one submitted URL."""

    session_factory: sessionmaker[Session]
    inspectors: tuple[RegisteredInspector, ...]
    # Read at call time, never snapshotted: an operator who changes the saved
    # proxy must see it take effect on the very next inspection without a
    # restart.
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

    def inspect(self, raw_url: str) -> LinkInspection:
        """Inspect one link, or raise a typed failure that creates no job.

        The URL is validated for shape first, so a plainly malformed paste is a
        `422` before any adapter runs. A recognized host inspects through its
        adapter, which itself rejects a bulk entity before touching the network.
        No host match at all is an unsupported link.
        """
        url = raw_url.strip()
        if not url:
            raise ValidationFailedError("Paste a link to add.", field="url")
        if len(url) > MAX_URL_LENGTH:
            raise ValidationFailedError("That link is too long to be a track URL.", field="url")
        if not _is_web_url(url):
            raise ValidationFailedError(
                "That is not a link. Paste one Spotify track or YouTube video URL.",
                field="url",
            )

        for registered in self.inspectors:
            if not registered.inspector.supports(url):
                continue
            # May raise UnsupportedEntityError for a bulk entity of a recognized
            # host — a playlist, album, or channel — which is the "no durable
            # job" guarantee expressed as a rejection before any download.
            candidate = registered.inspector.inspect(url, self.proxy_provider())
            source_type, review_required = _PROVIDER_POLICY[registered.provider]
            existing = self._existing_track_id(candidate)
            logger.info(
                "link inspected",
                extra={
                    "provider": str(registered.provider),
                    "review_required": review_required,
                    "duplicate": existing is not None,
                },
            )
            return LinkInspection(
                source_type=source_type,
                provider=registered.provider,
                review_required=review_required,
                candidate=candidate,
                existing_track_id=existing,
            )

        raise UnsupportedEntityError(
            "Chillify can only add a single Spotify track or YouTube video.",
            field="url",
            context={"reason": "unsupported_host"},
        )

    def _existing_track_id(self, candidate: TrackCandidate) -> TrackId | None:
        normalized = normalize_metadata(
            artist=candidate.artist, title=candidate.title, album=candidate.album
        )
        with self._transaction() as session:
            existing = TrackRepository(session).find_duplicate(
                provider=candidate.provider,
                source_id=candidate.source_id,
                isrc=candidate.isrc,
                normalized_artist=normalized.normalized_artist,
                normalized_title=normalized.normalized_title,
            )
        return None if existing is None else existing.id


def _is_web_url(url: str) -> bool:
    parts = urlsplit(url)
    return parts.scheme in ("http", "https") and bool(parts.hostname)
