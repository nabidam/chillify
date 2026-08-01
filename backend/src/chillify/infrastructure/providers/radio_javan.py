"""Radio Javan discovery and direct native-audio acquisition."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import httpx

from chillify.domain.errors import (
    AcquisitionCancelledError,
    AcquisitionFailedError,
    ProviderResponseError,
)
from chillify.domain.jobs import JobPhase
from chillify.domain.protocols import (
    AudioArtifact,
    CancelledCallback,
    ProgressCallback,
    TrackCandidate,
)
from chillify.infrastructure.providers.mp3 import single_valid_mp3
from chillify.infrastructure.providers.radio_javan_wire import (
    PROVIDER_NAME,
    candidates_from_browse,
    candidates_from_search,
    media_url_from_detail,
)
from chillify.infrastructure.security.outbound import OutboundHttp

_BASE_URL: Final = "https://rj-deskcloud.com/api2"
_USER_AGENT: Final = "Chillify/1.0 (Radio Javan integration)"
_JSON_MAX_BYTES: Final = 4 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class RadioJavanDiscoveryProvider:
    """Anonymous Radio Javan search over the shared outbound policy."""

    name: str = PROVIDER_NAME

    def search(self, query: str, limit: int, proxy: str | None) -> tuple[TrackCandidate, ...]:
        response = OutboundHttp(proxy=proxy).request(
            "GET",
            f"{_BASE_URL}/search",
            params={"query": query},
            headers={"Accept": "application/json", "User-Agent": _USER_AGENT},
        )
        payload = _json_response(response)
        return candidates_from_search(payload)[:limit]

    def browse(self, section: str, proxy: str | None) -> tuple[TrackCandidate, ...]:
        """Return the deliberately unpaginated Featured or Trending MP3 page."""
        if section not in {"featured", "trending"}:
            raise ProviderResponseError(
                "Radio Javan could not complete that request.",
                context={"provider": self.name},
            )
        response = OutboundHttp(proxy=proxy).request(
            "GET",
            f"{_BASE_URL}/mp3s",
            params={"url": "mp3s", "type": section, "page": "1"},
            headers={"Accept": "application/json", "User-Agent": _USER_AGENT},
        )
        return candidates_from_browse(_json_response(response))


@dataclass(frozen=True, slots=True)
class RadioJavanAcquisitionProvider:
    """Resolve a current Radio Javan detail record, then write its MP3."""

    name: str = PROVIDER_NAME

    def acquire(
        self,
        candidate: TrackCandidate,
        workspace: str,
        proxy: str | None,
        progress: ProgressCallback,
        cancelled: CancelledCallback,
    ) -> AudioArtifact:
        source_id = candidate.source_id or candidate.acquisition_locator
        detail = OutboundHttp(proxy=proxy).request(
            "GET",
            f"{_BASE_URL}/mp3",
            params={"id": source_id},
            headers={"Accept": "application/json", "User-Agent": _USER_AGENT},
        )
        media_url = media_url_from_detail(_json_response(detail), source_id)
        target = Path(workspace) / "radio-javan.mp3"
        if cancelled():
            raise AcquisitionCancelledError("That download was cancelled.")
        OutboundHttp(proxy=proxy, follow_redirects=True).stream_to_file(
            media_url,
            target,
            headers={"Accept": "audio/mpeg", "User-Agent": _USER_AGENT},
            cancelled=cancelled,
            progress=lambda percent: progress(JobPhase.DOWNLOADING, percent),
        )
        try:
            audio_path, duration_ms = single_valid_mp3(Path(workspace), provider=self.name)
        except AcquisitionFailedError:
            target.unlink(missing_ok=True)
            raise
        return AudioArtifact(
            location=str(audio_path),
            duration_ms=duration_ms,
            byte_size=audio_path.stat().st_size,
        )


def _json_response(response: httpx.Response) -> object:
    if response.status_code >= 400:
        raise ProviderResponseError(
            "Radio Javan could not complete that request.", context={"provider": PROVIDER_NAME}
        )
    if len(response.content) > _JSON_MAX_BYTES:
        raise ProviderResponseError(
            "Radio Javan returned a response Chillify could not read.",
            context={"provider": PROVIDER_NAME},
        )
    try:
        return json.loads(response.content)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ProviderResponseError(
            "Radio Javan returned a response Chillify could not read.",
            context={"provider": PROVIDER_NAME},
        ) from exc
