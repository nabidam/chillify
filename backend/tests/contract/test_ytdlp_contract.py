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

import json
import shutil
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from chillify.domain.errors import (
    AcquisitionCancelledError,
    AcquisitionFailedError,
    ProviderResponseError,
    UnsupportedEntityError,
)
from chillify.domain.protocols import LinkInspector, TrackCandidate
from chillify.infrastructure.providers.ytdlp import (
    FixtureYouTubeInspector,
    YouTubeInspector,
    YtDlpAcquisitionProvider,
    candidate_from_info,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
GATE_TONE = FIXTURES / "media" / "gate-tone.mp3"

VIDEO_URL = "https://www.youtube.com/watch?v=u7K72X4eo_s"
SHORT_URL = "https://youtu.be/u7K72X4eo_s"
VIDEO_IN_PLAYLIST = "https://www.youtube.com/watch?v=u7K72X4eo_s&list=PL1234567890"
PLAYLIST_URL = "https://www.youtube.com/playlist?list=PL1234567890"
CHANNEL_URL = "https://www.youtube.com/@massiveattack"


def _recorded_inspect_factory(root: Path) -> YouTubeInspector:
    """A production inspector whose yt-dlp handle returns the recorded document.

    The production adapter reads the same sanitized `extract_info` fixture the
    gate inspector does, so both are held to the identical inspection contract
    without contacting YouTube.
    """
    info = json.loads((root / "providers" / "ytdlp_inspect.json").read_text(encoding="utf-8"))

    @contextmanager
    def ydl_factory(_options: dict[str, Any]) -> Iterator[object]:
        class _Ydl:
            def extract_info(self, url: str, *, download: bool) -> object:
                return info

        yield _Ydl()

    return YouTubeInspector(ydl_factory=ydl_factory)


# Adapter factories under the shared inspection suite: the production adapter
# joins the fixture adapter against these same cases.
INSPECTOR_FACTORIES: list[tuple[str, Callable[[Path], LinkInspector]]] = [
    ("fixture", lambda root: FixtureYouTubeInspector(fixture_root=root)),
    ("production", _recorded_inspect_factory),
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


def _youtube_candidate() -> TrackCandidate:
    """A direct YouTube candidate: its own video is the acquisition target."""
    return TrackCandidate(
        provider="youtube",
        source_id="u7K72X4eo_s",
        source_url=VIDEO_URL,
        title="Teardrop",
        artist="Massive Attack",
        album=None,
        release_year=None,
        disc_number=None,
        track_number=None,
        duration_ms=None,
        isrc=None,
        artwork_url=None,
        acquisition_locator=VIDEO_URL,
        raw_fingerprint=None,
    )


def _deezer_candidate(duration_ms: int | None) -> TrackCandidate:
    """A Deezer candidate acquired via `ytsearch1:`; its match is verified."""
    return TrackCandidate(
        provider="deezer",
        source_id="3135556",
        source_url="https://www.deezer.com/track/3135556",
        title="Harder Better Faster Stronger",
        artist="Daft Punk",
        album="Discovery",
        release_year=None,
        disc_number=None,
        track_number=None,
        duration_ms=duration_ms,
        isrc=None,
        artwork_url=None,
        acquisition_locator="ytsearch1:Daft Punk Harder Better Faster Stronger",
        raw_fingerprint=None,
    )


_DOWNLOADING_STEPS = (
    {"status": "downloading", "downloaded_bytes": 25, "total_bytes": 100},
    {"status": "downloading", "downloaded_bytes": 50, "total_bytes": 100},
    {"status": "downloading", "downloaded_bytes": 100, "total_bytes": 100},
)


def _acquisition(
    *,
    produce_mp3: bool = True,
    steps: tuple[dict[str, Any], ...] = _DOWNLOADING_STEPS,
    info: dict[str, Any] | None = None,
) -> YtDlpAcquisitionProvider:
    """A production acquisition adapter whose yt-dlp handle is a recorded double.

    The double drives the real progress hooks, then copies the sanitized tone
    into the task workspace exactly as a finished download would leave one MP3.
    """

    @contextmanager
    def ydl_factory(options: dict[str, Any]) -> Iterator[object]:
        out_dir = Path(options["outtmpl"]["default"]).parent

        class _Ydl:
            def extract_info(self, url: str, *, download: bool) -> object:
                for step in steps:
                    for hook in options.get("progress_hooks", []):
                        hook(step)
                if produce_mp3:
                    shutil.copyfile(GATE_TONE, out_dir / "acquired.mp3")
                return info if info is not None else {"entries": [{"title": "x", "uploader": "y"}]}

        yield _Ydl()

    return YtDlpAcquisitionProvider(ydl_factory=ydl_factory)


@pytest.mark.contract
class TestYtDlpAcquisitionContract:
    def test_a_direct_video_yields_one_valid_mp3(self, tmp_path: Path) -> None:
        artifact = _acquisition().acquire(
            _youtube_candidate(), str(tmp_path), None, lambda _p: None, lambda: False
        )

        acquired = Path(artifact.location)
        assert acquired.is_file()
        assert acquired.parent == tmp_path
        assert artifact.byte_size > 0
        assert artifact.duration_ms is not None and artifact.duration_ms > 0

    def test_progress_is_reported_monotonically_and_never_invented(self, tmp_path: Path) -> None:
        reported: list[float | None] = []
        _acquisition().acquire(
            _youtube_candidate(), str(tmp_path), None, reported.append, lambda: False
        )

        known = [value for value in reported if value is not None]
        assert known == sorted(known)
        assert all(0.0 <= value <= 100.0 for value in known)

    def test_a_cancellation_before_work_leaves_the_workspace_empty(self, tmp_path: Path) -> None:
        with pytest.raises(AcquisitionCancelledError):
            _acquisition().acquire(
                _youtube_candidate(), str(tmp_path), None, lambda _p: None, lambda: True
            )

        assert list(tmp_path.iterdir()) == []

    def test_a_cancellation_during_download_stops_and_cleans_up(self, tmp_path: Path) -> None:
        checks = iter([False, True, True, True, True])

        with pytest.raises(AcquisitionCancelledError):
            _acquisition().acquire(
                _youtube_candidate(),
                str(tmp_path),
                None,
                lambda _p: None,
                lambda: next(checks, True),
            )

        assert list(tmp_path.iterdir()) == []

    def test_a_search_match_that_runs_too_long_is_refused(self, tmp_path: Path) -> None:
        """A `ytsearch1:` result whose duration disagrees is never accepted."""
        info = {"entries": [{"title": "Harder Better Faster Stronger", "uploader": "Daft Punk"}]}
        with pytest.raises(AcquisitionFailedError):
            _acquisition(info=info).acquire(
                _deezer_candidate(224_000), str(tmp_path), None, lambda _p: None, lambda: False
            )

        assert list(tmp_path.iterdir()) == []

    def test_a_search_result_with_a_foreign_title_is_refused(self, tmp_path: Path) -> None:
        info = {"entries": [{"title": "Something Entirely Different", "uploader": "Nobody"}]}
        with pytest.raises(AcquisitionFailedError):
            _acquisition(info=info).acquire(
                _deezer_candidate(None), str(tmp_path), None, lambda _p: None, lambda: False
            )

    def test_a_download_that_produces_no_mp3_fails(self, tmp_path: Path) -> None:
        with pytest.raises(AcquisitionFailedError):
            _acquisition(produce_mp3=False).acquire(
                _youtube_candidate(), str(tmp_path), None, lambda _p: None, lambda: False
            )
