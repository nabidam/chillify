"""The saved proxy actually reaches every outbound provider call.

Task 20's release-gate walkthrough found that `SearchService`,
`LinkInspectionService`, and `DownloadService` were built in the composition
root without their `proxy_url`, so every one of them ran with `proxy=None`
regardless of what an operator saved in Settings. `test_proxy_fail_closed.py`
exercised `OutboundHttp` and the `/settings/proxy/test` endpoint directly with
an explicit proxy value, and never went through `SearchService`,
`LinkInspectionService`, or `DownloadService` at all — so it could not have
caught a composition-root wiring gap that only ever supplied those services
with the default `None`.

This suite asserts the actual value each adapter call receives, proves a proxy
saved after a service is already built is still honoured (no frozen snapshot,
which matters most for the worker's long-running `DownloadService`), and
proves the fail-closed/no-proxy guarantees survive the fix.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import httpx
import pytest

from chillify.application.downloads import DownloadService
from chillify.composition import Composition, build_composition
from chillify.config import load_settings
from chillify.domain.errors import ProxyConnectionError
from chillify.domain.jobs import JobId, JobProvider, JobState, SourceType
from chillify.domain.protocols import (
    AudioArtifact,
    CancelledCallback,
    ProgressCallback,
    TrackCandidate,
)
from chillify.infrastructure.security import outbound

pytestmark = pytest.mark.integration

VIDEO_URL = "https://www.youtube.com/watch?v=u7K72X4eo_s"
SENTINEL_PROXY = "socks5://proxyuser:proxypass@proxy.invalid:1080"
BOGUS_PROXY = "socks5://unreachable.invalid:1"


def _candidate(source_id: str) -> TrackCandidate:
    return TrackCandidate(
        provider="deezer",
        source_id=source_id,
        source_url=f"https://www.deezer.com/track/{source_id}",
        title="Proxy Wiring Test",
        artist="Task 20",
        album=None,
        release_year=None,
        disc_number=None,
        track_number=None,
        duration_ms=None,
        isrc=None,
        artwork_url=None,
        acquisition_locator=f"ytsearch1:proxy wiring test {source_id}",
        raw_fingerprint=None,
    )


@dataclass
class _RecordingDiscovery:
    """Wraps a real discovery adapter and records the `proxy` it was handed."""

    delegate: object
    captured: list[str | None] = field(default_factory=list)
    name: str = "deezer"

    def search(self, query: str, limit: int, proxy: str | None) -> object:
        self.captured.append(proxy)
        return self.delegate.search(query, limit, proxy)


@dataclass
class _RecordingInspector:
    """Wraps a real link inspector and records the `proxy` it was handed."""

    delegate: object
    captured: list[str | None] = field(default_factory=list)
    name: str = "yt_dlp"

    def supports(self, url: str) -> bool:
        return self.delegate.supports(url)

    def inspect(self, url: str, proxy: str | None) -> TrackCandidate:
        self.captured.append(proxy)
        return self.delegate.inspect(url, proxy)


@dataclass
class _RecordingAcquisition:
    """Wraps a real acquisition adapter and records the `proxy` it was handed."""

    delegate: object
    captured: list[str | None] = field(default_factory=list)
    name: str = "fixture"

    def acquire(
        self,
        candidate: TrackCandidate,
        workspace: str,
        proxy: str | None,
        progress: ProgressCallback,
        cancelled: CancelledCallback,
    ) -> AudioArtifact:
        self.captured.append(proxy)
        return self.delegate.acquire(candidate, workspace, proxy, progress, cancelled)


def _save_proxy(composition: Composition, url: str) -> None:
    settings = composition.settings_service()
    revision = settings.read().proxy.revision
    settings.save_proxy(url, revision=revision)


class TestEachServicePropagatesTheSavedProxy:
    def test_search_service_passes_the_saved_proxy_to_the_adapter(
        self, gate_composition: Composition
    ) -> None:
        recorder = _RecordingDiscovery(delegate=gate_composition.registry.discovery["deezer"])
        gate_composition.registry.discovery["deezer"] = recorder

        _save_proxy(gate_composition, SENTINEL_PROXY)
        gate_composition.search_service().search_deezer("daft punk")

        assert recorder.captured == [SENTINEL_PROXY]

    def test_link_inspection_service_passes_the_saved_proxy_to_the_adapter(
        self, gate_composition: Composition
    ) -> None:
        recorder = _RecordingInspector(
            delegate=gate_composition.registry.link_inspectors[JobProvider.YT_DLP]
        )
        gate_composition.registry.link_inspectors[JobProvider.YT_DLP] = recorder

        _save_proxy(gate_composition, SENTINEL_PROXY)
        gate_composition.link_inspection_service().inspect(VIDEO_URL)

        assert recorder.captured == [SENTINEL_PROXY]

    def test_download_service_passes_the_saved_proxy_to_the_adapter_on_the_worker_path(
        self, gate_composition: Composition, dispatched_jobs: list[str]
    ) -> None:
        recorder = _RecordingAcquisition(
            delegate=gate_composition.registry.acquisition[JobProvider.YT_DLP]
        )
        gate_composition.registry.acquisition[JobProvider.YT_DLP] = recorder
        gate_composition.registry.acquisition[JobProvider.SPOTDL] = recorder

        # Queue with a throwaway service exactly like the API would; the queue
        # transport is stubbed because dispatch/Redis are not what this test
        # is about.
        queueing = DownloadService(
            session_factory=gate_composition.session_factory,
            registry=gate_composition.registry,
            music_root=gate_composition.settings.music_root,
            dispatch=lambda job_id: dispatched_jobs.append(str(job_id)) or "task-id",
            queue_reachable=lambda: True,
            worker_identity="test-api",
        )
        job = queueing.request_download(_candidate("wiring-1"), SourceType.DEEZER_RESULT)

        _save_proxy(gate_composition, SENTINEL_PROXY)

        # This is the object under test: built the way the worker really
        # builds it, through `composition.download_service`.
        worker = gate_composition.download_service(worker_identity="test-worker")
        worker.run_job(JobId(job.id))

        assert recorder.captured == [SENTINEL_PROXY]
        assert queueing.get_job(job.id).job.state == JobState.COMPLETED


class TestProxyChangesTakeEffectWithoutRebuildingTheService:
    def test_a_proxy_saved_after_search_service_construction_is_still_used(
        self, gate_composition: Composition
    ) -> None:
        recorder = _RecordingDiscovery(delegate=gate_composition.registry.discovery["deezer"])
        gate_composition.registry.discovery["deezer"] = recorder

        # Built while no proxy is configured.
        search_service = gate_composition.search_service()
        assert recorder.captured == []

        # An operator saves a proxy afterwards, with no restart.
        _save_proxy(gate_composition, SENTINEL_PROXY)

        search_service.search_deezer("daft punk")

        assert recorder.captured == [SENTINEL_PROXY]

    def test_a_proxy_saved_after_the_worker_download_service_is_built_is_still_used(
        self, gate_composition: Composition, dispatched_jobs: list[str]
    ) -> None:
        """The worker case matters most: one `DownloadService` can outlive many
        proxy edits, since nothing about acquiring a job's audio rebuilds it."""
        recorder = _RecordingAcquisition(
            delegate=gate_composition.registry.acquisition[JobProvider.YT_DLP]
        )
        gate_composition.registry.acquisition[JobProvider.YT_DLP] = recorder
        gate_composition.registry.acquisition[JobProvider.SPOTDL] = recorder

        queueing = DownloadService(
            session_factory=gate_composition.session_factory,
            registry=gate_composition.registry,
            music_root=gate_composition.settings.music_root,
            dispatch=lambda job_id: dispatched_jobs.append(str(job_id)) or "task-id",
            queue_reachable=lambda: True,
            worker_identity="test-api",
        )
        job = queueing.request_download(_candidate("wiring-2"), SourceType.DEEZER_RESULT)

        # Built while no proxy is configured — this is the long-lived worker
        # object a real deployment would keep using.
        worker = gate_composition.download_service(worker_identity="test-worker")

        # The operator saves a proxy only now, strictly after construction.
        _save_proxy(gate_composition, SENTINEL_PROXY)

        worker.run_job(JobId(job.id))

        assert recorder.captured == [SENTINEL_PROXY]


