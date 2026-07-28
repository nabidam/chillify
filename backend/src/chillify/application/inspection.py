"""Tracked link-inspection use cases and provider fallback policy."""

from __future__ import annotations

import inspect as inspect_module
import json
import logging
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from urllib.parse import urlsplit

from sqlalchemy.orm import Session, sessionmaker

from chillify.application.settings import InspectionMode, InspectionSettings
from chillify.domain.errors import (
    AcquisitionCancelledError,
    ChillifyError,
    ProviderResponseError,
    RecordNotFoundError,
    UnsupportedEntityError,
    ValidationFailedError,
)
from chillify.domain.jobs import JobProvider, SourceType
from chillify.domain.models import TrackId, normalize_metadata
from chillify.domain.protocols import CancelledCallback, LinkInspector, TrackCandidate
from chillify.infrastructure.db.repositories import (
    InspectionRecord,
    InspectionRepository,
    TrackRepository,
)

logger = logging.getLogger(__name__)

MAX_URL_LENGTH = 2048
INSPECTION_TTL_SECONDS = 300
INSPECTION_POLL_SECONDS = 0.1
HEARTBEAT_SECONDS = 15.0


@dataclass(frozen=True, slots=True)
class InspectionPolicy:
    """Choose the configured fast path and make fallback explicit."""

    spotify_api: LinkInspector
    spotdl: LinkInspector
    youtube: LinkInspector | None = None
    proxy_provider: Callable[[], str | None] = lambda: None

    def inspect(
        self,
        url: str,
        mode: InspectionMode | str,
        settings: InspectionSettings,
        *,
        phase_callback: Callable[[str, str], None] | None = None,
        cancelled: CancelledCallback | None = None,
    ) -> TrackCandidate:
        """Inspect one URL using the selected mode and fallback."""
        selected_mode = InspectionMode(mode)
        logger.debug(
            "inspection settings snapshot captured",
            extra={
                "timeout_spotify_s": settings.timeout_spotify_s,
                "timeout_spotdl_s": settings.timeout_spotdl_s,
                "timeout_ytdlp_s": settings.timeout_ytdlp_s,
            },
        )
        proxy = self.proxy_provider()

        if self.spotify_api.supports(url):
            if selected_mode is InspectionMode.THOROUGH:
                return self._inspect(
                    self.spotdl,
                    url,
                    proxy,
                    phase="matching_spotdl",
                    phase_callback=phase_callback,
                    cancelled=cancelled,
                )
            try:
                return self._inspect(
                    self.spotify_api,
                    url,
                    proxy,
                    phase="reading_spotify",
                    phase_callback=phase_callback,
                    cancelled=cancelled,
                )
            except ProviderResponseError as exc:
                if not _may_fallback(exc):
                    raise
                logger.info(
                    "spotify api inspection falling back to spotdl",
                    extra={"reason": exc.context.get("reason", "provider_failure")},
                )
                try:
                    return self._inspect(
                        self.spotdl,
                        url,
                        proxy,
                        phase="matching_spotdl",
                        phase_callback=phase_callback,
                        cancelled=cancelled,
                    )
                except ProviderResponseError as spotdl_error:
                    raise ProviderResponseError(
                        "Spotify and SpotDL could not inspect that link.",
                        context={"provider": "inspection", "fallback": False},
                    ) from spotdl_error

        if self.youtube is not None and self.youtube.supports(url):
            return self._inspect(
                self.youtube,
                url,
                proxy,
                phase="inspecting_youtube",
                phase_callback=phase_callback,
                cancelled=cancelled,
            )
        return self._inspect(
            self.spotdl,
            url,
            proxy,
            phase="matching_spotdl",
            phase_callback=phase_callback,
            cancelled=cancelled,
        )

    @staticmethod
    def _inspect(
        inspector: LinkInspector,
        url: str,
        proxy: str | None,
        *,
        phase: str,
        phase_callback: Callable[[str, str], None] | None,
        cancelled: CancelledCallback | None,
    ) -> TrackCandidate:
        if cancelled is not None and cancelled():
            raise AcquisitionCancelledError("That inspection was cancelled.")
        if phase_callback is not None:
            phase_callback(phase, inspector.name)
        parameters = inspect_module.signature(inspector.inspect).parameters
        if "cancelled" in parameters:
            candidate = inspector.inspect(url, proxy, cancelled=cancelled)  # type: ignore[call-arg]
        else:
            candidate = inspector.inspect(url, proxy)
        if cancelled is not None and cancelled():
            raise AcquisitionCancelledError("That inspection was cancelled.")
        return candidate


