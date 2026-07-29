"""Local-first search, explicit online search, and the durable event stream."""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from chillify.api.routes.events import event_frames
from chillify.application.downloads import DownloadService
from chillify.composition import Composition
from chillify.domain.jobs import JobId, JobProvider
from chillify.domain.protocols import TrackCandidate
from chillify.infrastructure.providers.fixtures import FixtureDiscoveryProvider
from chillify.infrastructure.providers.registry import ProviderRegistry
from chillify.infrastructure.providers.spotify_oembed import OEMBED_URL

pytestmark = pytest.mark.integration


@dataclass
class CountingDiscovery:
    """A discovery adapter that records every call made to it."""

    inner: FixtureDiscoveryProvider
    calls: list[str] = field(default_factory=list)
    name: str = "deezer"

    def search(self, query: str, limit: int, proxy: str | None) -> tuple[TrackCandidate, ...]:
        self.calls.append(query)
        return tuple(self.inner.search(query, limit, proxy))


@pytest.fixture
def counted_discovery(gate_composition: Composition) -> CountingDiscovery:
    """Replace the bound discovery adapter with one that counts its calls."""
    fixture_root = gate_composition.settings.fixture_root
    assert isinstance(fixture_root, Path)
    counting = CountingDiscovery(inner=FixtureDiscoveryProvider(fixture_root=fixture_root))
    gate_composition.registry = ProviderRegistry(
        discovery={"deezer": counting},
        acquisition=dict(gate_composition.registry.acquisition),
    )
    return counting


class TestLocalFirstSearch:
    def test_searching_the_library_makes_no_provider_call(
        self, gate_api: TestClient, counted_discovery: CountingDiscovery
    ) -> None:
        """Typing in the search box must never reach the internet."""
        response = gate_api.get("/api/v1/library/tracks", params={"q": "daft punk"})

        assert response.status_code == 200
        assert counted_discovery.calls == []

    def test_the_explicit_online_search_is_the_only_thing_that_calls_out(
        self, gate_api: TestClient, counted_discovery: CountingDiscovery
    ) -> None:
        gate_api.get("/api/v1/search/deezer", params={"q": "daft punk"})

        assert counted_discovery.calls == ["daft punk"]


class TestDeezerSearch:
    def test_a_result_is_never_playable(self, gate_api: TestClient) -> None:
        items = gate_api.get("/api/v1/search/deezer", params={"q": "daft punk"}).json()["items"]

        assert items
        assert all(item["is_playable"] is False for item in items)

    def test_a_result_carries_the_normalized_candidate_shape(self, gate_api: TestClient) -> None:
        first = gate_api.get("/api/v1/search/deezer", params={"q": "sigur"}).json()["items"][0]

        candidate = first["candidate"]
        assert candidate["provider"] == "deezer"
        assert candidate["title"] == "Hoppipolla"
        assert candidate["artist"] == "Sigur Ros"
        assert candidate["acquisition_locator"].startswith("ytsearch1:")
        assert first["existing_track_id"] is None

    def test_an_already_downloaded_result_links_to_the_local_track(
        self, gate_api: TestClient, gate_downloads: DownloadService
    ) -> None:
        """A duplicate offers the local track instead of a second download."""
        candidate = gate_api.get("/api/v1/search/deezer", params={"q": "daft punk"}).json()[
            "items"
        ][0]["candidate"]
        created = gate_api.post(
            "/api/v1/downloads", json={"source_type": "deezer_result", "candidate": candidate}
        ).json()
        gate_downloads.run_job(JobId(str(created["id"])))

        repeated = gate_api.get("/api/v1/search/deezer", params={"q": "daft punk"}).json()["items"][
            0
        ]

        assert repeated["existing_track_id"] is not None
        local = gate_api.get("/api/v1/library/tracks").json()["items"]
        assert [track["id"] for track in local] == [repeated["existing_track_id"]]

    def test_a_blank_query_is_rejected_before_any_provider_is_reached(
        self, gate_api: TestClient, counted_discovery: CountingDiscovery
    ) -> None:
        response = gate_api.get("/api/v1/search/deezer", params={"q": ""})

        assert response.status_code == 422
        assert counted_discovery.calls == []


