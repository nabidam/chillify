"""Fixture data for a disposable gate environment.

A demo gate walks a journey, and a journey needs something to walk over. This
module puts one profile and a couple of playable tracks into a gate database so
the walkthrough starts on a screen with content rather than on an empty state
that proves nothing.

It refuses to run anywhere but a gate environment. That refusal is the point:
seeding is the one operation that writes invented data, and household data is
exactly what it must never reach.
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import shutil
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import text

from chillify.composition import Composition, build_composition
from chillify.config import ConfigurationError, load_settings
from chillify.domain.models import ProfileId, normalize_metadata, to_rfc3339
from chillify.infrastructure.db.repositories import ProfileRepository, new_id
from chillify.infrastructure.media.storage import organized_relpath, resolve_managed_path
from chillify.infrastructure.media.tags import write_audio_tags

logger = logging.getLogger(__name__)

SEED_PROFILE_NAME = "Household"


@dataclass(frozen=True, slots=True)
class SeedTrack:
    """One track the gate journey can find, play, correct, and add to a playlist."""

    title: str
    artist: str
    album: str
    release_year: int
    track_number: int


SEED_TRACKS = (
    SeedTrack(
        title="Harder Better Faster Stronger",
        artist="Daft Punk",
        album="Discovery",
        release_year=2001,
        track_number=5,
    ),
    SeedTrack(
        title="Digital Love",
        artist="Daft Punk",
        album="Discovery",
        release_year=2001,
        track_number=4,
    ),
)


def seed(*, fixture_audio: Path) -> int:
    """Write the seed profile and tracks into the configured gate environment.

    Returns the number of tracks inserted. Running twice is not an error: rows
    that already exist are left alone, so re-seeding a prepared environment is
    safe.
    """
    settings = load_settings()
    if not settings.is_gate:
        raise ConfigurationError(
            "gate_seed_outside_gate",
            "Seeding is only possible in a gate environment.",
        )
    if not fixture_audio.is_file():
        raise ConfigurationError(
            "gate_seed_fixture_missing",
            "The fixture audio file to seed from does not exist.",
        )

    composition = build_composition(settings)
    try:
        profile_id = _ensure_profile(composition)
        inserted = sum(
            1
            for track in SEED_TRACKS
            if _insert_track(composition, track, fixture_audio=fixture_audio)
        )
    finally:
        composition.dispose()

    logger.info(
        "gate environment seeded",
        extra={"profile_id": str(profile_id), "tracks": inserted},
    )
    return inserted


def _ensure_profile(composition: Composition) -> ProfileId:
    """The seed profile, created only if the gate database has none by that name."""
    with composition.session_factory() as session:
        profiles = ProfileRepository(session)
        for profile in profiles.list_profiles():
            if profile.name == SEED_PROFILE_NAME:
                return profile.id
        created = profiles.create(SEED_PROFILE_NAME)
        session.commit()
        return created.id


def _insert_track(composition: Composition, track: SeedTrack, *, fixture_audio: Path) -> bool:
    """Publish one seeded track, or report that it is already present.

    The file is copied and tagged before its row is written, in the same order
    the worker publishes a real download, so a seeded track is indistinguishable
    from a downloaded one to every screen that reads it.
    """
    music_root = composition.settings.music_root
    relative = organized_relpath(
        artist=track.artist,
        album=track.album,
        title=track.title,
        track_number=track.track_number,
    )
    target = resolve_managed_path(music_root, relative)

    with composition.session_factory() as session:
        already_present = session.execute(
            text("SELECT id FROM tracks WHERE file_relpath = :relpath"),
            {"relpath": relative},
        ).first()
        if already_present is not None:
            return False

        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(fixture_audio, target)
        write_audio_tags(
            target,
            title=track.title,
            artist=track.artist,
            album=track.album,
            release_year=track.release_year,
            track_number=track.track_number,
        )

        payload = target.read_bytes()
        normalized = normalize_metadata(artist=track.artist, title=track.title, album=track.album)
        moment = to_rfc3339(datetime.now(UTC))
        session.execute(
            text(
                "INSERT INTO tracks (id, title, artist, album, release_year, disc_number,"
                " track_number, duration_ms, normalized_artist, normalized_title,"
                " normalized_album, file_relpath, mime_type, file_size_bytes, content_sha256,"
                " availability, revision, created_at, updated_at)"
                " VALUES (:id, :title, :artist, :album, :year, 1, :number, NULL,"
                " :normalized_artist, :normalized_title, :normalized_album, :relpath,"
                " 'audio/mpeg', :size, :digest, 'available', 1, :moment, :moment)"
            ),
            {
                "id": new_id(),
                "title": track.title,
                "artist": track.artist,
                "album": track.album,
                "year": track.release_year,
                "number": track.track_number,
                "normalized_artist": normalized.normalized_artist,
                "normalized_title": normalized.normalized_title,
                "normalized_album": normalized.normalized_album,
                "relpath": relative,
                "size": len(payload),
                "digest": hashlib.sha256(payload).hexdigest(),
                "moment": moment,
            },
        )
        session.commit()
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed a disposable gate environment.")
    parser.add_argument(
        "--fixture-audio",
        type=Path,
        required=True,
        help="Path to the decodable MP3 every seeded track is copied from.",
    )
    arguments = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)
    try:
        inserted = seed(fixture_audio=arguments.fixture_audio)
    except ConfigurationError as failure:
        logger.error("seed refused", extra={"error_code": failure.code})
        return 2
    logger.info("seed complete", extra={"tracks": inserted})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
