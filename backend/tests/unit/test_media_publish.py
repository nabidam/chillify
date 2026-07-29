"""Managed layout, publication, and tagging of one acquired file."""

from __future__ import annotations

from pathlib import Path

import pytest
from mutagen.easyid3 import EasyID3

from chillify.infrastructure.media.storage import (
    job_workspace,
    organized_relpath,
    publish_audio,
    remove_workspace,
)
from chillify.infrastructure.media.tags import write_audio_tags

FIXTURE_AUDIO = Path(__file__).resolve().parents[1] / "fixtures" / "media" / "gate-tone.mp3"


class TestOrganizedRelpath:
    @pytest.mark.unit
    def test_a_track_lands_under_artist_and_album_with_a_two_digit_prefix(self) -> None:
        relative = organized_relpath(
            artist="Daft Punk", album="Discovery", title="Aerodynamic", track_number=3
        )

        assert relative == "Music/Daft Punk/Discovery/03 - Aerodynamic.mp3"

    @pytest.mark.unit
    def test_a_track_number_above_ninety_nine_keeps_its_full_number(self) -> None:
        relative = organized_relpath(
            artist="Various", album="Long Set", title="Encore", track_number=104
        )

        assert relative.endswith("104 - Encore.mp3")

    @pytest.mark.unit
    def test_an_absent_album_uses_the_deterministic_unknown_context(self) -> None:
        relative = organized_relpath(
            artist="Daft Punk", album=None, title="Aerodynamic", track_number=None
        )

        assert relative == "Music/Daft Punk/Unknown Album/Aerodynamic.mp3"

    @pytest.mark.unit
    def test_a_separator_in_metadata_stays_one_path_component(self) -> None:
        relative = organized_relpath(
            artist="AC/DC", album="Back in Black", title="Hells Bells", track_number=1
        )

        assert relative == "Music/AC DC/Back in Black/01 - Hells Bells.mp3"

    @pytest.mark.unit
    def test_traversal_in_metadata_cannot_climb_out_of_the_library(self) -> None:
        relative = organized_relpath(
            artist="../../etc", album="../..", title="../passwd", track_number=None
        )

        assert ".." not in relative
        assert relative.startswith("Music/")


@pytest.mark.integration
class TestPublication:
    def test_a_published_file_is_moved_into_the_library(self, disposable_root: Path) -> None:
        music_root = disposable_root / "music"
        music_root.mkdir()
        workspace = job_workspace(music_root, "job-1")
        acquired = workspace / "acquired.mp3"
        acquired.write_bytes(FIXTURE_AUDIO.read_bytes())

        published = publish_audio(music_root, acquired, "Music/Artist/Album/01 - Song.mp3")

        assert (music_root / published.relative_path).is_file()
        assert not acquired.exists()
        assert published.size_bytes == FIXTURE_AUDIO.stat().st_size
        assert len(published.content_sha256) == 64

    def test_republishing_the_identical_file_reuses_the_existing_managed_file(
        self, disposable_root: Path
    ) -> None:
        music_root = disposable_root / "music"
        music_root.mkdir()
        relative = "Music/Artist/Album/01 - Song.mp3"
        first = job_workspace(music_root, "job-1") / "acquired.mp3"
        first.write_bytes(FIXTURE_AUDIO.read_bytes())
        first_published = publish_audio(music_root, first, relative)

        second = job_workspace(music_root, "job-2") / "acquired.mp3"
        second.write_bytes(FIXTURE_AUDIO.read_bytes())

        reused = publish_audio(music_root, second, relative)

        assert reused.relative_path == first_published.relative_path
        assert reused.content_sha256 == first_published.content_sha256
        assert reused.reused_existing_file is True
        assert second.is_file(), "the caller still owns the workspace copy"

    def test_a_different_file_with_the_same_name_never_overwrites(
        self, disposable_root: Path
    ) -> None:
        music_root = disposable_root / "music"
        music_root.mkdir()
        relative = "Music/Artist/Album/01 - Song.mp3"
        first = job_workspace(music_root, "job-1") / "acquired.mp3"
        first.write_bytes(FIXTURE_AUDIO.read_bytes())
        original = publish_audio(music_root, first, relative)

        second = job_workspace(music_root, "job-2") / "acquired.mp3"
        second.write_bytes(FIXTURE_AUDIO.read_bytes() + b"\x00")
        collided = publish_audio(music_root, second, relative)

        assert collided.relative_path != original.relative_path
        assert (music_root / original.relative_path).is_file()
        assert (music_root / collided.relative_path).is_file()

    def test_a_removed_workspace_takes_its_partial_files_with_it(
        self, disposable_root: Path
    ) -> None:
        music_root = disposable_root / "music"
        music_root.mkdir()
        workspace = job_workspace(music_root, "job-1")
        (workspace / "partial.mp3").write_bytes(b"partial")

        remove_workspace(workspace)

        assert not workspace.exists()

    def test_tags_are_written_before_the_file_is_published(self, disposable_root: Path) -> None:
        music_root = disposable_root / "music"
        music_root.mkdir()
        acquired = job_workspace(music_root, "job-1") / "acquired.mp3"
        acquired.write_bytes(FIXTURE_AUDIO.read_bytes())

        write_audio_tags(
            acquired,
            title="Aerodynamic",
            artist="Daft Punk",
            album="Discovery",
            release_year=2001,
            track_number=3,
        )
        published = publish_audio(music_root, acquired, "Music/D/Discovery/03 - Aerodynamic.mp3")

        tags = EasyID3(music_root / published.relative_path)
        assert tags["title"] == ["Aerodynamic"]
        assert tags["artist"] == ["Daft Punk"]
        assert tags["album"] == ["Discovery"]
