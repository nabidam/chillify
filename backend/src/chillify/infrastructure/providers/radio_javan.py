"""Radio Javan discovery and direct native-audio acquisition."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
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
from chillify.infrastructure.providers.mp3 import (
    convert_to_mp3,
    media_needs_conversion,
    mp3_duration_ms,
)
from chillify.infrastructure.providers.radio_javan_wire import (
    PROVIDER_NAME,
    candidates_from_browse,
    candidates_from_search,
    media_url_from_detail,
)
from chillify.infrastructure.security.outbound import OutboundHttp, _OutboundBodyTooLargeError

_BASE_URL: Final = "https://rj-deskcloud.com/api2"
_USER_AGENT: Final = "Chillify/1.0 (Radio Javan integration)"
_JSON_MAX_BYTES: Final = 4 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class RadioJavanDiscoveryProvider:
    """Anonymous Radio Javan search over the shared outbound policy."""

    name: str = PROVIDER_NAME

    def search(self, query: str, limit: int, proxy: str | None) -> tuple[TrackCandidate, ...]:
        payload = _request_json(
            f"{_BASE_URL}/search",
            params={"query": query},
            proxy=proxy,
        )
        return candidates_from_search(payload)[:limit]

    def browse(self, section: str, proxy: str | None) -> tuple[TrackCandidate, ...]:
        """Return the deliberately unpaginated Featured or Trending MP3 page."""
        if section not in {"featured", "trending"}:
            raise ProviderResponseError(
                "Radio Javan could not complete that request.",
                context={"provider": self.name},
            )
        return candidates_from_browse(
            _request_json(
                f"{_BASE_URL}/mp3s",
                params={"url": "mp3s", "type": section, "page": "1"},
                proxy=proxy,
            )
        )


@dataclass(frozen=True, slots=True)
class RadioJavanAcquisitionProvider:
    """Resolve a current Radio Javan detail record, then write its MP3."""

    name: str = PROVIDER_NAME
    converter: Callable[..., tuple[Path, int]] = field(default=convert_to_mp3, repr=False)

    def acquire(
        self,
        candidate: TrackCandidate,
        workspace: str,
        proxy: str | None,
        progress: ProgressCallback,
        cancelled: CancelledCallback,
    ) -> AudioArtifact:
        source_id = candidate.source_id or candidate.acquisition_locator
        media_url = media_url_from_detail(
            _request_json(f"{_BASE_URL}/mp3", params={"id": source_id}, proxy=proxy), source_id
        )
        downloaded = Path(workspace) / "radio-javan.download"
        target = Path(workspace) / "radio-javan.mp3"
        if cancelled():
            raise AcquisitionCancelledError("That download was cancelled.")
        OutboundHttp(proxy=proxy, follow_redirects=True).stream_to_file(
            media_url,
            downloaded,
            headers={"Accept": "audio/mpeg", "User-Agent": _USER_AGENT},
            cancelled=cancelled,
            progress=lambda percent: progress(JobPhase.DOWNLOADING, percent),
        )
        try:
            duration_ms = mp3_duration_ms(downloaded, provider=self.name)
        except AcquisitionFailedError:
            if not media_needs_conversion(downloaded):
                downloaded.unlink(missing_ok=True)
                raise
            progress(JobPhase.CONVERTING, None)
            try:
                audio_path, duration_ms = self.converter(downloaded, target, provider=self.name)
            except AcquisitionFailedError:
                downloaded.unlink(missing_ok=True)
                target.unlink(missing_ok=True)
                raise
            downloaded.unlink(missing_ok=True)
        else:
            downloaded.replace(target)
            audio_path = target
        return AudioArtifact(
            location=str(audio_path),
            duration_ms=duration_ms,
            byte_size=audio_path.stat().st_size,
        )


def _json_response(status_code: int | httpx.Response, body: bytes | None = None) -> object:
    """Decode a bounded response, retaining a response overload for wire tests."""
    if isinstance(status_code, httpx.Response):
        response = status_code
        if _content_length(response.headers.get("content-length")) > _JSON_MAX_BYTES:
            raise ProviderResponseError(
                "Radio Javan returned a response Chillify could not read.",
                context={"provider": PROVIDER_NAME},
            )
        body = response.content
        status = response.status_code
    else:
        status = status_code
    if status >= 400:
        raise ProviderResponseError(
            "Radio Javan could not complete that request.", context={"provider": PROVIDER_NAME}
        )
    if body is None or len(body) > _JSON_MAX_BYTES:
        raise ProviderResponseError(
            "Radio Javan returned a response Chillify could not read.",
            context={"provider": PROVIDER_NAME},
        )
    try:
        return json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ProviderResponseError(
            "Radio Javan returned a response Chillify could not read.",
            context={"provider": PROVIDER_NAME},
        ) from exc


def _content_length(value: str | None) -> int:
    try:
        return int(value) if value is not None else 0
    except ValueError:
        return 0


def _request_json(url: str, *, params: dict[str, str], proxy: str | None) -> object:
    try:
        status, body = OutboundHttp(proxy=proxy).request_limited_bytes(
            "GET",
            url,
            params=params,
            headers={"Accept": "application/json", "User-Agent": _USER_AGENT},
            max_bytes=_JSON_MAX_BYTES,
        )
    except _OutboundBodyTooLargeError as exc:
        raise ProviderResponseError(
            "Radio Javan returned a response Chillify could not read.",
            context={"provider": PROVIDER_NAME},
        ) from exc
    return _json_response(status, body)
