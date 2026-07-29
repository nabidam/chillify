"""MusicBrainz recording-search translation into ``TrackCandidate``.

Only this module understands the MusicBrainz JSON shape.  A result row is
untrusted provider data: a malformed row is omitted, while a malformed search
envelope is a typed provider-contract error.  This keeps the rest of the
application independent from MusicBrainz's release and artist-credit shapes.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Final

from chillify.domain.errors import ProviderResponseError, ValidationFailedError
from chillify.domain.normalization import normalize_isrc
from chillify.domain.protocols import TrackCandidate

PROVIDER_NAME: Final = "musicbrainz"


def candidates_from_recording_search(payload: object) -> tuple[TrackCandidate, ...]:
    """Return usable candidates from one documented recording-search response."""
    if not isinstance(payload, dict):
        raise _invalid_response("MusicBrainz returned a response Chillify could not read.")
    recordings = payload.get("recordings")
    if not isinstance(recordings, list):
        raise _invalid_response("MusicBrainz returned a response without any recordings field.")

    candidates: list[TrackCandidate] = []
    for recording in recordings:
        candidate = _candidate_or_none(recording)
        if candidate is not None:
            candidates.append(candidate)
    return tuple(candidates)


def _candidate_or_none(recording: object) -> TrackCandidate | None:
    if not isinstance(recording, dict):
        return None
    mbid = _mbid(recording.get("id"))
    title = _text(recording.get("title"))
    artist = _artist_credit(recording.get("artist-credit"))
    if mbid is None or title is None or artist is None:
        return None

    return TrackCandidate(
        provider=PROVIDER_NAME,
        source_id=mbid,
        source_url=f"https://musicbrainz.org/recording/{mbid}",
        title=title,
        artist=artist,
        album=_unambiguous_release_title(recording.get("releases")),
        release_year=_first_release_year(recording),
        disc_number=None,
        track_number=None,
        duration_ms=_positive_int(recording.get("length")),
        isrc=_first_valid_isrc(recording.get("isrcs")),
        # Cover Art Archive is deliberately not contacted in the search path.
        # A selected candidate can be enriched separately if artwork is wanted.
        artwork_url=None,
        acquisition_locator=f"ytsearch1:{artist} {title}",
        raw_fingerprint=fingerprint(recording),
    )


def fingerprint(recording: dict[str, Any]) -> str:
    """Make provenance stable without retaining a provider response body."""
    accepted = {
        "id": recording.get("id"),
        "title": recording.get("title"),
        "length": recording.get("length"),
        "artist-credit": recording.get("artist-credit"),
        "isrcs": recording.get("isrcs"),
        "releases": recording.get("releases"),
    }
    encoded = json.dumps(accepted, separators=(",", ":"), sort_keys=True, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _artist_credit(value: object) -> str | None:
    if not isinstance(value, list) or not value:
        return None
    parts: list[str] = []
    for credit in value:
        if not isinstance(credit, dict):
            return None
        name = _text(credit.get("name")) or _text(_nested(credit, "artist", "name"))
        if name is None:
            return None
        joinphrase = credit.get("joinphrase", "")
        if not isinstance(joinphrase, str):
            return None
        parts.extend((name, joinphrase))
    return _text("".join(parts))


def _unambiguous_release_title(value: object) -> str | None:
    """Use an album only when all supplied releases name the same one."""
    if not isinstance(value, list) or not value:
        return None
    titles: set[str] = set()
    for release in value:
        if not isinstance(release, dict):
            return None
        title = _text(release.get("title"))
        if title is None:
            return None
        titles.add(title)
    return titles.pop() if len(titles) == 1 else None


def _first_release_year(recording: dict[str, Any]) -> int | None:
    """Return the earliest valid year among MusicBrainz's release-date hints."""
    years = [_year(recording.get("first-release-date"))]
    releases = recording.get("releases")
    if isinstance(releases, list):
        for release in releases:
            if not isinstance(release, dict):
                continue
            years.append(_year(release.get("date")))
            years.append(_year(_nested(release, "release-group", "first-release-date")))
    known = [year for year in years if year is not None]
    return min(known) if known else None


def _first_valid_isrc(value: object) -> str | None:
    if not isinstance(value, list):
        return None
    for raw in value:
        text = _text(raw)
        if text is None:
            continue
        try:
            return normalize_isrc(text)
        except ValidationFailedError:
            continue
    return None


def _nested(item: dict[str, Any], parent: str, child: str) -> object:
    container = item.get(parent)
    return container.get(child) if isinstance(container, dict) else None


def _mbid(value: object) -> str | None:
    """Accept MusicBrainz UUIDs, but not arbitrary provider identifiers."""
    text = _text(value)
    if text is None:
        return None
    parts = text.split("-")
    if [len(part) for part in parts] != [8, 4, 4, 4, 12]:
        return None
    try:
        int("".join(parts), 16)
    except ValueError:
        return None
    return text.lower()


def _year(value: object) -> int | None:
    text = _text(value)
    if text is None or len(text) < 4 or not text[:4].isdigit():
        return None
    year = int(text[:4])
    return year if 1 <= year <= 9999 else None


def _positive_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _invalid_response(message: str) -> ProviderResponseError:
    return ProviderResponseError(message, context={"provider": PROVIDER_NAME})
