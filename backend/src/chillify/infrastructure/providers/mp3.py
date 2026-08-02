"""Shared acquisition-output validation.

Both audio adapters — yt-dlp and the SpotDL subprocess — must prove the same
thing before they hand an artifact back: exactly one decodable MP3 exists in the
task workspace. Exit zero, or a finished download hook, is never enough. This
lives in one place so the two adapters cannot disagree about what "one valid
MP3" means, the same reason the wire parsers are shared.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from mutagen import File as MutagenFile
from mutagen import MutagenError
from mutagen.mp3 import MP3, HeaderNotFoundError

from chillify.domain.errors import AcquisitionFailedError


def mp3_duration_ms(audio_path: Path, *, provider: str) -> int:
    """Prove one named file is a decodable MP3 and return its duration."""
    try:
        audio = MP3(audio_path)  # type: ignore[no-untyped-call]
    except (OSError, MutagenError, HeaderNotFoundError) as exc:
        raise AcquisitionFailedError(
            "The downloaded file is not a valid MP3.",
            context={"provider": provider},
        ) from exc
    length = getattr(audio.info, "length", 0.0)
    if not length or length <= 0:
        raise AcquisitionFailedError(
            "The downloaded MP3 has no decodable audio.",
            context={"provider": provider},
        )
    return round(length * 1000)


def media_needs_conversion(source: Path) -> bool:
    """Whether Mutagen recognizes a non-MP3 audio container at ``source``."""
    try:
        return MutagenFile(source) is not None
    except OSError, MutagenError:
        return False


def convert_to_mp3(source: Path, target: Path, *, provider: str) -> tuple[Path, int]:
    """Convert a recognized audio container without exposing tool output."""
    try:
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", str(source), "-vn", "-codec:a", "libmp3lame", str(target)],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as exc:
        raise AcquisitionFailedError(
            "The downloaded audio could not be converted.", context={"provider": provider}
        ) from exc
    if result.returncode != 0:
        raise AcquisitionFailedError(
            "The downloaded audio could not be converted.", context={"provider": provider}
        )
    return target, mp3_duration_ms(target, provider=provider)


def single_valid_mp3(workspace: Path, *, provider: str) -> tuple[Path, int]:
    """Return the one MP3 in `workspace` and its duration in milliseconds.

    Raises `AcquisitionFailedError` when the workspace holds anything other than
    exactly one file that Mutagen can decode as an MP3 with a positive length.
    """
    candidates = sorted(
        path for path in workspace.iterdir() if path.is_file() and path.suffix.lower() == ".mp3"
    )
    if len(candidates) != 1:
        raise AcquisitionFailedError(
            "The download did not produce exactly one audio file.",
            context={"provider": provider, "count": len(candidates)},
        )
    audio_path = candidates[0]
    return audio_path, mp3_duration_ms(audio_path, provider=provider)
