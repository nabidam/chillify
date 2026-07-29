"""Translation of the iTunes Search API wire format into ``TrackCandidate``.

Apple's search response is deliberately contained here.  The discovery adapter
and its recorded-payload tests share this parser, so no Apple response shape
can escape into the application layer.  ``previewUrl`` is intentionally never
read: it is promotional content, not an acquisition source.  Artwork is also
discarded so it cannot be persisted without a separately approved usage path.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Any, Final
from urllib.parse import urlsplit

from chillify.domain.errors import ProviderResponseError
from chillify.domain.protocols import TrackCandidate

PROVIDER_NAME: Final = "apple"


def candidates_from_search(payload: object) -> tuple[TrackCandidate, ...]:
    """Parse one iTunes Search API body into normalized song candidates.

    A missing results array is a provider-contract failure.  Malformed rows
    are omitted independently, so one stale catalog record does not hide the
    rest of a search result.
    """
    if not isinstance(payload, dict):
        raise ProviderResponseError(
            "Apple Music returned a response Chillify could not read.",
            context={"provider": PROVIDER_NAME},
        )
    results = payload.get("results")
    if not isinstance(results, list):
        raise ProviderResponseError(
            "Apple Music returned a response without any results field.",
            context={"provider": PROVIDER_NAME},
        )

    candidates = []
    for item in results:
        candidate = _candidate_or_none(item)
        if candidate is not None:
            candidates.append(candidate)
    return tuple(candidates)


def _candidate_or_none(item: object) -> TrackCandidate | None:
    if not isinstance(item, dict):
        return None

    source_id = _identifier(item.get("trackId"))
    source_url = _https_url(item.get("trackViewUrl"))
    title = _text(item.get("trackName"))
    artist = _text(item.get("artistName"))
    if source_id is None or source_url is None or title is None or artist is None:
        return None

    return TrackCandidate(
        provider=PROVIDER_NAME,
        source_id=source_id,
        source_url=source_url,
        title=title,
        artist=artist,
        album=_text(item.get("collectionName")),
        release_year=_release_year(item.get("releaseDate")),
        disc_number=_positive_int(item.get("discNumber")),
        track_number=_positive_int(item.get("trackNumber")),
        duration_ms=_positive_int(item.get("trackTimeMillis")),
        isrc=None,
        # Apple's documented artwork and previews are promotional content.
        # Do not retain either until a policy-approved artwork path exists.
        artwork_url=None,
        # Apple does not supply audio for acquisition; yt-dlp resolves the
        # explicit, metadata-based search target under the user's control.
        acquisition_locator=f"ytsearch1:{artist} {title}",
        raw_fingerprint=fingerprint(item),
    )


def fingerprint(item: dict[str, Any]) -> str:
    """Return a stable provenance digest without retaining the response body."""
    accepted = {
        "trackId": item.get("trackId"),
        "trackName": item.get("trackName"),
        "artistName": item.get("artistName"),
        "collectionId": item.get("collectionId"),
        "collectionName": item.get("collectionName"),
        "releaseDate": item.get("releaseDate"),
        "discNumber": item.get("discNumber"),
        "trackNumber": item.get("trackNumber"),
        "trackTimeMillis": item.get("trackTimeMillis"),
        "trackViewUrl": item.get("trackViewUrl"),
    }
    encoded = json.dumps(accepted, separators=(",", ":"), sort_keys=True, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _identifier(value: object) -> str | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return str(value) if value > 0 else None
    text = _text(value)
    return text if text is not None and text.isdigit() and int(text) > 0 else None


def _https_url(value: object) -> str | None:
    url = _text(value)
    if url is None:
        return None
    parts = urlsplit(url)
    return url if parts.scheme == "https" and parts.hostname else None


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


def _release_year(value: object) -> int | None:
    text = _text(value)
    if text is None or len(text) < 4 or not text[:4].isdigit():
        return None
    year = int(text[:4])
    try:
        date(year, 1, 1)
    except ValueError:
        return None
    return year
