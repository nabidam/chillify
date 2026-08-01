"""Radio Javan discovery and direct native-audio acquisition."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import httpx

from chillify.domain.errors import AcquisitionFailedError, ProviderResponseError
from chillify.domain.protocols import (
    AudioArtifact,
    CancelledCallback,
    ProgressCallback,
    TrackCandidate,
)
from chillify.infrastructure.providers.radio_javan_wire import (
    PROVIDER_NAME,
    candidates_from_browse,
    candidates_from_search,
    media_url_from_detail,
)
from chillify.infrastructure.security.outbound import OutboundHttp

_BASE_URL: Final = "https://rj-deskcloud.com/api2"
_USER_AGENT: Final = "Chillify/1.0 (Radio Javan integration)"


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
        if cancelled():
            raise AcquisitionFailedError(
                "That download was cancelled.", context={"provider": self.name}
            )
        media = OutboundHttp(proxy=proxy, follow_redirects=True).request(
            "GET",
            media_url,
            headers={"Accept": "audio/mpeg", "User-Agent": _USER_AGENT},
        )
        body = media.content
        if not body:
            raise AcquisitionFailedError(
                "Radio Javan returned an empty audio file.", context={"provider": self.name}
            )
        target = Path(workspace) / "radio-javan.mp3"
        target.write_bytes(body)
        progress(100.0)
        return AudioArtifact(
            location=str(target), duration_ms=candidate.duration_ms, byte_size=len(body)
        )


def _json_response(response: httpx.Response) -> object:
    if response.status_code >= 400:
        raise ProviderResponseError(
            "Radio Javan could not complete that request.", context={"provider": PROVIDER_NAME}
        )
    try:
        return json.loads(response.content)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ProviderResponseError(
            "Radio Javan returned a response Chillify could not read.",
            context={"provider": PROVIDER_NAME},
        ) from exc