class _RaisingClient:
    """A client whose every request fails as an unreachable proxy would."""

    def __enter__(self) -> _RaisingClient:
        return self

    def __exit__(self, *_exc: object) -> bool:
        return False

    def request(self, *_args: object, **_kwargs: object) -> httpx.Response:
        raise httpx.ConnectError("proxy unreachable")


@pytest.fixture
def production_composition(
    migrated_environment: dict[str, str],
) -> Composition:
    settings = load_settings()
    composition = build_composition(settings, verify_mounts=False)
    try:
        yield composition
    finally:
        composition.dispose()


class TestFailClosedThroughTheRealSearchService:
    """Uses the real (non-fixture) Deezer adapter so `OutboundHttp` is really
    on the call path, proving the fail-closed guarantee survives the wiring
    fix all the way from `SearchService` down."""

    def test_a_configured_but_unreachable_proxy_fails_closed_with_no_direct_attempt(
        self,
        production_composition: Composition,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        captured: list[str | None] = []

        def fake_build(*, proxy: str | None, **_kwargs: object) -> httpx.Client:
            captured.append(proxy)
            return _RaisingClient()  # type: ignore[return-value]

        monkeypatch.setattr(outbound, "build_httpx_client", fake_build)
        _save_proxy(production_composition, BOGUS_PROXY)

        with pytest.raises(ProxyConnectionError):
            production_composition.search_service().search_deezer("daft punk")

        assert captured, "the wired service never reached the outbound policy at all"
        assert all(proxy == BOGUS_PROXY for proxy in captured)
        assert None not in captured  # never a direct-fallback attempt

    def test_with_no_proxy_configured_the_search_still_goes_direct(
        self,
        production_composition: Composition,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        captured: list[str | None] = []

        def fake_build(*, proxy: str | None, **_kwargs: object) -> httpx.Client:
            captured.append(proxy)
            request = httpx.Request("GET", "https://api.deezer.com/search")
            return httpx.Client(
                transport=httpx.MockTransport(
                    lambda _request: httpx.Response(200, json={"data": []}, request=request)
                )
            )

        monkeypatch.setattr(outbound, "build_httpx_client", fake_build)

        # No proxy has been saved: `current_proxy_url()` returns None.
        results = production_composition.search_service().search_deezer("daft punk")

        assert results == ()
        assert captured == [None]
