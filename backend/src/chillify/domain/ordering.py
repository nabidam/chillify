"""Deterministic ordering and the opaque keyset cursor.

Every ordering ends in the track ID, so no two rows can ever compare equal and
a keyset page can never skip or repeat a row. Unknown disc, track, and year
values sort last rather than first: absent metadata is a gap to correct, not a
reason to lead a listing.
"""

from __future__ import annotations

import base64
import json
from typing import Final

from chillify.domain.errors import ValidationFailedError
from chillify.domain.models import LibrarySort, Track, to_rfc3339

# Sorts last against any real number without special-casing the comparison.
_UNKNOWN_LAST: Final = True
_KNOWN_FIRST: Final = False

_CURSOR_VERSION: Final = 1


def _disc_track_key(track: Track) -> tuple[bool, int, bool, int]:
    disc = track.disc_number
    number = track.track_number
    return (
        _UNKNOWN_LAST if disc is None else _KNOWN_FIRST,
        disc or 0,
        _UNKNOWN_LAST if number is None else _KNOWN_FIRST,
        number or 0,
    )


def album_sort_key(track: Track) -> tuple[bool, int, bool, int, str, str]:
    """Unknown disc/track last, then disc, track, normalized title, ID."""
    return (*_disc_track_key(track), track.normalized_title, track.id)


def artist_sort_key(track: Track) -> tuple[bool, int, str, bool, int, bool, int, str]:
    """Unknown year last, then year, normalized album, disc, track, ID."""
    year = track.release_year
    return (
        _UNKNOWN_LAST if year is None else _KNOWN_FIRST,
        year or 0,
        track.normalized_album,
        *_disc_track_key(track),
        track.id,
    )


def year_sort_key(track: Track) -> tuple[str, str, bool, int, bool, int, str]:
    """Normalized artist, normalized album, disc, track, ID."""
    return (
        track.normalized_artist,
        track.normalized_album,
        *_disc_track_key(track),
        track.id,
    )


# -- library keyset cursor --------------------------------------------------


def cursor_value(track: Track, sort: LibrarySort) -> str:
    """The single comparable column that leads the requested library sort."""
    match sort:
        case LibrarySort.RECENT:
            # Rendered in the stored form so the cursor and the column it
            # bounds compare identically as text.
            return to_rfc3339(track.created_at)
        case LibrarySort.TITLE:
            return track.normalized_title
        case LibrarySort.ARTIST:
            return track.normalized_artist


def encode_cursor(track: Track, sort: LibrarySort) -> str:
    """Encode the last row of a page as the next page's exclusive lower bound."""
    payload = json.dumps(
        {"v": _CURSOR_VERSION, "s": str(sort), "k": cursor_value(track, sort), "i": str(track.id)},
        separators=(",", ":"),
        sort_keys=True,
    )
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii").rstrip("=")


def decode_cursor(cursor: str, sort: LibrarySort) -> tuple[str, str]:
    """Return the `(sort_value, track_id)` bound, or reject the cursor.

    A cursor issued for another sort is rejected rather than reinterpreted:
    silently re-anchoring it would return an arbitrary window of the library.
    """
    padding = "=" * (-len(cursor) % 4)
    try:
        decoded = json.loads(base64.urlsafe_b64decode(cursor + padding).decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValidationFailedError("That page cursor is not readable.", field="cursor") from exc

    if (
        not isinstance(decoded, dict)
        or decoded.get("v") != _CURSOR_VERSION
        or decoded.get("s") != str(sort)
        or not isinstance(decoded.get("k"), str)
        or not isinstance(decoded.get("i"), str)
    ):
        raise ValidationFailedError(
            "That page cursor does not belong to this sort.", field="cursor"
        )
    return str(decoded["k"]), str(decoded["i"])
