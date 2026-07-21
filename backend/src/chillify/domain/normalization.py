"""The one versioned normalizer.

Search keys, uniqueness folds, and derived context keys all come from this
module so a value written by the worker and a value queried by the API can
never disagree. Changing any rule here requires a version bump and a backfill
migration, because stored `normalized_*` columns are the persisted output.
"""

from __future__ import annotations

import base64
import re
import unicodedata
from datetime import datetime
from typing import Final

from chillify.domain.errors import ValidationFailedError

# Bump only together with a migration that rewrites every stored normalized
# column; the columns are this function's cache, not an independent value.
NORMALIZER_VERSION: Final = 1

PROFILE_NAME_MIN_LENGTH: Final = 1
PROFILE_NAME_MAX_LENGTH: Final = 40
PLAYLIST_NAME_MIN_LENGTH: Final = 1
PLAYLIST_NAME_MAX_LENGTH: Final = 100
METADATA_TEXT_MAX_LENGTH: Final = 200
DISC_OR_TRACK_NUMBER_MIN: Final = 1
DISC_OR_TRACK_NUMBER_MAX: Final = 999
RELEASE_YEAR_MIN: Final = 1000

# Deterministic stand-ins for absent metadata. A real album literally named
# "Unknown Album" therefore shares the absent-album context; that collision is
# accepted deliberately in exchange for a normalizer with no special cases.
UNKNOWN_ARTIST: Final = "unknown artist"
UNKNOWN_TITLE: Final = "unknown title"
UNKNOWN_ALBUM: Final = "unknown album"

_ISRC_PATTERN: Final = re.compile(r"^[A-Z]{2}[A-Z0-9]{3}[0-9]{7}$")
_WHITESPACE_RUN: Final = re.compile(r"\s+")
# Everything that is neither a letter, a digit, nor a space is dropped rather
# than replaced, so "Sgt. Pepper" and "Sgt Pepper" share one key.
_NON_SEARCHABLE: Final = re.compile(r"[^\w\s]", re.UNICODE)


def collapse_whitespace(value: str) -> str:
    """Trim and reduce every internal whitespace run to one space."""
    return _WHITESPACE_RUN.sub(" ", value).strip()


def normalize_key(value: str, *, fallback: str) -> str:
    """Return the search/uniqueness key for one metadata value.

    Compatibility-decomposed, stripped of combining marks and punctuation,
    case-folded, and whitespace-collapsed. An input that normalizes away
    entirely yields the caller's deterministic fallback, because the stored
    columns are `NOT NULL` and must stay groupable.
    """
    decomposed = unicodedata.normalize("NFKD", value)
    without_marks = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    stripped = _NON_SEARCHABLE.sub(" ", without_marks)
    folded = collapse_whitespace(stripped).casefold()
    return folded or fallback


def normalize_artist(value: str) -> str:
    return normalize_key(value, fallback=UNKNOWN_ARTIST)


def normalize_title(value: str) -> str:
    return normalize_key(value, fallback=UNKNOWN_TITLE)


def normalize_album(value: str | None) -> str:
    """An absent album shares the artist's deterministic Unknown Album context."""
    if value is None:
        return UNKNOWN_ALBUM
    return normalize_key(value, fallback=UNKNOWN_ALBUM)


def fold_name(value: str) -> str:
    """Fold a profile or playlist name for its uniqueness constraint.

    Unlike a search key this keeps punctuation: "DJ K." and "DJ K" are two
    households a person can tell apart, so the database must too.
    """
    return collapse_whitespace(unicodedata.normalize("NFKC", value)).casefold()


def validate_profile_name(raw: str) -> str:
    """Return the storable profile name or raise the field-level failure."""
    name = collapse_whitespace(unicodedata.normalize("NFKC", raw))
    if len(name) < PROFILE_NAME_MIN_LENGTH:
        raise ValidationFailedError("A profile name cannot be empty.", field="name")
    if len(name) > PROFILE_NAME_MAX_LENGTH:
        raise ValidationFailedError(
            f"A profile name may be at most {PROFILE_NAME_MAX_LENGTH} characters.",
            field="name",
            context={"max_length": PROFILE_NAME_MAX_LENGTH},
        )
    return name


def validate_playlist_name(raw: str) -> str:
    """Return the storable playlist name or raise the field-level failure.

    Length is measured on the collapsed form, which is also what the uniqueness
    fold sees, so a name accepted here is a name the constraint can hold.
    """
    name = collapse_whitespace(unicodedata.normalize("NFKC", raw))
    if len(name) < PLAYLIST_NAME_MIN_LENGTH:
        raise ValidationFailedError("A playlist name cannot be empty.", field="name")
    if len(name) > PLAYLIST_NAME_MAX_LENGTH:
        raise ValidationFailedError(
            f"A playlist name may be at most {PLAYLIST_NAME_MAX_LENGTH} characters.",
            field="name",
            context={"max_length": PLAYLIST_NAME_MAX_LENGTH},
        )
    return name