class InspectionPhase(StrEnum):
    READING_SPOTIFY = "reading_spotify"
    MATCHING_SPOTDL = "matching_spotdl"
    INSPECTING_YOUTUBE = "inspecting_youtube"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    FAILED = "failed"
    DONE = "done"


TERMINAL_PHASES = frozenset(
    {
        InspectionPhase.CANCELLED.value,
        InspectionPhase.EXPIRED.value,
        InspectionPhase.FAILED.value,
        InspectionPhase.DONE.value,
    }
)


@dataclass(frozen=True, slots=True)
class InspectionAccepted:
    id: str
    phase: str
    started_at: datetime


@dataclass(frozen=True, slots=True)
class InspectionService:
    """Run one inspection off the event loop and persist observable state."""

    session_factory: sessionmaker[Session]
    spotify_api: LinkInspector
    spotdl: LinkInspector
    youtube: LinkInspector | None
    settings_provider: Callable[[], InspectionSettings]
    proxy_provider: Callable[[], str | None] = lambda: None
    ttl_seconds: int = INSPECTION_TTL_SECONDS

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

    def start(self, raw_url: str) -> InspectionAccepted:
        url = _validate_url(raw_url)
        settings = self.settings_provider()
        phase = self._initial_phase(url, settings.mode)
        provider = self._initial_provider(url, settings.mode)
        started_at = datetime.now(UTC)
        with self._transaction() as session:
            record = InspectionRepository(session).create(
                url=url,
                mode=settings.mode.value,
                phase=phase,
                provider=provider,
                started_at=started_at,
                expires_at=started_at + timedelta(seconds=self.ttl_seconds),
            )
        thread = threading.Thread(
            target=self._run,
            args=(record.id, url, settings),
            name=f"chillify-inspection-{record.id[:8]}",
            daemon=True,
        )
        thread.start()
        return InspectionAccepted(id=record.id, phase=record.phase, started_at=record.started_at)

    def cancel(self, inspection_id: str) -> None:
        with self._transaction() as session:
            record = InspectionRepository(session).request_cancel(
                inspection_id, now=datetime.now(UTC)
            )
        if record is None:
            raise RecordNotFoundError("That inspection does not exist or has expired.")

    def ensure_active(self, inspection_id: str) -> InspectionRecord:
        with self._transaction() as session:
            record = InspectionRepository(session).get(inspection_id)
        if record is None:
            raise RecordNotFoundError("That inspection does not exist or has expired.")
        return record

    def event_frames(self, inspection_id: str) -> Iterator[str]:
        """Yield changed inspection envelopes and the standard SSE heartbeat."""
        last_phase: str | None = None
        last_result: str | None = None
        last_heartbeat = time.monotonic()
        while True:
            with self._transaction() as session:
                repository = InspectionRepository(session)
                record = repository.get(inspection_id, include_expired=True)
                if record is None:
                    return
                if record.expires_at <= datetime.now(UTC) and record.phase not in TERMINAL_PHASES:
                    record = repository.expire(inspection_id, now=datetime.now(UTC))
            if record is None:
                return
            if record.phase == InspectionPhase.EXPIRED.value:
                yield _inspection_frame(record)
                return

            result_marker = json.dumps(record.result, sort_keys=True)
            if last_phase is None:
                for replay_phase, replay_provider in self._replay_phases(record):
                    replay = (
                        record
                        if replay_phase == record.phase
                        else replace(
                            record,
                            phase=replay_phase,
                            provider=replay_provider,
                            result=None,
                            error=None,
                        )
                    )
                    yield _inspection_frame(replay)
                last_phase = record.phase
                last_result = result_marker
                last_heartbeat = time.monotonic()
                if record.phase in TERMINAL_PHASES:
                    return
                time.sleep(INSPECTION_POLL_SECONDS)
                continue
            if record.phase != last_phase or result_marker != last_result:
                last_phase = record.phase
                last_result = result_marker
                last_heartbeat = time.monotonic()
                yield _inspection_frame(record)
                if record.phase in TERMINAL_PHASES:
                    return
            elif time.monotonic() - last_heartbeat >= HEARTBEAT_SECONDS:
                last_heartbeat = time.monotonic()
                yield ": heartbeat\n\n"
            time.sleep(INSPECTION_POLL_SECONDS)

    def _replay_phases(self, record: InspectionRecord) -> tuple[tuple[str, str | None], ...]:
        """Reconstruct the small phase history retained by the row contract."""
        initial = self._initial_phase(record.url, InspectionMode(record.mode))
        provider = self._initial_provider(record.url, InspectionMode(record.mode))
        phases: list[tuple[str, str | None]] = [(initial, provider)]
        used_spotdl_fallback = (
            initial == InspectionPhase.READING_SPOTIFY.value and record.provider == "spotdl"
        )
        if used_spotdl_fallback:
            phases.append((InspectionPhase.MATCHING_SPOTDL.value, "spotdl"))
        if record.phase not in {phase for phase, _ in phases}:
            phases.append((record.phase, record.provider))
        return tuple(phases)

    def _initial_phase(self, url: str, mode: InspectionMode) -> str:
        if self.spotify_api.supports(url):
            return (
                InspectionPhase.READING_SPOTIFY.value
                if mode is InspectionMode.FAST
                else InspectionPhase.MATCHING_SPOTDL.value
            )
        if self.youtube is not None and self.youtube.supports(url):
            return InspectionPhase.INSPECTING_YOUTUBE.value
        if self.spotdl.supports(url):
            return InspectionPhase.MATCHING_SPOTDL.value
        raise UnsupportedEntityError(
            "Chillify can only inspect a single Spotify track or YouTube video.",
            field="url",
            context={"reason": "unsupported_host"},
        )

    def _initial_provider(self, url: str, mode: InspectionMode) -> str:
        if self.spotify_api.supports(url):
            return "spotify_api" if mode is InspectionMode.FAST else "spotdl"
        if self.youtube is not None and self.youtube.supports(url):
            return "yt_dlp"
        return "spotdl"

    def _run(self, inspection_id: str, url: str, settings: InspectionSettings) -> None:
        policy = InspectionPolicy(
            spotify_api=self.spotify_api,
            spotdl=self.spotdl,
            youtube=self.youtube,
            proxy_provider=self.proxy_provider,
        )

        def cancelled() -> bool:
            with self._transaction() as session:
                record = InspectionRepository(session).get(inspection_id, include_expired=True)
            return (
                record is None
                or record.cancel_requested_at is not None
                or record.expires_at <= datetime.now(UTC)
            )

        def phase_changed(phase: str, provider: str) -> None:
            with self._transaction() as session:
                InspectionRepository(session).update_phase(
                    inspection_id, phase=phase, provider=provider
                )

        try:
            candidate = policy.inspect(
                url,
                settings.mode,
                settings,
                phase_callback=phase_changed,
                cancelled=cancelled,
            )
            if cancelled():
                raise AcquisitionCancelledError("That inspection was cancelled.")
            result = self._result(url, candidate)
            with self._transaction() as session:
                InspectionRepository(session).complete(inspection_id, result=result)
        except AcquisitionCancelledError:
            with self._transaction() as session:
                repository = InspectionRepository(session)
                record = repository.get(inspection_id, include_expired=True)
                if record is not None and record.expires_at <= datetime.now(UTC):
                    repository.expire(inspection_id, now=datetime.now(UTC))
                else:
                    repository.request_cancel(inspection_id, now=datetime.now(UTC))
        except ChillifyError as exc:
            if cancelled():
                with self._transaction() as session:
                    InspectionRepository(session).request_cancel(
                        inspection_id, now=datetime.now(UTC)
                    )
                return
            self._fail(inspection_id, code=exc.code, message=exc.message)
        except Exception:
            logger.exception("inspection worker failed", extra={"inspection_id": inspection_id})
            if cancelled():
                with self._transaction() as session:
                    InspectionRepository(session).request_cancel(
                        inspection_id, now=datetime.now(UTC)
                    )
            else:
                self._fail(
                    inspection_id,
                    code="inspection_failed",
                    message="The link could not be inspected.",
                )

    def _fail(self, inspection_id: str, *, code: str, message: str) -> None:
        with self._transaction() as session:
            InspectionRepository(session).fail(
                inspection_id,
                error={"code": code, "message": message},
            )

    def _result(self, url: str, candidate: TrackCandidate) -> dict[str, object]:
        source_type, provider, review_required = _source_policy(url)
        existing = self._existing_track_id(candidate)
        return {
            "source_type": source_type.value,
            "provider": provider.value,
            "review_required": review_required,
            "candidate": _candidate_json(candidate),
            "is_playable": False,
            "existing_track_id": None if existing is None else str(existing),
        }

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