class TestCatalogSearch:
    def test_all_catalog_search_uses_available_providers(self, gate_api: TestClient) -> None:
        response = gate_api.get(
            "/api/v1/search/catalog",
            params={"q": "daft punk", "provider": "all", "limit": 5},
        )

        assert response.status_code == 200
        assert response.json()["items"]

    def test_spotify_reference_returns_catalog_choices(self, gate_api: TestClient) -> None:
        track_id = "2cGxRwrMyEAp8dEbuZaVv6"
        with respx.mock:
            respx.get(OEMBED_URL).mock(
                return_value=httpx.Response(
                    200,
                    json={
                        "title": "Hoppipolla",
                        "thumbnail_url": "https://i.scdn.co/image/reference",
                    },
                )
            )
            response = gate_api.post(
                "/api/v1/links/spotify/matches",
                json={"url": f"https://open.spotify.com/track/{track_id}"},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["reference"]["spotify_id"] == track_id
        assert body["reference"]["title"] == "Hoppipolla"
        assert body["items"][0]["candidate"]["provider"] == "deezer"


class TestUnavailableProviders:
    def test_downloading_without_a_bound_adapter_is_refused_with_a_safe_message(
        self, gate_api: TestClient, gate_composition: Composition
    ) -> None:
        candidate = gate_api.get("/api/v1/search/deezer", params={"q": "daft punk"}).json()[
            "items"
        ][0]["candidate"]
        gate_composition.registry = ProviderRegistry(
            discovery=dict(gate_composition.registry.discovery), acquisition={}
        )
        from chillify.api.dependencies import get_download_service

        gate_api.app.dependency_overrides.pop(get_download_service, None)

        response = gate_api.post(
            "/api/v1/downloads", json={"source_type": "deezer_result", "candidate": candidate}
        )

        assert response.status_code == 503
        assert response.json()["error"]["code"] == "provider_disabled"
        assert response.json()["error"]["detail"] == {"provider": str(JobProvider.YT_DLP)}


class TestEventStream:
    """The stream is exercised as the iterator it is.

    A browser disconnects by closing the socket; a test cannot, because the
    stream deliberately never ends on its own. Driving the generator directly
    tests exactly the behaviour the route mounts, and stops when it has seen it.
    """

    def test_a_reconnect_replays_the_durable_events_it_missed(
        self,
        gate_api: TestClient,
        gate_composition: Composition,
        gate_downloads: DownloadService,
    ) -> None:
        job_id = _run_one_download(gate_api, gate_downloads)

        frames = _drain(
            event_frames(gate_downloads, gate_composition, cursor=0), until="library.changed"
        )

        assert frames[0][0] == "system.changed"
        job_events = [payload for name, payload in frames if name == "job.changed"]
        assert [event["phase"] for event in job_events][-1] == "completed"
        assert all(event["job_id"] == job_id for event in job_events)
        assert ("library.changed", {"job_id": job_id}) in frames

    def test_durable_events_carry_an_id_and_transient_ones_do_not(
        self,
        gate_api: TestClient,
        gate_composition: Composition,
        gate_downloads: DownloadService,
    ) -> None:
        """One cursor, one sequence: transient frames must not move it."""
        _run_one_download(gate_api, gate_downloads)

        raw = _drain_raw(
            event_frames(gate_downloads, gate_composition, cursor=0), until="library.changed"
        )

        for frame in raw:
            has_id = frame.startswith("id: ")
            assert has_id == ("event: job.changed" in frame)

    def test_a_fresh_connection_starts_from_now_rather_than_replaying_history(
        self,
        gate_api: TestClient,
        gate_composition: Composition,
        gate_downloads: DownloadService,
    ) -> None:
        _run_one_download(gate_api, gate_downloads)

        frames = _drain(
            event_frames(gate_downloads, gate_composition, cursor=-1), until="system.changed"
        )

        assert [name for name, _ in frames] == ["system.changed"]

    def test_the_status_snapshot_reports_readiness_and_degradation(
        self, gate_composition: Composition, gate_downloads: DownloadService
    ) -> None:
        frames = _drain(
            event_frames(gate_downloads, gate_composition, cursor=-1), until="system.changed"
        )

        _, payload = frames[0]
        assert set(payload) == {"ready", "degraded", "redis"}

    def test_the_route_declares_the_event_stream_media_type(self, gate_api: TestClient) -> None:
        schema = gate_api.get("/api/v1/openapi.json").json()
        responses = schema["paths"]["/api/v1/events"]["get"]["responses"]

        assert "text/event-stream" in responses["200"]["content"]


def _run_one_download(client: TestClient, downloads: DownloadService) -> str:
    candidate = client.get("/api/v1/search/deezer", params={"q": "sigur"}).json()["items"][0][
        "candidate"
    ]
    created = client.post(
        "/api/v1/downloads", json={"source_type": "deezer_result", "candidate": candidate}
    ).json()
    downloads.run_job(JobId(str(created["id"])))
    return str(created["id"])


# A stream that is still producing after this many frames is a defect, not a
# slow test; the bound turns that into a failure instead of a hang.
FRAME_LIMIT = 200


def _drain(stream: Iterator[str], *, until: str) -> list[tuple[str, dict[str, object]]]:
    return [_parse(frame) for frame in _drain_raw(stream, until=until)]


def _drain_raw(stream: Iterator[str], *, until: str) -> list[str]:
    """Read frames until one announces `until`, then stop consuming."""
    frames: list[str] = []
    for frame in stream:
        frames.append(frame)
        if f"event: {until}" in frame or len(frames) >= FRAME_LIMIT:
            break
    return frames


def _parse(frame: str) -> tuple[str, dict[str, object]]:
    name = ""
    payload: dict[str, object] = {}
    for line in frame.splitlines():
        if line.startswith("event: "):
            name = line.removeprefix("event: ")
        elif line.startswith("data: "):
            payload = json.loads(line.removeprefix("data: "))
    return name, payload
