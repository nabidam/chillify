"""ID3 tag writing, via Mutagen.

Every tag Chillify writes is written here. The download path writes text tags
onto a file that is still inside its workspace; the edit path rewrites text and
embedded cover art together onto a staged copy. Neither ever rewrites a file
that is currently part of the library — the published copy is replaced, not
edited in place, which is what makes an interrupted save recoverable.
"""

from __future__ import annotations

from pathlib import Path

from mutagen import MutagenError
from mutagen.easyid3 import EasyID3
from mutagen.id3 import APIC, ID3, ID3NoHeaderError

from chillify.domain.errors import StorageUnwritableError

# The cover-art frame a music player shows. `3` is the ID3v2 "front cover"
# picture type; anything else is filed as an extra image rather than the cover.
_FRONT_COVER_PICTURE_TYPE = 3

UNKNOWN_ALBUM_TAG = "Unknown Album"


def write_audio_tags(
    path: Path,
    *,
    title: str,
    artist: str,
    album: str | None,
    release_year: int | None,
    track_number: int | None,
) -> None:
    """Write the text tags a music player reads.

    The file is tagged in the workspace, before publication, so the copy that
    becomes part of the library is already correct and no published file is
    ever rewritten in place by this path.
    """
    try:
        tags = EasyID3(path)  # type: ignore[no-untyped-call]
    except ID3NoHeaderError:
        tags = EasyID3()  # type: ignore[no-untyped-call]

    tags["title"] = title
    tags["artist"] = artist
    tags["album"] = album or UNKNOWN_ALBUM_TAG
    if release_year is not None:
        tags["date"] = str(release_year)
    if track_number is not None:
        tags["tracknumber"] = str(track_number)

    try:
        tags.save(path)
    except (OSError, MutagenError) as exc:
        raise StorageUnwritableError("The downloaded file could not be tagged.") from exc


def write_track_tags(
    path: Path,
    *,
    title: str,
    artist: str,
    album: str | None,
    release_year: int | None,
    disc_number: int | None,
    track_number: int | None,
    artwork: Path | None,
) -> None:
    """Rewrite every text tag and the embedded cover of one staged MP3.

    The intended record is written whole rather than merged: a save carries the
    complete record, so a field the person cleared has to leave the file as
    well as the database. Absent cover art is likewise removed, not left behind
    for a player to keep showing.
    """
    write_audio_tags(
        path,
        title=title,
        artist=artist,
        album=album,
        release_year=release_year,
        track_number=track_number,
    )

    try:
        easy = EasyID3(path)  # type: ignore[no-untyped-call]
    except ID3NoHeaderError:  # pragma: no cover - the text write just created it
        easy = EasyID3()  # type: ignore[no-untyped-call]
    # EasyID3 has no disc-number-only key beyond `discnumber`, and clearing a
    # key it does not hold raises, so absence is handled explicitly.
    if disc_number is None:
        easy.pop("discnumber", None)  # type: ignore[no-untyped-call]
    else:
        easy["discnumber"] = str(disc_number)
    try:
        easy.save(path)
    except (OSError, MutagenError) as exc:
        raise StorageUnwritableError("The track's tags could not be written.") from exc

    _write_cover(path, artwork)


def _write_cover(path: Path, artwork: Path | None) -> None:
    """Replace the front-cover frame, or remove it when there is no art."""
    try:
        tags = ID3(path)  # type: ignore[no-untyped-call]
    except ID3NoHeaderError:  # pragma: no cover - the text write just created it
        tags = ID3()  # type: ignore[no-untyped-call]

    tags.delall("APIC")  # type: ignore[no-untyped-call]
    if artwork is not None:
        try:
            payload = artwork.read_bytes()
        except OSError as exc:
            raise StorageUnwritableError("The cover image could not be read.") from exc
        tags.add(  # type: ignore[no-untyped-call]
            APIC(  # type: ignore[no-untyped-call]
                encoding=3,
                mime="image/jpeg",
                type=_FRONT_COVER_PICTURE_TYPE,
                desc="Cover",
                data=payload,
            )
        )

    try:
        tags.save(path)
    except (OSError, MutagenError) as exc:
        raise StorageUnwritableError("The track's cover art could not be written.") from exc
