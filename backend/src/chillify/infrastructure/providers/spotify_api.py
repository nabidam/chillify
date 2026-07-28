"""Spotify Web API link inspection.

This module is the only adapter that understands Spotify's Web API response
shape.  It uses Client Credentials, keeps the short-lived access token in the
adapter process, and returns only the normalized domain candidate.  The
fixture adapter deliberately shares the same parser so the gate cannot accept
a payload the production adapter would reject.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from threading import Lock
from typing import Any, Final

import httpx

from chillify.domain.errors import (
    ProviderResponseError,
    UnsupportedEntityError,
    ValidationFailedError,
)
from chillify.domain.normalization import collapse_whitespace, normalize_isrc
from chillify.domain.protocols import TrackCandidate
from chillify.infrastructure.providers.spotdl import LinkKind, recognize
from chillify.infrastructure.security.outbound import OutboundHttp

logger = logging.getLogger(__name__)

PROVIDER_NAME: Final = "spotify_api"
CANDIDATE_PROVIDER_NAME: Final = "spotify"
TOKEN_URL: Final = "https://accounts.spotify.com/api/token"
TRACK_URL: Final = "https://api.spotify.com/v1/tracks/{}"
MAX_RESPONSE_BYTES: Final = 1 * 1024 * 1024
TOKEN_REFRESH_MARGIN_SECONDS: Final = 60
SUCCESS_FIXTURE: Final = "spotify_api/track_success.json"

CredentialsProvider = Callable[[], tuple[str, str] | None]


@dataclass(frozen=True, slots=True)
class _Token:
    value: str
    expires_at: float


def candidate_from_api_payload(
    payload: object, *, track_id: str, canonical_url: str
) -> TrackCandidate:
    """Normalize one Spotify track response into the domain boundary type."""
    if not isinstance(payload, dict):
        raise _failed_lookup("Spotify returned a response Chillify could not read.")

    title = _text(payload.get("name"))
    artist = _first_artist(payload.get("artists"))
    if title is None or artist is None:
        raise _failed_lookup("Spotify returned a track without usable metadata.")

    album = payload.get("album")
    album_object = album if isinstance(album, dict) else {}
    return TrackCandidate(
        provider=CANDIDATE_PROVIDER_NAME,
        source_id=track_id,
        source_url=canonical_url,
        title=title,
        artist=artist,
        album=_text(album_object.get("name")),
        release_year=_release_year(album_object.get("release_date")),
        disc_number=_positive_int(payload.get("disc_number")),
        track_number=_positive_int(payload.get("track_number")),
        duration_ms=_positive_int(payload.get("duration_ms")),
        isrc=_isrc_or_none(
            payload.get("external_ids", {}).get("isrc")
            if isinstance(payload.get("external_ids"), dict)
            else None
        ),
        artwork_url=_largest_artwork(album_object.get("images")),
        acquisition_locator=canonical_url,
        raw_fingerprint=_fingerprint(payload, track_id),
    )


@dataclass(slots=True)
class SpotifyApiInspector:
    """Production Spotify inspector using the documented Web API."""

    credentials_provider: CredentialsProvider | None = None
    credentials: tuple[str, str] | None = None
    name: str = PROVIDER_NAME
    _token: _Token | None = field(default=None, init=False, repr=False)
    _token_lock: Lock = field(default_factory=Lock, init=False, repr=False)

    def supports(self, url: str) -> bool:
        return recognize(url) is not None

    def inspect(self, url: str, proxy: str | None) -> TrackCandidate:
        link = recognize(url)
        if link is None:
            raise UnsupportedEntityError(
                "Chillify can only inspect Spotify track links.",
                field="url",
                context={"provider": CANDIDATE_PROVIDER_NAME},
            )
        if link.kind is LinkKind.BULK or link.canonical_url is None or link.track_id is None:
            raise UnsupportedEntityError(
                "That is an album, playlist, or artist. Add one track at a time.",
                field="url",
                context={"provider": CANDIDATE_PROVIDER_NAME, "reason": "bulk"},
            )

        credentials = self._credentials()
        if credentials is None:
            raise _failed_lookup(
                "Spotify credentials are not configured.", reason="credentials_missing"
            )

        token = self._get_token(credentials, proxy)
        for attempt in range(2):
            response = self._request_track(token=token, track_id=link.track_id, proxy=proxy)
            if response.status_code != 401 or attempt == 1:
                break
            self._invalidate_token(token)
            token = self._get_token(credentials, proxy, force_refresh=True)

        if response.status_code == 404:
            raise _failed_lookup(
                "Spotify could not find that track.", reason="not_found", fallback=False
            )
        if response.status_code == 429:
            _honor_retry_after(response.headers.get("Retry-After"))
            raise _failed_lookup("Spotify rate limited this lookup.", reason="rate_limited")
        if response.status_code in (400, 401):
            raise _failed_lookup("Spotify credentials were rejected.", reason="credentials")
        if response.status_code >= 400:
            raise _failed_lookup("Spotify could not inspect that track.", reason="http_error")

        payload = _bounded_json(response)
        candidate = candidate_from_api_payload(
            payload, track_id=link.track_id, canonical_url=link.canonical_url
        )
        logger.info("spotify api inspection complete", extra={"provider": self.name})
        return candidate

    def _credentials(self) -> tuple[str, str] | None:
        if self.credentials_provider is not None:
            return self.credentials_provider()
        return self.credentials

    def _get_token(
        self,
        credentials: tuple[str, str],
        proxy: str | None,
        *,
        force_refresh: bool = False,
    ) -> str:
        now = time.monotonic()
        with self._token_lock:
            if not force_refresh and self._token is not None and self._token.expires_at > now:
                return self._token.value

            client_id, client_secret = credentials
            encoded = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode("ascii")
            try:
                with OutboundHttp(proxy=proxy).open() as client:
                    response = client.post(
                        TOKEN_URL,
                        data={"grant_type": "client_credentials"},
                        headers={"Authorization": f"Basic {encoded}"},
                    )
            except httpx.HTTPError as exc:
                raise _failed_lookup("Spotify token request failed.", reason="transport") from exc

            if response.status_code in (400, 401):
                raise _failed_lookup("Spotify credentials were rejected.", reason="credentials")
            if response.status_code >= 400:
                raise _failed_lookup("Spotify token request failed.", reason="http_error")
            payload = _bounded_json(response)
            if not isinstance(payload, dict):
                raise _failed_lookup("Spotify returned an invalid token response.")
            token = _text(payload.get("access_token"))
            expires_in = _positive_int(payload.get("expires_in"))
            if token is None or expires_in is None:
                raise _failed_lookup("Spotify returned an invalid token response.")
            self._token = _Token(
                value=token,
                expires_at=time.monotonic() + max(0, expires_in - TOKEN_REFRESH_MARGIN_SECONDS),
            )
            return token

    def _invalidate_token(self, token: str) -> None:
        with self._token_lock:
            if self._token is not None and self._token.value == token:
                self._token = None

    @staticmethod
    def _request_track(*, token: str, track_id: str, proxy: str | None) -> httpx.Response:
        try:
            with OutboundHttp(proxy=proxy).open() as client:
                return client.get(
                    TRACK_URL.format(track_id),
                    headers={"Authorization": f"Bearer {token}"},
                )
        except httpx.HTTPError as exc:
            raise _failed_lookup("Spotify track request failed.", reason="transport") from exc


@dataclass(frozen=True, slots=True)
class FixtureSpotifyApiInspector:
    """Recorded Spotify success adapter used by gate and contract tests."""

    fixture_root: Path
    name: str = PROVIDER_NAME

    def supports(self, url: str) -> bool:
        return recognize(url) is not None

    def inspect(self, url: str, proxy: str | None) -> TrackCandidate:  # noqa: ARG002
        link = recognize(url)
        if link is None or link.kind is LinkKind.BULK or link.canonical_url is None:
            raise UnsupportedEntityError(
                "That is an album, playlist, or artist. Add one track at a time.",
                field="url",
                context={"provider": CANDIDATE_PROVIDER_NAME, "reason": "bulk"},
            )
        payload = _read_fixture(self.fixture_root / SUCCESS_FIXTURE)
        return candidate_from_api_payload(
            payload, track_id=link.track_id or "", canonical_url=link.canonical_url
        )


def _failed_lookup(
    message: str, *, reason: str = "invalid_response", fallback: bool = True
) -> ProviderResponseError:
    return ProviderResponseError(
        message,
        context={"provider": PROVIDER_NAME, "reason": reason, "fallback": fallback},
    )


def _bounded_json(response: httpx.Response) -> object:
    content_length = response.headers.get("Content-Length")
    if content_length is not None:
        try:
            if int(content_length) > MAX_RESPONSE_BYTES:
                raise _failed_lookup(
                    "Spotify returned a response that was too large.", reason="too_large"
                )
        except ValueError:
            pass
    try:
        content = response.content
    except httpx.HTTPError as exc:
        raise _failed_lookup("Spotify returned a response Chillify could not read.") from exc
    if len(content) > MAX_RESPONSE_BYTES:
        raise _failed_lookup("Spotify returned a response that was too large.", reason="too_large")
    try:
        return json.loads(content)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise _failed_lookup("Spotify returned a response Chillify could not read.") from exc


def _read_fixture(path: Path) -> object:
    try:
        content = path.read_bytes()
    except OSError as exc:
        raise ProviderResponseError(
            "The gate Spotify fixture is missing.", context={"provider": PROVIDER_NAME}
        ) from exc
    if len(content) > MAX_RESPONSE_BYTES:
        raise _failed_lookup("The gate Spotify fixture was too large.", reason="too_large")
    try:
        return json.loads(content)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ProviderResponseError(
            "The gate Spotify fixture could not be read.", context={"provider": PROVIDER_NAME}
        ) from exc


def _first_artist(value: object) -> str | None:
    if not isinstance(value, list):
        return None
    for entry in value:
        if isinstance(entry, dict):
            artist = _text(entry.get("name"))
            if artist is not None:
                return artist
    return None


def _largest_artwork(value: object) -> str | None:
    if not isinstance(value, list):
        return None
    candidates: list[tuple[int, int, str]] = []
    for entry in value:
        if not isinstance(entry, dict):
            continue
        url = _https(entry.get("url"))
        if url is None:
            continue
        width = _positive_int(entry.get("width")) or 0
        height = _positive_int(entry.get("height")) or 0
        candidates.append((width * height, max(width, height), url))
    if not candidates:
        return None
    return max(candidates)[2]


def _release_year(value: object) -> int | None:
    date = _text(value)
    if date is None or len(date) < 4 or not date[:4].isdigit():
        return None
    year = int(date[:4])
    return year if 1 <= year <= 9999 else None


def _isrc_or_none(value: object) -> str | None:
    text = _text(value)
    if text is None:
        return None
    try:
        return normalize_isrc(text)
    except ValidationFailedError:
        # Provider metadata is untrusted; an invalid optional ISRC is dropped.
        return None


def _fingerprint(payload: dict[str, Any], track_id: str) -> str:
    accepted = {
        "id": track_id,
        "name": payload.get("name"),
        "duration_ms": payload.get("duration_ms"),
        "isrc": (payload.get("external_ids") or {}).get("isrc")
        if isinstance(payload.get("external_ids"), dict)
        else None,
    }
    encoded = json.dumps(accepted, separators=(",", ":"), sort_keys=True, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = collapse_whitespace(value)
    return stripped or None


def _https(value: object) -> str | None:
    value = _text(value)
    return value if value is not None and value.startswith("https://") else None


def _positive_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        return None
    try:
        number = int(float(value))
    except TypeError, ValueError:
        return None
    return number if number > 0 else None


def _honor_retry_after(value: str | None) -> None:
    if value is None:
        return
    try:
        seconds = max(0, int(value.strip()))
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(value)
        except TypeError, ValueError, IndexError:
            return
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=UTC)
        seconds = max(0, round((retry_at - datetime.now(UTC)).total_seconds()))
    time.sleep(seconds)
