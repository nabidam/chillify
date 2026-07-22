"""The shared SpotDL link-inspection contract.

Every adapter that inspects a Spotify link is held to the same behaviour here,
whether it reads a recorded metadata document or invokes the isolated SpotDL
CLI. The suite is parameterized over adapter factories so the production adapter
Task 16 binds joins these same cases.

Collection rejection and metadata normalization are part of the contract: an
album, playlist, or artist link must be refused before invocation, and a single
track must normalize cleanly with its ISRC and numbering intact.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from chillify.domain.errors import ProviderResponseError, UnsupportedEntityError
from chillify.domain.protocols import LinkInspector
from chillify.infrastructure.providers.spotdl import (
    FixtureSpotdlInspector,
    candidate_from_metadata,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"

TRACK_ID = "2cGxRwrMyEAp8dEbuZaVv6"
TRACK_URL = f"https://open.spotify.com/track/{TRACK_ID}"
INTL_TRACK_URL = f"https://open.spotify.com/intl-de/track/{TRACK_ID}"
ALBUM_URL = "https://open.spotify.com/album/1DFixLWuPkv3KT3TnV35m3"
PLAYLIST_URL = "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M"
ARTIST_URL = "https://open.spotify.com/artist/4tZwfgrHOc3mvqYlEYSvVi"

INSPECTOR_FACTORIES: list[tuple[str, Callable[[Path], LinkInspector]]] = [
    ("fixture", lambda root: FixtureSpotdlInspector(fixture_root=root)),
]


@pytest.fixture
def fixture_root(disposable_root: Path) -> Path:
    root = disposable_root / "fixtures"
    shutil.copytree(FIXTURES, root)
    return root


@pytest.mark.contract
@pytest.mark.parametrize(("name", "factory"), INSPECTOR_FACTORIES)
class TestSpotdlInspectorContract:
    def test_a_track_url_is_supported(
        self, name: str, factory: Callable[[Path], LinkInspector], fixture_root: Path
    ) -> None:
        inspector = factory(fixture_root)

        assert inspector.supports(TRACK_URL)
        assert inspector.supports(INTL_TRACK_URL)

    def test_a_foreign_host_is_not_supported(
        self, name: str, factory: Callable[[Path], LinkInspector], fixture_root: Path
    ) -> None:
        assert not factory(fixture_root).supports("https://www.youtube.com/watch?v=u7K72X4eo_s")

    def test_a_supported_track_inspects_to_a_normalized_candidate(
        self, name: str, factory: Callable[[Path], LinkInspector], fixture_root: Path
    ) -> None:
        candidate = factory(fixture_root).inspect(TRACK_URL, None)

        assert candidate.provider == "spotify"
        assert candidate.title
        assert candidate.artist
        assert candidate.source_id == TRACK_ID
        assert candidate.source_url == TRACK_URL
        assert candidate.acquisition_locator == TRACK_URL
        assert candidate.isrc == "USQX91300108"
        assert candidate.duration_ms is not None and candidate.duration_ms > 0
        assert not candidate.is_playable

    @pytest.mark.parametrize("url", [ALBUM_URL, PLAYLIST_URL, ARTIST_URL])
    def test_a_collection_link_is_rejected_before_invocation(
        self,
        name: str,
        factory: Callable[[Path], LinkInspector],
        fixture_root: Path,
        url: str,
    ) -> None:
        with pytest.raises(UnsupportedEntityError):
            factory(fixture_root).inspect(url, None)


@pytest.mark.contract
class TestSpotdlWireNormalization:
    """The SpotDL metadata contract, shared by every adapter that parses it."""

    def _candidate(self, payload: object):
        return candidate_from_metadata(payload, track_id=TRACK_ID, canonical_url=TRACK_URL)

    def test_the_first_named_artist_is_used(self) -> None:
        candidate = self._candidate(
            [{"name": "Instant Crush", "artists": ["Daft Punk", "Julian Casablancas"]}]
        )

        assert candidate.artist == "Daft Punk"

    def test_more_than_one_song_is_refused(self) -> None:
        with pytest.raises(ProviderResponseError):
            self._candidate([{"name": "A", "artist": "X"}, {"name": "B", "artist": "Y"}])

    def test_an_empty_result_is_refused(self) -> None:
        with pytest.raises(ProviderResponseError):
            self._candidate([])

    def test_a_non_object_is_refused(self) -> None:
        with pytest.raises(ProviderResponseError):
            self._candidate("not a song")

    def test_an_insecure_cover_is_dropped(self) -> None:
        candidate = self._candidate(
            [{"name": "A", "artist": "X", "cover_url": "http://cdn.invalid/c.jpg"}]
        )

        assert candidate.artwork_url is None

    def test_a_malformed_isrc_is_dropped_rather_than_failing(self) -> None:
        candidate = self._candidate([{"name": "A", "artist": "X", "isrc": "nope"}])

        assert candidate.isrc is None

    def test_a_duration_is_normalized_to_milliseconds(self) -> None:
        candidate = self._candidate([{"name": "A", "artist": "X", "duration": 337.56}])

        assert candidate.duration_ms == 337_560
