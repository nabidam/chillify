"""The shared yt-dlp link-inspection contract.

Every adapter that inspects a YouTube link is held to the same behaviour here,
whether it reads a recorded `extract_info` document or calls yt-dlp. The suite
is parameterized over adapter factories so the production adapter Task 16 binds
joins these same cases instead of getting a weaker set of its own.

Recognition, bulk rejection, and normalization are all part of the contract. An
adapter that quietly accepts a playlist, or that lets a video's unreliable title
through unnormalized, is the failure this suite exists to catch.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from chillify.domain.errors import ProviderResponseError, UnsupportedEntityError
from chillify.domain.protocols import LinkInspector
from chillify.infrastructure.providers.ytdlp import FixtureYouTubeInspector, candidate_from_info

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"

VIDEO_URL = "https://www.youtube.com/watch?v=u7K72X4eo_s"
SHORT_URL = "https://youtu.be/u7K72X4eo_s"
VIDEO_IN_PLAYLIST = "https://www.youtube.com/watch?v=u7K72X4eo_s&list=PL1234567890"
PLAYLIST_URL = "https://www.youtube.com/playlist?list=PL1234567890"
CHANNEL_URL = "https://www.youtube.com/@massiveattack"

# Adapter factories under the shared suite. The production adapter is bound in
# Task 16 and is appended here, against these same cases.
INSPECTOR_FACTORIES: list[tuple[str, Callable[[Path], LinkInspector]]] = [
    ("fixture", lambda root: FixtureYouTubeInspector(fixture_root=root)),
]


@pytest.fixture
def fixture_root(disposable_root: Path) -> Path:
    root = disposable_root / "fixtures"
    shutil.copytree(FIXTURES, root)
    return root


@pytest.mark.contract
@pytest.mark.parametrize(("name", "factory"), INSPECTOR_FACTORIES)
class TestYouTubeInspectorContract:
    def test_a_video_url_is_supported(
        self, name: str, factory: Callable[[Path], LinkInspector], fixture_root: Path
    ) -> None:
        inspector = factory(fixture_root)

        assert inspector.supports(VIDEO_URL)
        assert inspector.supports(SHORT_URL)
        assert inspector.supports(VIDEO_IN_PLAYLIST)

    def test_a_foreign_host_is_not_supported(
        self, name: str, factory: Callable[[Path], LinkInspector], fixture_root: Path
    ) -> None:
        assert not factory(fixture_root).supports("https://open.spotify.com/track/x")

    def test_a_supported_video_inspects_to_a_normalized_candidate(
        self, name: str, factory: Callable[[Path], LinkInspector], fixture_root: Path
    ) -> None:
        candidate = factory(fixture_root).inspect(VIDEO_URL, None)

        assert candidate.provider == "youtube"
        assert candidate.title
        assert candidate.artist
        assert candidate.source_id == "u7K72X4eo_s"
        assert candidate.source_url == VIDEO_URL
        # A YouTube video is its own acquisition target; there is no search.
        assert candidate.acquisition_locator == VIDEO_URL
        assert not candidate.is_playable

    def test_a_video_reached_inside_a_playlist_is_the_video(
        self, name: str, factory: Callable[[Path], LinkInspector], fixture_root: Path
    ) -> None:
        """`noplaylist`: `watch?v=X&list=Y` is video X, not the playlist."""
        candidate = factory(fixture_root).inspect(VIDEO_IN_PLAYLIST, None)

        assert candidate.source_id == "u7K72X4eo_s"

    def test_a_playlist_link_is_rejected_before_any_inspection(
        self, name: str, factory: Callable[[Path], LinkInspector], fixture_root: Path
    ) -> None:
        with pytest.raises(UnsupportedEntityError):
            factory(fixture_root).inspect(PLAYLIST_URL, None)

    def test_a_channel_link_is_rejected(
        self, name: str, factory: Callable[[Path], LinkInspector], fixture_root: Path
    ) -> None:
        with pytest.raises(UnsupportedEntityError):
            factory(fixture_root).inspect(CHANNEL_URL, None)


@pytest.mark.contract
class TestYouTubeWireNormalization:
    """The `extract_info` contract, shared by every adapter that parses it."""

    def _candidate(self, info: object):
        return candidate_from_info(info, video_id="u7K72X4eo_s", canonical_url=VIDEO_URL)

    def test_music_track_fields_are_preferred_over_the_raw_title(self) -> None:
        candidate = self._candidate(
            {
                "title": "Massive Attack - Teardrop (Official Video)",
                "track": "Teardrop",
                "artist": "Massive Attack",
            }
        )

        assert candidate.title == "Teardrop"
        assert candidate.artist == "Massive Attack"

    def test_the_uploader_stands_in_for_a_missing_artist(self) -> None:
        candidate = self._candidate({"title": "Teardrop", "uploader": "Massive Attack"})

        assert candidate.artist == "Massive Attack"

    def test_a_playlist_document_is_refused(self) -> None:
        with pytest.raises(ProviderResponseError):
            self._candidate({"_type": "playlist", "entries": []})

    def test_a_non_object_is_refused(self) -> None:
        with pytest.raises(ProviderResponseError):
            self._candidate(["not", "an", "object"])

    def test_a_document_without_a_title_is_refused(self) -> None:
        with pytest.raises(ProviderResponseError):
            self._candidate({"uploader": "Nobody"})

    def test_an_insecure_thumbnail_is_dropped(self) -> None:
        candidate = self._candidate(
            {
                "title": "Teardrop",
                "uploader": "Massive Attack",
                "thumbnail": "http://x.invalid/t.jpg",
            }
        )

        assert candidate.artwork_url is None

    def test_a_duration_is_normalized_to_milliseconds(self) -> None:
        candidate = self._candidate(
            {"title": "Teardrop", "uploader": "Massive Attack", "duration": 331}
        )

        assert candidate.duration_ms == 331_000
