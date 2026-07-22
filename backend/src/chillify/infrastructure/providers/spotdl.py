"""SpotDL link recognition and inspection.

The only place a Spotify URL is understood and the only place SpotDL's metadata
JSON is normalized into a `TrackCandidate`. The fixture inspector below and the
production subprocess adapter Task 16 adds parse through these same functions,
so the isolated CLI boundary and the gate cannot disagree about the shape.

Album, playlist, artist, and episode entities are rejected from the URL alone,
before any inspection runs — SpotDL is never invoked for a collection, and no
bulk link ever reaches a job.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Final
from urllib.parse import urlsplit

from chillify.domain.errors import (
    ProviderResponseError,
    UnsupportedEntityError,
    ValidationFailedError,
)
from chillify.domain.normalization import collapse_whitespace, normalize_isrc
from chillify.domain.protocols import TrackCandidate

logger = logging.getLogger(__name__)

PROVIDER_NAME: Final = "spotify"

# Layout beneath CHILLIFY_FIXTURE_ROOT. One recorded, sanitized SpotDL metadata
# document, exactly the shape the isolated CLI emits for a single track query.
METADATA_FIXTURE: Final = "providers/spotdl_metadata.json"

_HOSTS: Final = frozenset({"open.spotify.com", "play.spotify.com"})
# A Spotify ID is twenty-two base62 characters.
_TRACK_ID: Final = re.compile(r"^[A-Za-z0-9]{22}$")
_COLLECTION_ENTITIES: Final = frozenset({"album", "playlist", "artist"})


class LinkKind(StrEnum):
    """What a recognized Spotify URL points at."""

    TRACK = "track"
    BULK = "bulk"


@dataclass(frozen=True, slots=True)
class SpotifyLink:
    """A recognized Spotify URL, classified before any inspection runs."""

    kind: LinkKind
    track_id: str | None
    canonical_url: str | None


def recognize(url: str) -> SpotifyLink | None:
    """Classify one URL, or return None when the host is not Spotify.

    Only a single `track` is acquirable. An album, playlist, artist, episode,
    or show — with or without a `/intl-xx/` locale prefix — is `BULK`.
    """
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if host not in _HOSTS:
        return None

    segments = [segment for segment in parts.path.split("/") if segment]
    # A leading locale segment such as `intl-de` precedes the entity.
    if segments and segments[0].startswith("intl-"):
        segments = segments[1:]
    if len(segments) >= 2 and segments[0] == "track" and _TRACK_ID.match(segments[1]):
        track_id = segments[1]
        return SpotifyLink(
            kind=LinkKind.TRACK,
            track_id=track_id,
            canonical_url=f"https://open.spotify.com/track/{track_id}",
        )
    return SpotifyLink(kind=LinkKind.BULK, track_id=None, canonical_url=None)


def candidate_from_metadata(
    payload: object, *, track_id: str, canonical_url: str
) -> TrackCandidate:
    """Normalize one SpotDL metadata document into a `TrackCandidate`.

    SpotDL emits a list of songs even for a single query. More than one song is
    a collection that should have been rejected before invocation; an empty list
    or a non-object is a contract failure. Exactly one song normalizes cleanly —
    Spotify metadata is authoritative, so this needs no S5 review.
    """
    song = _single_song(payload)

    title = _text(song.get("name"))
    artist = _first_artist(song)
    if title is None or artist is None:
        raise ProviderResponseError(
            "Spotify returned a track without a title Chillify could use.",
            context={"provider": PROVIDER_NAME},
        )

    return TrackCandidate(
        provider=PROVIDER_NAME,
        source_id=track_id,
        source_url=canonical_url,
        title=title,
        artist=artist,
        album=_text(song.get("album_name")),
        release_year=_release_year(song),
        disc_number=_positive_int(song.get("disc_number")),
        track_number=_positive_int(song.get("track_number")),
        duration_ms=_duration_ms(song.get("duration")),
        isrc=_isrc_or_none(song.get("isrc")),
        artwork_url=_https(song.get("cover_url")),
        # The canonical track URL is what the SpotDL subprocess acquires.
        acquisition_locator=canonical_url,
        raw_fingerprint=_fingerprint(song, track_id),
    )


@dataclass(frozen=True, slots=True)
class FixtureSpotdlInspector:
    """Spotify inspection served from a recorded SpotDL metadata document."""

    fixture_root: Path
    name: str = "spotdl"

    def supports(self, url: str) -> bool:
        """True when the URL's host is Spotify, single track or not.

        Collection rejection is `inspect`'s job: an album link is a Spotify link
        the person submitted, and it deserves "that is an album", not
        "unsupported host".
        """
        return recognize(url) is not None

    def inspect(
        self,
        url: str,
        proxy: str | None,  # noqa: ARG002 - protocol parameter; a fixture makes no request
    ) -> TrackCandidate:
        link = recognize(url)
        if link is None or link.kind is LinkKind.BULK or link.canonical_url is None:
            raise UnsupportedEntityError(
                "That is an album, playlist, or artist. Add one track at a time.",
                field="url",
                context={"provider": PROVIDER_NAME, "reason": "bulk"},
            )
        payload = _read_json(self.fixture_root / METADATA_FIXTURE)
        candidate = candidate_from_metadata(
            payload, track_id=link.track_id or "", canonical_url=link.canonical_url
        )
        logger.info("fixture spotify inspection complete", extra={"provider": self.name})
        return candidate


def _single_song(payload: object) -> dict[str, Any]:
    songs = payload if isinstance(payload, list) else [payload]
    objects = [song for song in songs if isinstance(song, dict)]
    if not objects:
        raise ProviderResponseError(
            "Spotify returned no track for that link.", context={"provider": PROVIDER_NAME}
        )
    if len(objects) > 1:
        raise ProviderResponseError(
            "That link resolved to more than one track.", context={"provider": PROVIDER_NAME}
        )
    return objects[0]


def _first_artist(song: dict[str, Any]) -> str | None:
    artists = song.get("artists")
    if isinstance(artists, list):
        for entry in artists:
            name = _text(entry)
            if name is not None:
                return name
    return _text(song.get("artist"))


def _release_year(song: dict[str, Any]) -> int | None:
    year = _positive_int(song.get("year"))
    if year is not None:
        return year
    date = _text(song.get("date"))
    if date is not None and len(date) >= 4 and date[:4].isdigit():
        return int(date[:4])
    return None


def _duration_ms(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        return None
    try:
        seconds = float(value)
    except TypeError, ValueError:
        return None
    return round(seconds * 1000) if seconds > 0 else None


def _isrc_or_none(value: object) -> str | None:
    """A malformed ISRC is dropped rather than failing the row, exactly as the
    Deezer path treats it: provider metadata, not something the person typed."""
    text = _text(value)
    if text is None:
        return None
    try:
        return normalize_isrc(text)
    except ValidationFailedError:
        return None


def _fingerprint(song: dict[str, Any], track_id: str) -> str:
    accepted = {
        "id": track_id,
        "name": song.get("name"),
        "isrc": song.get("isrc"),
        "duration": song.get("duration"),
    }
    encoded = json.dumps(accepted, separators=(",", ":"), sort_keys=True, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = collapse_whitespace(value)
    return stripped or None


def _https(value: object) -> str | None:
    text = _text(value)
    return text if text is not None and text.startswith("https://") else None


def _positive_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        return None
    try:
        number = int(float(value))
    except TypeError, ValueError:
        return None
    return number if number > 0 else None


def _read_json(path: Path) -> object:
    if not path.is_file():
        raise ProviderResponseError(
            "The gate Spotify fixture is missing.", context={"provider": PROVIDER_NAME}
        )
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProviderResponseError(
            "The gate Spotify fixture could not be read.", context={"provider": PROVIDER_NAME}
        ) from exc
