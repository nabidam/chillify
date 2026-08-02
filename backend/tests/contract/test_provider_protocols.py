"""The shared provider protocol suite.

Every adapter that claims a capability is held to the same behaviour here,
whether it talks to Deezer or reads a recorded payload. The suite is
parameterized over adapter factories rather than written twice: when Task 16
binds the production adapters, they join these same cases instead of getting a
second, weaker set of their own.

Rejected wire inputs are part of the contract, not an edge case. An adapter
that quietly accepts a malformed payload is the failure this suite exists to
catch.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from chillify.domain.errors import AcquisitionCancelledError, ProviderResponseError
from chillify.domain.protocols import (
    AcquisitionProvider,
    DiscoveryProvider,
    TrackCandidate,
)
from chillify.infrastructure.providers.deezer_wire import candidates_from_search
from chillify.infrastructure.providers.fixtures import (
    FixtureAcquisitionProvider,
    FixtureDiscoveryProvider,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"

# Adapter factories under the shared suite. Production adapters are bound in
# Task 16 and are appended here, against these same cases.
DISCOVERY_FACTORIES: list[tuple[str, Callable[[Path], DiscoveryProvider]]] = [
    ("fixture", lambda root: FixtureDiscoveryProvider(fixture_root=root)),
]
ACQUISITION_FACTORIES: list[tuple[str, Callable[[Path], AcquisitionProvider]]] = [
    ("fixture", lambda root: FixtureAcquisitionProvider(fixture_root=root)),
]


@pytest.fixture
def fixture_root(disposable_root: Path) -> Path:
    root = disposable_root / "fixtures"
    shutil.copytree(FIXTURES, root)
    return root


def a_candidate(**overrides: Any) -> TrackCandidate:
    defaults: dict[str, Any] = {
        "provider": "deezer",
        "source_id": "3135556",
        "source_url": "https://www.deezer.com/track/3135556",
        "title": "Harder Better Faster Stronger",
        "artist": "Daft Punk",
        "album": "Discovery",
        "release_year": None,
        "disc_number": None,
        "track_number": None,
        "duration_ms": 224000,
        "isrc": "GBDUW0000059",
        "artwork_url": None,
        "acquisition_locator": "ytsearch1:Daft Punk Harder Better Faster Stronger",
        "raw_fingerprint": None,
    }
    return TrackCandidate(**{**defaults, **overrides})


@pytest.mark.contract
@pytest.mark.parametrize(("name", "factory"), DISCOVERY_FACTORIES)
class TestDiscoveryProviderContract:
    def test_a_match_is_returned_as_a_normalized_candidate(
        self, name: str, factory: Callable[[Path], DiscoveryProvider], fixture_root: Path
    ) -> None:
        results = factory(fixture_root).search("daft punk", 10, None)

        assert results
        first = results[0]
        assert first.provider == "deezer"
        assert first.title
        assert first.artist
        assert first.acquisition_locator

    def test_every_candidate_is_unplayable(
        self, name: str, factory: Callable[[Path], DiscoveryProvider], fixture_root: Path
    ) -> None:
        """A remote result has no local file, so no screen may offer Play."""
        results = factory(fixture_root).search("daft punk", 10, None)

        assert all(not candidate.is_playable for candidate in results)

    def test_the_requested_limit_is_honoured(
        self, name: str, factory: Callable[[Path], DiscoveryProvider], fixture_root: Path
    ) -> None:
        results = factory(fixture_root).search("a", 1, None)

        assert len(results) <= 1

    def test_a_query_with_no_match_returns_nothing_rather_than_failing(
        self, name: str, factory: Callable[[Path], DiscoveryProvider], fixture_root: Path
    ) -> None:
        assert factory(fixture_root).search("zzzz no such artist zzzz", 10, None) == ()


@pytest.mark.contract
@pytest.mark.parametrize(("name", "factory"), ACQUISITION_FACTORIES)
class TestAcquisitionProviderContract:
    def test_one_valid_mp3_appears_in_the_workspace(
        self,
        name: str,
        factory: Callable[[Path], AcquisitionProvider],
        fixture_root: Path,
        disposable_root: Path,
    ) -> None:
        workspace = disposable_root / "work"
        workspace.mkdir()

        artifact = factory(fixture_root).acquire(
            a_candidate(), str(workspace), None, lambda _phase, _percent: None, lambda: False
        )

        acquired = Path(artifact.location)
        assert acquired.is_file()
        assert acquired.parent == workspace
        assert artifact.byte_size > 0

    def test_progress_is_reported_monotonically_and_never_invented(
        self,
        name: str,
        factory: Callable[[Path], AcquisitionProvider],
        fixture_root: Path,
        disposable_root: Path,
    ) -> None:
        workspace = disposable_root / "work"
        workspace.mkdir()
        reported: list[float | None] = []

        factory(fixture_root).acquire(
            a_candidate(),
            str(workspace),
            None,
            lambda _phase, percent: reported.append(percent),
            lambda: False,
        )

        known = [value for value in reported if value is not None]
        assert known == sorted(known)
        assert all(0.0 <= value <= 100.0 for value in known)

    def test_a_cancellation_request_stops_the_work(
        self,
        name: str,
        factory: Callable[[Path], AcquisitionProvider],
        fixture_root: Path,
        disposable_root: Path,
    ) -> None:
        workspace = disposable_root / "work"
        workspace.mkdir()

        with pytest.raises(AcquisitionCancelledError):
            factory(fixture_root).acquire(
                a_candidate(), str(workspace), None, lambda _phase, _percent: None, lambda: True
            )

        assert list(workspace.iterdir()) == []


@pytest.mark.contract
class TestRejectedWireInputs:
    """The Deezer wire contract, shared by every adapter that parses it."""

    def test_a_provider_error_object_is_refused(self) -> None:
        with pytest.raises(ProviderResponseError):
            candidates_from_search({"error": {"type": "Exception", "message": "quota"}})

    def test_a_body_without_a_data_array_is_refused(self) -> None:
        with pytest.raises(ProviderResponseError):
            candidates_from_search({"total": 0})

    def test_a_body_that_is_not_an_object_is_refused(self) -> None:
        with pytest.raises(ProviderResponseError):
            candidates_from_search(["not", "an", "object"])

    def test_a_malformed_row_is_dropped_without_losing_the_usable_ones(self) -> None:
        payload = {
            "data": [
                {"id": None, "title": "No identifier", "artist": {"name": "Nobody"}},
                {"id": 1, "title": "Usable", "artist": {"name": "Somebody"}},
                "not an object",
            ]
        }

        candidates = candidates_from_search(payload)

        assert [candidate.title for candidate in candidates] == ["Usable"]

    def test_an_unusable_isrc_is_dropped_rather_than_failing_the_row(self) -> None:
        payload = {"data": [{"id": 1, "title": "T", "artist": {"name": "A"}, "isrc": "nope"}]}

        candidates = candidates_from_search(payload)

        assert candidates[0].isrc is None

    def test_an_empty_isrc_means_absent_not_malformed(self) -> None:
        payload = {"data": [{"id": 1, "title": "T", "artist": {"name": "A"}, "isrc": ""}]}

        assert candidates_from_search(payload)[0].isrc is None

    def test_a_deezer_candidate_carries_a_yt_dlp_search_locator(self) -> None:
        """Deezer never supplies audio, so the locator names the audio match."""
        payload = {"data": [{"id": 1, "title": "Teardrop", "artist": {"name": "Massive Attack"}}]}

        candidate = candidates_from_search(payload)[0]

        assert candidate.acquisition_locator == "ytsearch1:Massive Attack Teardrop"

    def test_an_insecure_cover_url_is_not_accepted(self) -> None:
        payload = {
            "data": [
                {
                    "id": 1,
                    "title": "T",
                    "artist": {"name": "A"},
                    "album": {"cover_xl": "http://cdn.invalid/x.jpg"},
                }
            ]
        }

        assert candidates_from_search(payload)[0].artwork_url is None
