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
import os
import re
import signal
import subprocess
import tempfile
import time
from collections.abc import Callable, Sequence
from contextlib import suppress
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Final
from urllib.parse import urlsplit

from chillify.domain.errors import (
    AcquisitionCancelledError,
    AcquisitionFailedError,
    ProviderResponseError,
    UnsupportedEntityError,
    ValidationFailedError,
)
from chillify.domain.normalization import collapse_whitespace, normalize_isrc
from chillify.domain.protocols import (
    AudioArtifact,
    CancelledCallback,
    ProgressCallback,
    TrackCandidate,
)
from chillify.infrastructure.providers.mp3 import single_valid_mp3
from chillify.infrastructure.security.outbound import parse_proxy

logger = logging.getLogger(__name__)

PROVIDER_NAME: Final = "spotify"

# SpotDL is invoked as an argument vector, never a shell. These timeouts bound a
# metadata inspection and a full download respectively.
#
# `save` performs a YouTube Music connectivity preflight (`get_visitor_id`)
# ahead of the actual Spotify metadata fetch. Once the child's proxy env is
# fixed to actually route that traffic through a SOCKS proxy instead of
# failing DNS resolution instantly, the round trip's wall time is bounded by
# the proxy's real latency rather than a fast local failure. Measured live
# against the release gate's proxy: two full `save` invocations completed in
# 122 s and 140 s. 60 s was sized for the pre-fix failure mode, not this one,
# so it fails almost every real inspection on a proxied network; 180 s gives
# headroom above the observed range without approaching the 600 s download
# bound below.
_INSPECT_TIMEOUT_SECONDS: Final = 180.0
_DOWNLOAD_TIMEOUT_SECONDS: Final = 600.0
# How often the download runner checks the cancellation flag while SpotDL runs.
_CANCEL_POLL_SECONDS: Final = 0.2

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


@dataclass(frozen=True, slots=True)
class SubprocessResult:
    """The captured outcome of one SpotDL invocation."""

    returncode: int
    stdout: str
    stderr: str


# Runs one SpotDL argument vector and returns its captured result. A test injects
# a double so no case here launches a real process. `cancelled` is consulted by
# the download runner while the child runs; inspection passes None.
SpotdlRunner = Callable[..., SubprocessResult]


def _default_spotdl_runner(
    argv: Sequence[str],
    *,
    timeout: float,
    cancelled: CancelledCallback | None = None,
    env: dict[str, str] | None = None,
) -> SubprocessResult:
    """Launch SpotDL in its own process group and capture its output.

    The child runs in a new session so a cancellation can terminate the whole
    process group, not just the parent shell SpotDL would otherwise leave. When
    `cancelled` is supplied it is polled while the child runs and the group is
    killed the moment a cancel is seen.

    `env` is either None — the child inherits this process's environment
    unchanged, exactly Python's default when `Popen(env=None)` — or a full
    environment mapping built by `_child_env`, which starts from this
    process's environment and adds the proxy variables. Either way the child
    always inherits `PATH`, `HOME`, temp-dir, and locale variables it needs;
    only the proxy variables are ever added on top.
    """
    process = subprocess.Popen(
        list(argv),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
        env=env,
    )
    deadline = time.monotonic() + timeout
    while True:
        try:
            stdout, stderr = process.communicate(timeout=_CANCEL_POLL_SECONDS)
        except subprocess.TimeoutExpired:
            if cancelled is not None and cancelled():
                _terminate_group(process)
                raise AcquisitionCancelledError("That download was cancelled.") from None
            if time.monotonic() > deadline:
                _terminate_group(process)
                raise AcquisitionFailedError(
                    "SpotDL did not finish in time.", context={"provider": PROVIDER_NAME}
                ) from None
            continue
        return SubprocessResult(returncode=process.returncode, stdout=stdout, stderr=stderr)


def _terminate_group(process: subprocess.Popen[str]) -> None:
    with suppress(ProcessLookupError, PermissionError):
        os.killpg(os.getpgid(process.pid), signal.SIGKILL)


def _proxy_for_child_env(proxy: str) -> str:
    """Rewrite a saved proxy for the SpotDL child's environment.

    `HTTP_PROXY`/`HTTPS_PROXY` are honoured by the `requests`/urllib3 stack
    SpotDL uses internally (album art, YouTube Music lookups, and more) — the
    traffic that a bare `--proxy` CLI flag never reaches. Plain `socks5://`
    makes urllib3 resolve the target hostname *locally* before tunnelling
    through the proxy; on a network whose DNS is hijacked or otherwise
    unreachable (the exact case this fixes — `music.youtube.com` failing to
    resolve) that local lookup fails before the proxy ever gets a chance.
    `socks5h://` pushes DNS resolution through the proxy itself, which is what
    actually works. `http://`/`https://` proxies already resolve remotely via
    `CONNECT`, so they pass through unchanged; an already-`socks5h://` proxy is
    left alone too. `parse_proxy` (the one URL parser this codebase uses for
    proxy strings) supplies the validated scheme; only the scheme segment is
    rewritten so any embedded credentials survive untouched.
    """
    endpoint = parse_proxy(proxy)
    if endpoint.scheme == "socks5":
        return "socks5h://" + endpoint.raw.split("://", 1)[1]
    return endpoint.raw


