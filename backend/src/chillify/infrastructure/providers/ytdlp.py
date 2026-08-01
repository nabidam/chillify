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
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Final, Protocol
from urllib.parse import parse_qs, urlsplit

from chillify.domain.errors import (
    AcquisitionCancelledError,
    AcquisitionFailedError,
    ProviderResponseError,
    UnsupportedEntityError,
)
from chillify.domain.jobs import JobPhase
from chillify.domain.normalization import collapse_whitespace, normalize_key
from chillify.domain.protocols import (
    AudioArtifact,
    CancelledCallback,
    ProgressCallback,
    TrackCandidate,
)
from chillify.infrastructure.providers.mp3 import single_valid_mp3

logger = logging.getLogger(__name__)

PROVIDER_NAME: Final = "youtube"

# Duration agreement for a Deezer `ytsearch1:` match: the wider of ten seconds
# or fifteen percent, so a weak match is refused rather than silently accepted.
_MIN_DURATION_TOLERANCE_MS: Final = 10_000
_DURATION_TOLERANCE_FRACTION: Final = 0.15

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


class YoutubeDLLike(Protocol):
    """The one yt-dlp method these adapters use, so a test can inject a double."""

    def extract_info(self, url: str, *, download: bool) -> object: ...


# Opens a configured yt-dlp handle as a context manager. Real `yt_dlp.YoutubeDL`
# already is one; a test supplies a double so no case here touches the network.
YdlFactory = Callable[[dict[str, Any]], AbstractContextManager[YoutubeDLLike]]


class _AcquisitionAbortedError(Exception):
    """Internal signal raised inside a progress hook to stop a cancelled run."""


def _default_ydl_factory(options: dict[str, Any]) -> AbstractContextManager[YoutubeDLLike]:
    """Build a real yt-dlp handle. Imported lazily so the package loads once."""
    import yt_dlp

    return yt_dlp.YoutubeDL(options)  # type: ignore[no-any-return]


@dataclass(frozen=True, slots=True)
class YouTubeInspector:
    """Production YouTube inspection through the injected yt-dlp Python API.

    Recognition and bulk rejection are URL-only and identical to the fixture
    inspector's; only the metadata source differs, so both are held to one
    contract. `skip_download` and `noplaylist` keep inspection metadata-only.
    """

    ydl_factory: YdlFactory = field(default=_default_ydl_factory)
    name: str = "yt_dlp"

    def supports(self, url: str) -> bool:
        return recognize(url) is not None

    def inspect(self, url: str, proxy: str | None) -> TrackCandidate:
        link = recognize(url)
        if link is None or link.kind is LinkKind.BULK or link.canonical_url is None:
            raise UnsupportedEntityError(
                "That is a playlist or channel. Add one video at a time.",
                field="url",
                context={"provider": PROVIDER_NAME, "reason": "bulk"},
            )
        options: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "noplaylist": True,
            "extract_flat": False,
        }
        if proxy is not None:
            options["proxy"] = proxy
        try:
            with self.ydl_factory(options) as ydl:
                info = ydl.extract_info(link.canonical_url, download=False)
        except _AcquisitionAbortedError:
            raise
        except Exception as exc:
            # The adapter boundary translates the third-party failure once; the
            # yt-dlp message (which can carry the URL) never travels onward.
            raise ProviderResponseError(
                "YouTube could not be inspected.", context={"provider": PROVIDER_NAME}
            ) from exc
        candidate = candidate_from_info(
            info, video_id=link.video_id or "", canonical_url=link.canonical_url
        )
        logger.info("youtube inspection complete", extra={"provider": self.name})
        return candidate