def validate_required_text(raw: str, *, field: str, label: str) -> str:
    """Return a collapsed, non-empty metadata value bounded by the column."""
    value = collapse_whitespace(unicodedata.normalize("NFKC", raw))
    if not value:
        raise ValidationFailedError(f"{label} cannot be empty.", field=field)
    if len(value) > METADATA_TEXT_MAX_LENGTH:
        raise ValidationFailedError(
            f"{label} may be at most {METADATA_TEXT_MAX_LENGTH} characters.",
            field=field,
            context={"max_length": METADATA_TEXT_MAX_LENGTH},
        )
    return value


def validate_optional_text(raw: str | None, *, field: str, label: str) -> str | None:
    """Return a collapsed optional value, treating a blank string as absence.

    A cleared album field arrives as `""`, and an absent one arrives as null.
    Both mean the same thing to a person, so both become None here rather than
    letting an empty string reach a `length >= 1` column check.
    """
    if raw is None:
        return None
    value = collapse_whitespace(unicodedata.normalize("NFKC", raw))
    if not value:
        return None
    if len(value) > METADATA_TEXT_MAX_LENGTH:
        raise ValidationFailedError(
            f"{label} may be at most {METADATA_TEXT_MAX_LENGTH} characters.",
            field=field,
            context={"max_length": METADATA_TEXT_MAX_LENGTH},
        )
    return value


def validate_ordinal(value: int | None, *, field: str, label: str) -> int | None:
    """Bound a disc or track number to the range the column accepts."""
    if value is None:
        return None
    if value < DISC_OR_TRACK_NUMBER_MIN or value > DISC_OR_TRACK_NUMBER_MAX:
        raise ValidationFailedError(
            f"{label} must be between {DISC_OR_TRACK_NUMBER_MIN} and {DISC_OR_TRACK_NUMBER_MAX}.",
            field=field,
            context={"minimum": DISC_OR_TRACK_NUMBER_MIN, "maximum": DISC_OR_TRACK_NUMBER_MAX},
        )
    return value


def validate_release_year(value: int | None, *, now: datetime) -> int | None:
    """Bound a release year by the injected clock, not by a literal.

    The database check is a corruption guard with a far wider range; this is the
    rule a person's input is actually held to.
    """
    if value is None:
        return None
    upper = now.year + 1
    if value < RELEASE_YEAR_MIN or value > upper:
        raise ValidationFailedError(
            f"A release year must be between {RELEASE_YEAR_MIN} and {upper}.",
            field="release_year",
            context={"minimum": RELEASE_YEAR_MIN, "maximum": upper},
        )
    return value


def normalize_isrc(value: str | None) -> str | None:
    """Return the canonical ISRC, or None when the field is absent.

    An empty or whitespace-only value is absence, not a malformed code: provider
    payloads routinely carry `""` for a track that simply has no ISRC.
    """
    if value is None:
        return None
    candidate = re.sub(r"[\s-]", "", value).upper()
    if not candidate:
        return None
    if not _ISRC_PATTERN.match(candidate):
        raise ValidationFailedError("That ISRC is not a valid 12-character code.", field="isrc")
    return candidate


# -- derived context keys --------------------------------------------------


def _encode(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii").rstrip("=")


def _decode(key: str) -> str:
    padding = "=" * (-len(key) % 4)
    try:
        return base64.urlsafe_b64decode(key + padding).decode("utf-8")
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValidationFailedError("That context key is not a valid identifier.") from exc


def encode_artist_key(normalized_artist: str) -> str:
    """Unpadded base64url of the UTF-8 normalized artist."""
    return _encode(normalized_artist)


def decode_artist_key(key: str) -> str:
    """Decode and verify canonical form before the value reaches a query.

    Canonical means two things: the key re-encodes to itself, and the value it
    carries is already normalized. Without the second check a key could name a
    string no stored row can ever hold.
    """
    artist = _decode(key)
    if not artist or encode_artist_key(artist) != key or normalize_artist(artist) != artist:
        raise ValidationFailedError("That artist key is not in canonical form.")
    return artist


def encode_album_key(normalized_artist: str, normalized_album: str) -> str:
    """Unpadded base64url of `normalized_artist + NUL + normalized_album`."""
    return _encode(f"{normalized_artist}\x00{normalized_album}")


def decode_album_key(key: str) -> tuple[str, str]:
    """Decode and verify canonical form; same-named albums stay separate."""
    decoded = _decode(key)
    artist, separator, album = decoded.partition("\x00")
    if (
        not separator
        or not artist
        or not album
        or encode_album_key(artist, album) != key
        or normalize_artist(artist) != artist
        or normalize_album(album) != album
    ):
        raise ValidationFailedError("That album key is not in canonical form.")
    return artist, album