def _child_env(proxy: str | None) -> dict[str, str] | None:
    """Build the SpotDL child's environment, or None to inherit unchanged.

    ARCHITECTURE's SpotDL contract calls for "the saved proxy exported only to
    the child": never on argv, where `ps` on the host would expose it —
    including any embedded proxy credential — to every other user on the
    machine. `None` here means `subprocess.Popen(env=None)`, which inherits
    this process's environment verbatim, so `PATH`/`HOME`/temp-dir/locale are
    always present; the proxy variables are the only addition ever made.
    """
    if proxy is None:
        return None
    env = dict(os.environ)
    child_proxy = _proxy_for_child_env(proxy)
    for key in ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy"):
        env[key] = child_proxy
    return env


@dataclass(frozen=True, slots=True)
class SpotdlInspector:
    """Production Spotify inspection through the isolated SpotDL CLI.

    Recognition and collection rejection are URL-only and identical to the
    fixture inspector's; SpotDL is invoked with `save` to emit one metadata
    document, which normalizes through the same `candidate_from_metadata` the
    fixture uses. The exact flags are the contract this adapter's test pins.
    """

    executable: str = "spotdl"
    runner: SpotdlRunner = field(default=_default_spotdl_runner)
    name: str = "spotdl"

    def supports(self, url: str) -> bool:
        return recognize(url) is not None

    def inspect(self, url: str, proxy: str | None) -> TrackCandidate:
        link = recognize(url)
        if link is None or link.kind is LinkKind.BULK or link.canonical_url is None:
            raise UnsupportedEntityError(
                "That is an album, playlist, or artist. Add one track at a time.",
                field="url",
                context={"provider": PROVIDER_NAME, "reason": "bulk"},
            )
        with tempfile.TemporaryDirectory(prefix="chillify-spotdl-") as directory:
            save_file = Path(directory) / "metadata.spotdl"
            argv = [
                self.executable,
                "save",
                link.canonical_url,
                "--save-file",
                str(save_file),
            ]
            result = self.runner(argv, timeout=_INSPECT_TIMEOUT_SECONDS, env=_child_env(proxy))
            if result.returncode != 0 or not save_file.is_file():
                # The captured stderr can carry the URL and the proxy; it is
                # logged under the provider, never returned to the browser.
                logger.info(
                    "spotdl inspection failed",
                    extra={"provider": self.name, "returncode": result.returncode},
                )
                raise ProviderResponseError(
                    "Spotify could not be inspected.", context={"provider": PROVIDER_NAME}
                )
            payload = _read_json(save_file)
        candidate = candidate_from_metadata(
            payload, track_id=link.track_id or "", canonical_url=link.canonical_url
        )
        logger.info("spotify inspection complete", extra={"provider": self.name})
        return candidate


@dataclass(frozen=True, slots=True)
class SpotdlAcquisitionProvider:
    """Production audio retrieval through the isolated SpotDL CLI subprocess.

    One canonical track URL is downloaded to a task-local output as MP3, in a
    dedicated process group so a cancel can stop it. Exit zero is not trusted:
    exactly one decodable MP3 must exist in the workspace afterwards.
    """

    executable: str = "spotdl"
    runner: SpotdlRunner = field(default=_default_spotdl_runner)
    name: str = "spotdl"

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

        argv = [
            self.executable,
            "download",
            candidate.acquisition_locator,
            "--output",
            str(workspace_path / "{track-id}.{output-ext}"),
            "--format",
            "mp3",
        ]
        try:
            result = self.runner(
                argv,
                timeout=_DOWNLOAD_TIMEOUT_SECONDS,
                cancelled=cancelled,
                env=_child_env(proxy),
            )
        except AcquisitionCancelledError:
            _clear(workspace_path)
            raise
        if result.returncode != 0:
            _clear(workspace_path)
            logger.info(
                "spotdl download failed",
                extra={"provider": self.name, "returncode": result.returncode},
            )
            raise AcquisitionFailedError(
                "Spotify audio could not be downloaded.", context={"provider": self.name}
            )

        audio_path, duration_ms = single_valid_mp3(workspace_path, provider=self.name)
        progress(100.0)
        logger.info("spotify acquisition complete", extra={"provider": self.name})
        return AudioArtifact(
            location=str(audio_path),
            duration_ms=duration_ms,
            byte_size=audio_path.stat().st_size,
        )


def _clear(workspace: Path) -> None:
    """Remove every partial file a cancelled or failed run may have left."""
    if not workspace.is_dir():
        return
    for path in workspace.iterdir():
        if path.is_file():
            path.unlink(missing_ok=True)


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
