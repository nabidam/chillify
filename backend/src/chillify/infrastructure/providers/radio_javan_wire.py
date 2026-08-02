"""Normalize the narrow Radio Javan wire contract into Chillify candidates."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Final
from urllib.parse import urlsplit

from chillify.domain.errors import ProviderResponseError
from chillify.domain.protocols import TrackCandidate

PROVIDER_NAME: Final = "radiojavan"
_SOURCE_HOSTS: Final = ("rj.app", "radiojavan.com", "play.radiojavan.com")
_MEDIA_FIELDS: Final = ("hq_link", "link", "lq_link")


def candidates_from_search(payload: object) -> tuple[TrackCandidate, ...]:
    """Read only the MP3 group from one Radio Javan search response."""
    if not isinstance(payload, dict):
        raise _response_error()
    rows = payload.get("mp3s", [])
    if not isinstance(rows, list):
        raise _response_error()
    return tuple(candidate for row in rows if (candidate := _candidate_or_none(row)) is not None)


def candidates_from_browse(payload: object) -> tuple[TrackCandidate, ...]:
    """Read one Radio Javan Featured or Trending MP3 browse response."""
    if not isinstance(payload, list):
        raise _response_error()
    return tuple(candidate for row in payload if (candidate := _candidate_or_none(row)) is not None)


def candidate_from_row(row: object) -> TrackCandidate:
    candidate = _candidate_or_none(row)
    if candidate is None:
        raise _response_error()
    return candidate


def media_url_from_detail(payload: object, source_id: str) -> str:
    """Validate a detail response and choose the first usable quality URL."""
    if not isinstance(payload, dict) or _identifier(payload.get("id")) != source_id:
        raise _response_error()
    for field in _MEDIA_FIELDS:
        value = payload.get(field)
        if isinstance(value, str) and value.strip().startswith("https://"):
            return value.strip()
    raise _response_error()


def _candidate_or_none(row: object) -> TrackCandidate | None:
    if not isinstance(row, dict):
        return None
    source_id = _identifier(row.get("id"))
    artist = _text(row.get("artist"))
    title = _text(row.get("title")) or _text(row.get("name")) or _text(row.get("song"))
    if source_id is None or artist is None or title is None:
        return None

    title = _clean_title(title, artist)
    album = _album(row.get("album"))
    duration_seconds = _positive_int(row.get("duration"))
    return TrackCandidate(
        provider=PROVIDER_NAME,
        source_id=source_id,
        source_url=_source_url(row.get("share_link"), source_id),
        title=title,
        artist=artist,
        album=album,
        release_year=_year(row.get("date") or row.get("created_at")),
        disc_number=None,
        track_number=None,
        duration_ms=None if duration_seconds is None else duration_seconds * 1000,
        isrc=None,
        artwork_url=_artwork_url(
            row.get("photo"), row.get("thumbnail"), row.get("photo_thumbnail")
        ),
        acquisition_locator=source_id,
        raw_fingerprint=fingerprint(row),
    )


def fingerprint(row: dict[str, Any]) -> str:
    accepted = {
        field: row.get(field)
        for field in (
            "id",
            "artist",
            "title",
            "name",
            "song",
            "album",
            "date",
            "created_at",
            "duration",
            "photo",
            "thumbnail",
            "photo_thumbnail",
            "permlink",
            "share_link",
        )
    }
    encoded = json.dumps(accepted, separators=(",", ":"), sort_keys=True, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _source_url(value: object, source_id: str) -> str:
    if isinstance(value, str):
        candidate = value.strip()
        parts = urlsplit(candidate)
        host = (parts.hostname or "").lower().rstrip(".")
        if parts.scheme == "https" and any(
            host == allowed or host.endswith(f".{allowed}") for allowed in _SOURCE_HOSTS
        ):
            return candidate
    return f"https://play.radiojavan.com/song/{source_id}"


def _artwork_url(*values: object) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip().startswith("https://"):
            return value.strip()
    return None


def _album(value: object) -> str | None:
    if isinstance(value, str):
        return _text(value)
    if isinstance(value, dict):
        return _text(value.get("title")) or _text(value.get("name"))
    return None


def _clean_title(title: str, artist: str) -> str:
    prefix = f"{artist} - "
    if title.casefold().startswith(prefix.casefold()):
        title = title[len(prefix) :].strip()
    if len(title) >= 2 and title[0] == title[-1] and title[0] in {"'", '"'}:
        title = title[1:-1].strip()
    return title


def _identifier(value: object) -> str | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value > 0:
        return str(value)
    if isinstance(value, str) and value.strip().isdigit() and int(value.strip()) > 0:
        return value.strip()
    return None


def _positive_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float | str):
        try:
            parsed = int(value)
        except TypeError, ValueError:
            return None
        return parsed if parsed > 0 else None
    return None


def _year(value: object) -> int | None:
    if isinstance(value, int) and 1000 <= value <= 9999:
        return value
    if isinstance(value, str) and value[:4].isdigit():
        parsed = int(value[:4])
        return parsed if 1000 <= parsed <= 9999 else None
    return None


def _text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _response_error() -> ProviderResponseError:
    return ProviderResponseError(
        "Radio Javan returned a response Chillify could not read.",
        context={"provider": PROVIDER_NAME},
    )
