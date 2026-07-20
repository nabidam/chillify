"""Translation of the Deezer search wire format into `TrackCandidate`.

This is the only place a Deezer payload is understood. Both the fixture adapter
and the production adapter parse through these functions, so a response shape
that one accepts cannot be a shape the other rejects.

Only the documented fields are read. Anything else in the payload is ignored
rather than passed along, which is what keeps a provider response type from
escaping the adapter boundary.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Final

from chillify.domain.errors import ProviderResponseError, ValidationFailedError
from chillify.domain.normalization import normalize_isrc
from chillify.domain.protocols import TrackCandidate

PROVIDER_NAME: Final = "deezer"

# Cover sizes in the order the contract prefers them.
_COVER_FIELDS: Final = ("cover_xl", "cover_big", "cover_medium")


def candidates_from_search(payload: object) -> tuple[TrackCandidate, ...]:
    """Parse one `GET /search` body into candidates.

    An `error` object, a missing `data` array, or a body that is not an object
    is a provider-contract failure. Individual malformed items are dropped: one
    unusable row in a result list is not a reason to show the person nothing.
    """
    if not isinstance(payload, dict):
        raise ProviderResponseError(
            "Deezer returned a response Chillify could not read.",
            context={"provider": PROVIDER_NAME},
        )
    if "error" in payload:
        raise ProviderResponseError(
            "Deezer reported an error for that search.",
            context={"provider": PROVIDER_NAME},
        )
    data = payload.get("data")
    if not isinstance(data, list):
        raise ProviderResponseError(
            "Deezer returned a response without any results field.",
            context={"provider": PROVIDER_NAME},
        )

    candidates = []
    for item in data:
        candidate = _candidate_or_none(item)
        if candidate is not None:
            candidates.append(candidate)
    return tuple(candidates)


def _candidate_or_none(item: object) -> TrackCandidate | None:
    if not isinstance(item, dict):
        return None

    source_id = _identifier(item.get("id"))
    title = _text(item.get("title"))
    artist = _text(_nested(item, "artist", "name"))
    if source_id is None or title is None or artist is None:
        return None

    album = _text(_nested(item, "album", "title"))
    duration_seconds = _positive_int(item.get("duration"))

    return TrackCandidate(
        provider=PROVIDER_NAME,
        source_id=source_id,
        source_url=f"https://www.deezer.com/track/{source_id}",
        title=title,
        artist=artist,
        album=album,
        # Deezer's search payload carries no release year, disc, or track
        # number. They stay absent rather than guessed; the person can supply
        # them in the track editor.
        release_year=None,
        disc_number=None,
        track_number=None,
        duration_ms=None if duration_seconds is None else duration_seconds * 1000,
        isrc=_isrc_or_none(item.get("isrc")),
        artwork_url=_artwork_url(item.get("album")),
        # Deezer never supplies audio. The acquisition locator is the yt-dlp
        # search target the worker resolves instead.
        acquisition_locator=f"ytsearch1:{artist} {title}",
        raw_fingerprint=fingerprint(item),
    )


def fingerprint(item: dict[str, Any]) -> str:
    """A stable digest of the accepted fields, for provenance without the body."""
    accepted = {
        "id": item.get("id"),
        "title": item.get("title"),
        "duration": item.get("duration"),
        "isrc": item.get("isrc"),
        "artist_id": _nested(item, "artist", "id"),
        "album_id": _nested(item, "album", "id"),
    }
    encoded = json.dumps(accepted, separators=(",", ":"), sort_keys=True, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _nested(item: dict[str, Any], parent: str, child: str) -> object:
    container = item.get(parent)
    return container.get(child) if isinstance(container, dict) else None


def _artwork_url(album: object) -> str | None:
    if not isinstance(album, dict):
        return None
    for field in _COVER_FIELDS:
        url = _text(album.get(field))
        if url is not None and url.startswith("https://"):
            return url
    return None


def _identifier(value: object) -> str | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return str(value)
    text = _text(value)
    return text if text is not None and text.isdigit() else None


def _text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _positive_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        return None
    try:
        number = int(value)
    except TypeError, ValueError:
        return None
    return number if number > 0 else None


def _isrc_or_none(value: object) -> str | None:
    """A malformed ISRC is dropped rather than failing the whole result.

    The code is provider-supplied metadata, not something the person typed, so
    a bad one must not hide an otherwise usable track.
    """
    text = _text(value)
    if text is None:
        return None
    try:
        return normalize_isrc(text)
    except ValidationFailedError:
        return None
