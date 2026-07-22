"""yt-dlp link recognition and inspection.

This is the only place a YouTube URL is understood and the only place a yt-dlp
`extract_info` document is normalized into a `TrackCandidate`. Both the fixture
inspector below and the production adapter Task 16 adds parse through these same
functions, so a payload one accepts cannot be a payload the other rejects.

Recognition is URL-only and never touches the network: a playlist, channel, or
foreign host is rejected before any inspection is invoked, which is what keeps a
bulk link from ever reaching the extractor or creating a job.
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
from urllib.parse import parse_qs, urlsplit

from chillify.domain.errors import ProviderResponseError, UnsupportedEntityError
from chillify.domain.normalization import collapse_whitespace
from chillify.domain.protocols import TrackCandidate

logger = logging.getLogger(__name__)

PROVIDER_NAME: Final = "youtube"

# Layout beneath CHILLIFY_FIXTURE_ROOT. One recorded, sanitized `extract_info`
# document with `skip_download`, exactly as the production adapter would receive.
INSPECT_FIXTURE: Final = "providers/ytdlp_inspect.json"

_VIDEO_HOSTS: Final = frozenset(
    {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"}
)
_SHORT_HOST: Final = "youtu.be"
# A YouTube video ID is eleven URL-safe base64 characters.
_VIDEO_ID: Final = re.compile(r"^[A-Za-z0-9_-]{11}$")
# Path prefixes that carry the video ID as their next segment.
_ID_IN_PATH: Final = ("/shorts/", "/embed/", "/v/", "/live/")


class LinkKind(StrEnum):
    """What a recognized YouTube URL points at."""

    VIDEO = "video"
    BULK = "bulk"


@dataclass(frozen=True, slots=True)
class YouTubeLink:
    """A recognized YouTube URL, classified before any inspection runs."""

    kind: LinkKind
    video_id: str | None
    canonical_url: str | None


def recognize(url: str) -> YouTubeLink | None:
    """Classify one URL, or return None when the host is not YouTube.

    A single video — including a video reached inside a playlist context — is
    `VIDEO`. A bare playlist, channel, or handle is `BULK`. A `noplaylist`
    stance is expressed here: `watch?v=X&list=Y` is the video X, not the list.
    """
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if host not in _VIDEO_HOSTS and host != _SHORT_HOST:
        return None

    video_id = _extract_video_id(host, parts.path, parts.query)
    if video_id is None:
        return YouTubeLink(kind=LinkKind.BULK, video_id=None, canonical_url=None)
    return YouTubeLink(
        kind=LinkKind.VIDEO,
        video_id=video_id,
        canonical_url=f"https://www.youtube.com/watch?v={video_id}",
    )


def _extract_video_id(host: str, path: str, query: str) -> str | None:
    if host == _SHORT_HOST:
        return _valid_id(path.lstrip("/").split("/", 1)[0])
    if path == "/watch":
        values = parse_qs(query).get("v", [])
        return _valid_id(values[0]) if values else None
    for prefix in _ID_IN_PATH:
        if path.startswith(prefix):
            return _valid_id(path[len(prefix) :].split("/", 1)[0])
    return None


def _valid_id(value: str) -> str | None:
    return value if _VIDEO_ID.match(value) else None


def candidate_from_info(info: object, *, video_id: str, canonical_url: str) -> TrackCandidate:
    """Normalize one yt-dlp `extract_info` document into a `TrackCandidate`.

    A playlist document, a non-object, or a document without a usable title is a
    provider-contract failure: the inspector asked for one video and must get
    one. Every other field is optional and simply stays absent when missing —
    YouTube metadata is unreliable, which is exactly why S5 reviews it.
    """
    if not isinstance(info, dict):
        raise ProviderResponseError(
            "YouTube returned something Chillify could not read.",
            context={"provider": PROVIDER_NAME},
        )
    if info.get("_type") == "playlist" or "entries" in info:
        raise ProviderResponseError(
            "That link resolved to a playlist rather than a single video.",
            context={"provider": PROVIDER_NAME},
        )

    title = _text(info.get("track")) or _text(info.get("title"))
    artist = _text(info.get("artist")) or _text(info.get("uploader")) or _text(info.get("channel"))
    if title is None or artist is None:
        raise ProviderResponseError(
            "YouTube did not return a title Chillify could use.",
            context={"provider": PROVIDER_NAME},
        )

    return TrackCandidate(
        provider=PROVIDER_NAME,
        source_id=video_id,
        source_url=canonical_url,
        title=title,
        artist=artist,
        album=_text(info.get("album")),
        release_year=_release_year(info),
        disc_number=None,
        track_number=None,
        duration_ms=_duration_ms(info.get("duration")),
        isrc=None,
        artwork_url=_https(info.get("thumbnail")),
        # The video itself is the acquisition target; there is no search to run.
        acquisition_locator=canonical_url,
        raw_fingerprint=_fingerprint(info, video_id),
    )


@dataclass(frozen=True, slots=True)
class FixtureYouTubeInspector:
    """YouTube inspection served from a recorded `extract_info` document.

    It recognizes the same URLs the production adapter does and returns the same
    normalized shape, so a gate walkthrough exercises the real inspection use
    case — recognition, rejection, normalization — without contacting YouTube.
    """

    fixture_root: Path
    name: str = "yt_dlp"

    def supports(self, url: str) -> bool:
        """True when the URL's host is YouTube, single video or not.

        Bulk rejection is `inspect`'s job, not this one's: a playlist link is a
        YouTube link the person genuinely submitted, and reporting "unsupported
        host" for it would be a worse error than "that is a playlist".
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
                "That is a playlist or channel. Add one video at a time.",
                field="url",
                context={"provider": PROVIDER_NAME, "reason": "bulk"},
            )
        info = _read_json(self.fixture_root / INSPECT_FIXTURE)
        candidate = candidate_from_info(
            info, video_id=link.video_id or "", canonical_url=link.canonical_url
        )
        logger.info("fixture youtube inspection complete", extra={"provider": self.name})
        return candidate


def _release_year(info: dict[str, Any]) -> int | None:
    year = _positive_int(info.get("release_year"))
    if year is not None:
        return year
    upload_date = _text(info.get("upload_date"))
    if upload_date is not None and len(upload_date) >= 4 and upload_date[:4].isdigit():
        return int(upload_date[:4])
    return None


def _duration_ms(value: object) -> int | None:
    seconds = _positive_int(value)
    return None if seconds is None else seconds * 1000


def _fingerprint(info: dict[str, Any], video_id: str) -> str:
    """A stable digest of the accepted fields, for provenance without the body."""
    accepted = {
        "id": video_id,
        "title": info.get("title"),
        "track": info.get("track"),
        "artist": info.get("artist"),
        "duration": info.get("duration"),
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
            "The gate YouTube fixture is missing.", context={"provider": PROVIDER_NAME}
        )
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProviderResponseError(
            "The gate YouTube fixture could not be read.", context={"provider": PROVIDER_NAME}
        ) from exc