@dataclass(frozen=True, slots=True)
class YtDlpAcquisitionProvider:
    """Production audio retrieval through the injected yt-dlp Python API.

    A direct YouTube candidate acquires its canonical video; a Deezer candidate
    acquires `ytsearch1:{artist} {title}` and its first match must agree on
    title/artist and, when both are known, duration — a weak match fails rather
    than downloading quietly. Cancellation is consulted inside the progress hook
    and between phases, and a cancelled or failed run leaves no file behind.
    """

    ydl_factory: YdlFactory = field(default=_default_ydl_factory)
    name: str = "yt_dlp"

    def acquire(
        self,
        candidate: TrackCandidate,
        workspace: str,
        proxy: str | None,
        progress: ProgressCallback,
        cancelled: CancelledCallback,
    ) -> AudioArtifact:
        workspace_path = Path(workspace)
        if cancelled():
            raise AcquisitionCancelledError("That download was cancelled.")

        aborted = {"tripped": False}

        def hook(status: dict[str, Any]) -> None:
            if cancelled():
                aborted["tripped"] = True
                raise _AcquisitionAbortedError
            if status.get("status") == "downloading":
                progress(JobPhase.DOWNLOADING, _download_percent(status))

        options: dict[str, Any] = {
            "format": "bestaudio/best",
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "outtmpl": {"default": str(workspace_path / "%(id)s.%(ext)s")},
            "progress_hooks": [hook],
            "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3"}],
        }
        if proxy is not None:
            options["proxy"] = proxy

        info: object
        try:
            with self.ydl_factory(options) as ydl:
                info = ydl.extract_info(candidate.acquisition_locator, download=True)
        except _AcquisitionAbortedError as exc:
            _clear(workspace_path)
            raise AcquisitionCancelledError("That download was cancelled.") from exc
        except Exception as exc:
            _clear(workspace_path)
            if aborted["tripped"] or cancelled():
                # yt-dlp may wrap the hook's abort in its own error; a cancel
                # that was requested is reported as a cancel, never a failure.
                raise AcquisitionCancelledError("That download was cancelled.") from exc
            raise AcquisitionFailedError(
                "YouTube audio could not be downloaded.", context={"provider": self.name}
            ) from exc

        try:
            audio_path, duration_ms = single_valid_mp3(workspace_path, provider=self.name)
            if candidate.acquisition_locator.startswith("ytsearch"):
                _enforce_search_match(candidate, info, duration_ms, provider=self.name)
        except AcquisitionFailedError:
            # A produced-but-rejected file — a weak search match or an invalid
            # MP3 — is never kept; the workspace is left clean for the retry.
            _clear(workspace_path)
            raise
        progress(JobPhase.DOWNLOADING, 100.0)
        logger.info("youtube acquisition complete", extra={"provider": self.name})
        return AudioArtifact(
            location=str(audio_path),
            duration_ms=duration_ms,
            byte_size=audio_path.stat().st_size,
        )


def _download_percent(status: dict[str, Any]) -> float | None:
    """Real downloaded fraction when a total is known, else None. Never invented."""
    downloaded = status.get("downloaded_bytes")
    total = status.get("total_bytes") or status.get("total_bytes_estimate")
    if not isinstance(downloaded, int | float) or not isinstance(total, int | float) or total <= 0:
        return None
    return max(0.0, min(100.0, downloaded / total * 100.0))


def _enforce_search_match(
    candidate: TrackCandidate, info: object, duration_ms: int, *, provider: str
) -> None:
    """Refuse a `ytsearch1:` result that does not match the Deezer candidate."""
    entry = _first_entry(info)
    title = _text(entry.get("track")) or _text(entry.get("title"))
    artist = (
        _text(entry.get("artist")) or _text(entry.get("uploader")) or _text(entry.get("channel"))
    )
    if title is None or artist is None:
        raise AcquisitionFailedError(
            "The search result had no usable title to verify.", context={"provider": provider}
        )
    if normalize_key(candidate.title, fallback="") not in normalize_key(title, fallback="") and (
        normalize_key(title, fallback="") not in normalize_key(candidate.title, fallback="")
    ):
        raise AcquisitionFailedError(
            "The best audio match did not match the requested track.",
            context={"provider": provider},
        )
    if candidate.duration_ms is not None and duration_ms > 0:
        tolerance = max(
            _MIN_DURATION_TOLERANCE_MS,
            int(candidate.duration_ms * _DURATION_TOLERANCE_FRACTION),
        )
        if abs(candidate.duration_ms - duration_ms) > tolerance:
            raise AcquisitionFailedError(
                "The best audio match ran too long or short to be the same track.",
                context={"provider": provider},
            )


def _first_entry(info: object) -> dict[str, Any]:
    if isinstance(info, dict):
        entries = info.get("entries")
        if isinstance(entries, list):
            for entry in entries:
                if isinstance(entry, dict):
                    return entry
            return {}
        return info
    return {}


def _clear(workspace: Path) -> None:
    """Remove every partial file a cancelled or failed run may have left."""
    if not workspace.is_dir():
        return
    for path in workspace.iterdir():
        if path.is_file():
            path.unlink(missing_ok=True)


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
