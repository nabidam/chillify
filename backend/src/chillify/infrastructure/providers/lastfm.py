"""The production Last.fm enrichment adapter.

Last.fm only ever fills gaps: it is asked for the fields a candidate is missing
and never overwrites one that is populated. Its failure — no key, an API error,
an absent track, a timeout — is a non-fatal warning, so `enrich` catches every
outcome and returns whatever it could gather, down to an empty patch. A blocked
or misconfigured Last.fm never fails a download.

The API key is a stored secret. It is registered for redaction as soon as this
adapter is built, so it cannot appear in a log line, and it never leaves this
module.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Final

from chillify.domain.protocols import MetadataPatch, TrackCandidate
from chillify.infrastructure.logging.setup import redactor
from chillify.infrastructure.security.outbound import OutboundHttp

logger = logging.getLogger(__name__)

_INFO_URL: Final = "https://ws.audioscrobbler.com/2.0/"
_PROVIDER_NAME: Final = "lastfm"


@dataclass(frozen=True, slots=True)
class LastfmEnricher:
    """Optional metadata gap fill through the shared outbound policy."""

    api_key: str | None = None
    name: str = _PROVIDER_NAME

    def __post_init__(self) -> None:
        if self.api_key:
            redactor().register(self.api_key)

    def enrich(
        self,
        candidate: TrackCandidate,
        missing_fields: Sequence[str],
        proxy: str | None,
    ) -> MetadataPatch:
        """Fill only the requested missing fields, or return an empty patch.

        Every failure path returns rather than raises: an unconfigured or
        unreachable Last.fm must not turn an otherwise complete acquisition into
        a failed job.
        """
        if not self.api_key or not missing_fields:
            return MetadataPatch()
        try:
            track = self._fetch(candidate, proxy)
        except Exception as exc:
            logger.info(
                "last.fm enrichment skipped",
                extra={"provider": self.name, "reason": type(exc).__name__},
            )
            return MetadataPatch()
        if track is None:
            return MetadataPatch()
        return _patch_from(track, missing_fields)

    def _fetch(self, candidate: TrackCandidate, proxy: str | None) -> dict[str, Any] | None:
        policy = OutboundHttp(proxy=proxy)
        response = policy.request(
            "GET",
            _INFO_URL,
            params={
                "method": "track.getInfo",
                "api_key": self.api_key or "",
                "artist": candidate.artist,
                "track": candidate.title,
                "autocorrect": "1",
                "format": "json",
            },
        )
        if response.status_code >= 400:
            return None
        payload = json.loads(response.content)
        if not isinstance(payload, dict) or "error" in payload:
            return None
        track = payload.get("track")
        return track if isinstance(track, dict) else None


def _patch_from(track: dict[str, Any], missing_fields: Sequence[str]) -> MetadataPatch:
    requested = set(missing_fields)
    return MetadataPatch(
        title=_text(track.get("name")) if "title" in requested else None,
        artist=_text(_nested(track, "artist", "name")) if "artist" in requested else None,
        album=_text(_nested(track, "album", "title")) if "album" in requested else None,
        duration_ms=_duration_ms(track.get("duration")) if "duration_ms" in requested else None,
        artwork_url=_largest_image(track.get("album")) if "artwork_url" in requested else None,
    )


def _nested(track: dict[str, Any], parent: str, child: str) -> object:
    container = track.get(parent)
    return container.get(child) if isinstance(container, dict) else None


def _largest_image(album: object) -> str | None:
    if not isinstance(album, dict):
        return None
    images = album.get("image")
    if not isinstance(images, list):
        return None
    # Last.fm lists images small→extralarge; the last non-empty secure URL wins.
    chosen: str | None = None
    for entry in images:
        if isinstance(entry, dict):
            url = _text(entry.get("#text"))
            if url is not None and url.startswith("https://"):
                chosen = url
    return chosen


def _duration_ms(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int | str):
        return None
    try:
        milliseconds = int(value)
    except TypeError, ValueError:
        return None
    return milliseconds if milliseconds > 0 else None


def _text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None