def _validate_url(raw_url: str) -> str:
    url = raw_url.strip()
    if not url:
        raise ValidationFailedError("Paste a link to add.", field="url")
    if len(url) > MAX_URL_LENGTH:
        raise ValidationFailedError("That link is too long to be a track URL.", field="url")
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValidationFailedError(
            "That is not a link. Paste one Spotify track or YouTube video URL.", field="url"
        )
    return url


def _source_policy(url: str) -> tuple[SourceType, JobProvider, bool]:
    host = (urlsplit(url).hostname or "").lower()
    if host in {"www.youtube.com", "youtube.com", "youtu.be", "music.youtube.com"}:
        return SourceType.YOUTUBE_VIDEO, JobProvider.YT_DLP, True
    return SourceType.SPOTIFY_TRACK, JobProvider.SPOTDL, False


def _candidate_json(candidate: TrackCandidate) -> dict[str, object | None]:
    return {
        "provider": candidate.provider,
        "source_id": candidate.source_id,
        "source_url": candidate.source_url,
        "title": candidate.title,
        "artist": candidate.artist,
        "album": candidate.album,
        "release_year": candidate.release_year,
        "disc_number": candidate.disc_number,
        "track_number": candidate.track_number,
        "duration_ms": candidate.duration_ms,
        "isrc": candidate.isrc,
        "artwork_url": candidate.artwork_url,
        "acquisition_locator": candidate.acquisition_locator,
        "raw_fingerprint": candidate.raw_fingerprint,
        "is_playable": False,
    }


def _inspection_frame(record: InspectionRecord) -> str:
    elapsed_ms = max(0, round((datetime.now(UTC) - record.started_at).total_seconds() * 1000))
    payload: dict[str, object] = {
        "phase": record.phase,
        "elapsed_ms": elapsed_ms,
        "provider": record.provider,
        "terminal": record.phase in TERMINAL_PHASES,
    }
    if record.result is not None:
        payload["result"] = record.result
    if record.error is not None:
        payload["error"] = record.error
    return (
        "event: inspection.changed\ndata: "
        + json.dumps(payload, separators=(",", ":"), sort_keys=True)
        + "\n\n"
    )


def _may_fallback(error: ProviderResponseError) -> bool:
    return error.context.get("fallback", True) is True
