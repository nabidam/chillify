"""The filesystem mechanics one recoverable edit is built from.

These are the pieces that decide whether an interrupted save leaves a person
with their old track, their new track, or neither. The last outcome is the one
every assertion here exists to rule out.
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from chillify.domain.errors import MutationLockedError
from chillify.infrastructure.media import mutations

pytestmark = pytest.mark.unit


@pytest.fixture
def music_root(disposable_root: Path) -> Path:
    root = disposable_root / "music"
    root.mkdir()
    return root


def _write(music_root: Path, relative: str, payload: bytes) -> Path:
    path = music_root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


class TestUnusedRelpath:
    def test_a_free_location_is_used_as_is(self, music_root: Path) -> None:
        assert (
            mutations.unused_relpath(music_root, "Music/A/B/01 - Song.mp3")
            == "Music/A/B/01 - Song.mp3"
        )

    def test_the_track_s_own_current_path_does_not_count_as_occupied(
        self, music_root: Path
    ) -> None:
        _write(music_root, "Music/A/B/01 - Song.mp3", b"audio")

        resolved = mutations.unused_relpath(
            music_root, "Music/A/B/01 - Song.mp3", keeping="Music/A/B/01 - Song.mp3"
        )

        assert resolved == "Music/A/B/01 - Song.mp3"

    def test_another_track_s_path_is_stepped_around_rather_than_overwritten(
        self, music_root: Path
    ) -> None:
        _write(music_root, "Music/A/B/01 - Song.mp3", b"somebody else")

        resolved = mutations.unused_relpath(
            music_root, "Music/A/B/01 - Song.mp3", keeping="Music/A/B/09 - Other.mp3"
        )

        assert resolved == "Music/A/B/01 - Song (2).mp3"
        assert (music_root / "Music/A/B/01 - Song.mp3").read_bytes() == b"somebody else"


class TestRecovery:
    def test_a_live_file_is_snapshotted_without_being_moved(self, music_root: Path) -> None:
        _write(music_root, "Music/A/B/song.mp3", b"original")

        links = mutations.preserve_recovery(
            music_root, mutation_id="m1", relpaths=["Music/A/B/song.mp3"]
        )

        assert (music_root / "Music/A/B/song.mp3").read_bytes() == b"original"
        assert Path(links["Music/A/B/song.mp3"]).read_bytes() == b"original"

    def test_an_absent_file_is_skipped_rather_than_failing_the_change(
        self, music_root: Path
    ) -> None:
        links = mutations.preserve_recovery(
            music_root, mutation_id="m1", relpaths=["Music/A/B/gone.mp3"]
        )

        assert links == {}

    def test_restoring_puts_the_previous_bytes_back_after_a_placement(
        self, music_root: Path
    ) -> None:
        """The recovery link survives because placement replaces, never rewrites.

        A hard link shares its inode, so an in-place rewrite of the live file
        would change the snapshot too. That is precisely why the edit path only
        ever moves a staged file over the old one: the rename gives the new
        version its own inode and leaves the snapshot pointing at the old bytes.
        """
        _write(music_root, "Music/A/B/song.mp3", b"original")
        links = mutations.preserve_recovery(
            music_root, mutation_id="m1", relpaths=["Music/A/B/song.mp3"]
        )
        staged = mutations.stage_bytes(
            music_root, mutation_id="m1", name="audio.mp3", payload=b"replaced"
        )
        mutations.place(
            music_root,
            mutations.StagedFile(staged_path=staged, intended_relpath="Music/A/B/song.mp3"),
        )
        assert (music_root / "Music/A/B/song.mp3").read_bytes() == b"replaced"

        mutations.restore_recovery(music_root, links)

        assert (music_root / "Music/A/B/song.mp3").read_bytes() == b"original"

    def test_restoring_recreates_a_path_whose_directory_was_emptied(self, music_root: Path) -> None:
        _write(music_root, "Music/A/B/song.mp3", b"original")
        links = mutations.preserve_recovery(
            music_root, mutation_id="m1", relpaths=["Music/A/B/song.mp3"]
        )
        (music_root / "Music/A/B/song.mp3").unlink()
        (music_root / "Music/A/B").rmdir()

        mutations.restore_recovery(music_root, links)

        assert (music_root / "Music/A/B/song.mp3").read_bytes() == b"original"


class TestPlacement:
    def test_a_staged_file_is_moved_atomically_into_the_library(self, music_root: Path) -> None:
        staged = mutations.stage_bytes(
            music_root, mutation_id="m1", name="audio.mp3", payload=b"edited"
        )

        mutations.place(
            music_root,
            mutations.StagedFile(staged_path=staged, intended_relpath="Music/A/B/01 - Song.mp3"),
        )

        assert (music_root / "Music/A/B/01 - Song.mp3").read_bytes() == b"edited"
        assert not staged.exists()

    def test_a_digest_describes_the_bytes_that_are_about_to_be_placed(
        self, music_root: Path
    ) -> None:
        staged = mutations.stage_bytes(
            music_root, mutation_id="m1", name="audio.mp3", payload=b"edited"
        )

        digest, size = mutations.file_digest(staged)

        assert size == len(b"edited")
        assert len(digest) == 64

    def test_pruning_removes_only_the_directories_a_move_emptied(self, music_root: Path) -> None:
        _write(music_root, "Music/Old/Album/song.mp3", b"audio")
        _write(music_root, "Music/Old/Kept/other.mp3", b"audio")
        (music_root / "Music/Old/Album/song.mp3").unlink()

        mutations.prune_empty_parents(music_root, ["Music/Old/Album/song.mp3"])

        assert not (music_root / "Music/Old/Album").exists()
        assert (music_root / "Music/Old/Kept/other.mp3").is_file()


class TestLocks:
    def test_a_second_writer_waiting_past_the_bound_is_told_the_track_is_busy(
        self, music_root: Path
    ) -> None:
        holding = threading.Event()
        release = threading.Event()

        def hold() -> None:
            with mutations.media_locks(music_root, track_id="track-1"):
                holding.set()
                release.wait(timeout=5)

        holder = threading.Thread(target=hold)
        holder.start()
        try:
            assert holding.wait(timeout=5)
            with (
                pytest.raises(MutationLockedError) as failure,
                mutations.media_locks(music_root, track_id="track-1", timeout=0.1),
            ):
                pass
        finally:
            release.set()
            holder.join(timeout=5)

        assert failure.value.status_code == 423
        assert failure.value.retryable is True

    def test_a_released_lock_is_available_to_the_next_change(self, music_root: Path) -> None:
        with mutations.media_locks(music_root, track_id="track-1"):
            pass

        with mutations.media_locks(music_root, track_id="track-1", timeout=0.1):
            pass
