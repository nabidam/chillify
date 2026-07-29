"""Spotify link references through the public oEmbed endpoint.

This adapter deliberately resolves only the small, public reference Spotify
offers without credentials.  oEmbed identifies a submitted track well enough
to start a later metadata-match journey, but it does *not* provide artist,
album, duration, ISRC, or acquisition rights.  Consequently this module does
not implement ``LinkInspector`` and never creates a ``TrackCandidate``.

No page, iframe, or private Spotify response is scraped here.  The one network
call uses the shared outbound policy so saved proxy settings remain fail-closed.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Final
from urllib.parse import urlsplit

import httpx

from chillify.domain.errors import (
    ProviderResponseError,
    UnsupportedEntityError,
    ValidationFailedError,
)
from chillify.domain.normalization import collapse_whitespace
from chillify.infrastructure.security.outbound import OutboundHttp

logger = logging.getLogger(__name__)

PROVIDER_NAME: Final = "spotify_oembed"
OEMBED_URL: Final = "https://open.spotify.com/oembed"
MAX_RESPONSE_BYTES: Final = 64 * 1024
MAX_TITLE_CHARS: Final = 500
MAX_THUMBNAIL_URL_CHARS: Final = 2_048

_HOSTS: Final = frozenset({"open.spotify.com", "play.spotify.com"})
_TRACK_ID: Final = re.compile(r"^[A-Za-z0-9]{22}$")
_LOCALE: Final = re.compile(r"^intl-[A-Za-z]{2}(?:-[A-Za-z]{2})?$")
_COLLECTION_ENTITIES: Final = frozenset({"album", "playlist"})


@dataclass(frozen=True, slots=True)
class TrackReference:
    """The deliberately limited public reference for one Spotify track."""

    spotify_id: str
    canonical_url: str
    title: str
    thumbnail_url: str | None


def canonicalize_track_url(raw_url: str) -> tuple[str, str]:
    """Validate one Spotify track URL and return its ID plus stable URL.

    Query parameters and fragments are deliberately discarded: neither changes
    the Spotify track identity and forwarding them to oEmbed would preserve
    needless tracking data.  Only public web track URLs are accepted; Spotify
    URIs and collection URLs are not another spelling of a single track.
    """
    value = raw_url.strip()
    if not value or any(character.isspace() for character in value):
        raise _invalid_url()
    try:
        parts = urlsplit(value)
        # Accessing ``port`` validates a malformed numeric port too.
        _ = parts.port
    except ValueError as exc:
        raise _invalid_url() from exc

    if (
        parts.scheme.lower() != "https"
        or (parts.hostname or "").lower() not in _HOSTS
        or parts.username is not None
        or parts.password is not None
    ):
        raise _invalid_url()

    segments = [segment for segment in parts.path.split("/") if segment]
    if segments and _LOCALE.fullmatch(segments[0]):
        segments = segments[1:]

    if len(segments) == 2 and segments[0] == "track" and _TRACK_ID.fullmatch(segments[1]):
        track_id = segments[1]
        return track_id, f"https://open.spotify.com/track/{track_id}"

    if segments and segments[0] in _COLLECTION_ENTITIES:
        raise UnsupportedEntityError(
            "Chillify can only use individual Spotify track links.",
            field="url",
            context={"provider": PROVIDER_NAME, "reason": "collection"},
        )
    raise _invalid_url()


@dataclass(frozen=True, slots=True)
class SpotifyOEmbedReferenceResolver:
    """Resolve one public Spotify track URL without a Spotify account."""

    name: str = PROVIDER_NAME

    def resolve(self, url: str, proxy: str | None) -> TrackReference:
        """Return a strictly parsed oEmbed track reference.

        Provider failures intentionally contain no response body.  Proxy errors
        are already typed by ``OutboundHttp`` and are allowed to preserve their
        more actionable failure code.
        """
        spotify_id, canonical_url = canonicalize_track_url(url)
        try:
            response = OutboundHttp(proxy=proxy).request(
                "GET", OEMBED_URL, params={"url": canonical_url}
            )
        except httpx.TimeoutException as exc:
            raise _provider_failure("Spotify did not respond in time.", reason="timeout") from exc
        except httpx.HTTPError as exc:
            raise _provider_failure(
                "Spotify could not resolve that track.", reason="transport"
            ) from exc

        if response.status_code == 404:
            raise _provider_failure(
                "Spotify could not find that track.", reason="not_found", fallback=False
            )
        if response.status_code >= 400:
            raise _provider_failure("Spotify could not resolve that track.", reason="http_error")

        payload = _bounded_json(response)
        title, thumbnail_url = _reference_fields(payload)
        logger.info("spotify oembed reference resolved", extra={"provider": self.name})
        return TrackReference(
            spotify_id=spotify_id,
            canonical_url=canonical_url,
            title=title,
            thumbnail_url=thumbnail_url,
        )


def _invalid_url() -> ValidationFailedError:
    return ValidationFailedError(
        "Enter an individual Spotify track link from open.spotify.com or play.spotify.com.",
        field="url",
    )


def _provider_failure(message: str, *, reason: str, fallback: bool = True) -> ProviderResponseError:
    return ProviderResponseError(
        message,
        context={"provider": PROVIDER_NAME, "reason": reason, "fallback": fallback},
    )


def _bounded_json(response: httpx.Response) -> object:
    content_length = response.headers.get("Content-Length")
    if content_length is not None:
        try:
            if int(content_length) > MAX_RESPONSE_BYTES:
                raise _provider_failure(
                    "Spotify returned a response that was too large.", reason="too_large"
                )
        except ValueError:
            pass
    try:
        content = response.content
    except httpx.HTTPError as exc:
        raise _provider_failure(
            "Spotify returned an unreadable response.", reason="unreadable"
        ) from exc
    if len(content) > MAX_RESPONSE_BYTES:
        raise _provider_failure(
            "Spotify returned a response that was too large.", reason="too_large"
        )
    try:
        return json.loads(content)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise _provider_failure(
            "Spotify returned an unreadable response.", reason="invalid_response"
        ) from exc


def _reference_fields(payload: object) -> tuple[str, str | None]:
    if not isinstance(payload, dict):
        raise _provider_failure(
            "Spotify returned an invalid track reference.", reason="invalid_response"
        )
    title = _text(payload.get("title"), maximum=MAX_TITLE_CHARS)
    thumbnail_url = _https_url(payload.get("thumbnail_url"), maximum=MAX_THUMBNAIL_URL_CHARS)
    if title is None:
        raise _provider_failure(
            "Spotify returned an invalid track reference.", reason="invalid_response"
        )
    return title, thumbnail_url


def _text(value: object, *, maximum: int) -> str | None:
    if not isinstance(value, str):
        return None
    text = collapse_whitespace(value)
    return text if text and len(text) <= maximum else None


def _https_url(value: object, *, maximum: int) -> str | None:
    if not isinstance(value, str) or not value or len(value) > maximum:
        return None
    try:
        parts = urlsplit(value)
        _ = parts.port
    except ValueError:
        return None
    if (
        parts.scheme.lower() != "https"
        or not parts.hostname
        or parts.username is not None
        or parts.password is not None
        or any(character.isspace() for character in value)
    ):
        return None
    return value
