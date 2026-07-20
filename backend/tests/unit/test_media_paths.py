"""Containment of stored relative paths inside the managed music root."""

from __future__ import annotations

from pathlib import Path

import pytest

from chillify.domain.errors import UnsafeMediaPathError
from chillify.infrastructure.media.storage import resolve_managed_path

pytestmark = pytest.mark.unit


@pytest.fixture
def music_root(disposable_root: Path) -> Path:
    root = disposable_root / "music"
    (root / "Music" / "Artist" / "Album").mkdir(parents=True)
    return root


class TestContainedPaths:
    def test_a_managed_relative_path_resolves_beneath_the_root(self, music_root: Path) -> None:
        resolved = resolve_managed_path(music_root, "Music/Artist/Album/01 - Title.mp3")

        assert resolved == music_root.resolve() / "Music/Artist/Album/01 - Title.mp3"

    def test_resolution_does_not_require_the_file_to_exist_yet(self, music_root: Path) -> None:
        assert resolve_managed_path(music_root, "Artwork/track.jpg").name == "track.jpg"


class TestRefusedPaths:
    @pytest.mark.parametrize(
        "relative_path",
        [
            "",
            " Music/x.mp3",
            "/etc/passwd",
            "../../etc/passwd",
            "Music/../../escape.mp3",
            "Music/./x.mp3",
            "Music/x\x00.mp3",
            "Music/CON.mp3",
            "Music/lpt1.txt",
        ],
    )
    def test_a_path_that_leaves_or_abuses_the_root_is_refused(
        self, music_root: Path, relative_path: str
    ) -> None:
        with pytest.raises(UnsafeMediaPathError):
            resolve_managed_path(music_root, relative_path)

    def test_a_symlink_pointing_outside_the_root_is_refused(
        self, music_root: Path, disposable_root: Path
    ) -> None:
        outside = disposable_root / "outside"
        outside.mkdir()
        (outside / "secret.mp3").write_bytes(b"nope")
        (music_root / "Music" / "escape").symlink_to(outside)

        with pytest.raises(UnsafeMediaPathError):
            resolve_managed_path(music_root, "Music/escape/secret.mp3")

    def test_the_refusal_message_never_echoes_the_offending_path(self, music_root: Path) -> None:
        with pytest.raises(UnsafeMediaPathError) as caught:
            resolve_managed_path(music_root, "../../etc/passwd")

        assert "passwd" not in str(caught.value)
        assert caught.value.context == {}
