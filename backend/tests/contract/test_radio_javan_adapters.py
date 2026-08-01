"""Shared, offline contracts for the real and fixture Radio Javan adapters."""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
import respx

from chillify.domain.errors import AcquisitionCancelledError, ProviderResponseError
from chillify.domain.jobs import JobPhase
from chillify.domain.protocols import (
    AudioArtifact,
    CancelledCallback,
    ProgressCallback,
    TrackCandidate,
)
from chillify.infrastructure.providers.fixtures import (
    FixtureRadioJavanAcquisitionProvider,
    FixtureRadioJavanDiscoveryProvider,
)
from chillify.infrastructure.providers.radio_javan import (
    _BASE_URL,
    RadioJavanAcquisitionProvider,
    RadioJavanDiscoveryProvider,
    _request_json,
)
from chillify.infrastructure.providers.radio_javan_wire import media_url_from_detail

pytestmark = pytest.mark.contract

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
PROXY = "socks5://proxyuser:proxysecretpw@proxy.invalid:1080"


def _fixture(name: str) -> object:
    return json.loads((FIXTURES / "providers" / name).read_text(encoding="utf-8"))


def _assert_discovery_contract(
    search: Callable[[], tuple[TrackCandidate, ...]],
    featured: Callable[[], tuple[TrackCandidate, ...]],
    trending: Callable[[], tuple[TrackCandidate, ...]],
) -> None:
    results = search()
    assert [(item.source_id, item.title) for item in results] == [
        ("900001", "Radio Javan Walking Skeleton")
    ]
    assert [(item.source_id, item.title) for item in featured()] == [("900002", "Featured Fixture")]
    assert [(item.source_id, item.title) for item in trending()] == [("900004", "Trending Fixture")]


def _candidate() -> TrackCandidate:
    return TrackCandidate(
        provider="radiojavan",
        source_id="900001",
        source_url="https://play.radiojavan.com/song/900001",
        title="Radio Javan Walking Skeleton",
        artist="Radio Javan Ensemble",
        album="Chillify Fixtures",
        release_year=None,
        disc_number=None,
        track_number=None,
        duration_ms=12_000,
        isrc=None,
        artwork_url=None,
        acquisition_locator="900001",
        raw_fingerprint=None,
    )


def _assert_acquisition_contract(
    acquire: Callable[[Path, ProgressCallback, CancelledCallback], AudioArtifact], tmp_path: Path
) -> None:
    phases: list[tuple[JobPhase, float | None]] = []
    artifact = acquire(
        tmp_path / "success", lambda phase, percent: phases.append((phase, percent)), lambda: False
    )

    assert Path(artifact.location).is_file()
    assert artifact.byte_size > 0
    assert phases[0][0] is JobPhase.DOWNLOADING
    assert phases[-1] == (JobPhase.DOWNLOADING, 100.0)

    with pytest.raises(AcquisitionCancelledError):
        acquire(tmp_path / "cancelled", lambda _phase, _percent: None, lambda: True)


def _assert_safe_detail_failure(acquire: Callable[[], AudioArtifact]) -> None:
    with pytest.raises(ProviderResponseError) as raised:
        acquire()
    assert raised.value.message == "Radio Javan returned a response Chillify could not read."
    assert raised.value.context == {"provider": "radiojavan"}


def test_fixture_discovery_satisfies_the_shared_recorded_wire_contract(tmp_path: Path) -> None:
    fixture_root = tmp_path / "fixtures"
    shutil.copytree(FIXTURES, fixture_root)
    adapter = FixtureRadioJavanDiscoveryProvider(fixture_root=fixture_root)

    _assert_discovery_contract(
        lambda: adapter.search("walking", 10, PROXY),
        lambda: adapter.browse("featured", PROXY),
        lambda: adapter.browse("trending", PROXY),
    )


def test_production_discovery_satisfies_the_same_recorded_wire_contract() -> None:
    adapter = RadioJavanDiscoveryProvider()
    with respx.mock(assert_all_called=True) as router:
        search_route = router.get(f"{_BASE_URL}/search").mock(
            return_value=httpx.Response(200, json=_fixture("radiojavan_search.json"))
        )
        router.get(f"{_BASE_URL}/mp3s").mock(
            side_effect=[
                httpx.Response(200, json=_fixture("radiojavan_featured.json")),
                httpx.Response(200, json=_fixture("radiojavan_trending.json")),
            ]
        )

        _assert_discovery_contract(
            lambda: adapter.search("walking", 10, None),
            lambda: adapter.browse("featured", None),
            lambda: adapter.browse("trending", None),
        )

    request = search_route.calls.last.request
    assert dict(request.url.params) == {"query": "walking"}
    assert request.headers["accept"] == "application/json"
    assert request.headers["user-agent"].startswith("Chillify/")
    assert "cookie" not in request.headers
    assert "authorization" not in request.headers


def test_fixture_acquisition_satisfies_the_shared_detail_cancel_and_progress_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture_root = tmp_path / "fixtures"
    shutil.copytree(FIXTURES, fixture_root)
    adapter = FixtureRadioJavanAcquisitionProvider(fixture_root=fixture_root)
    resolved: list[tuple[object, str]] = []

    def record_detail(payload: object, source_id: str) -> str:
        resolved.append((payload, source_id))
        return media_url_from_detail(payload, source_id)

    monkeypatch.setattr(
        "chillify.infrastructure.providers.fixtures.media_url_from_detail", record_detail
    )

    def acquire(
        workspace: Path, progress: ProgressCallback, cancelled: CancelledCallback
    ) -> AudioArtifact:
        workspace.mkdir()
        return adapter.acquire(_candidate(), str(workspace), PROXY, progress, cancelled)

    _assert_acquisition_contract(acquire, tmp_path)
    assert resolved and resolved[0][1] == "900001"
    assert media_url_from_detail(*resolved[0]) == "https://cdn.radiojavan.test/audio/900001.mp3"

    (fixture_root / "providers" / "radiojavan_detail.json").write_text(
        '{"id": 900002, "hq_link": "https://cdn.radiojavan.test/not-used.mp3"}', encoding="utf-8"
    )
    failed_workspace = tmp_path / "fixture-failure"
    failed_workspace.mkdir()
    _assert_safe_detail_failure(
        lambda: adapter.acquire(
            _candidate(), str(failed_workspace), PROXY, lambda _phase, _percent: None, lambda: False
        )
    )


def test_production_acquisition_satisfies_the_shared_detail_cancel_and_progress_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    selected_media: list[str] = []
    detail_payload = _fixture("radiojavan_detail.json")
    assert isinstance(detail_payload, dict)
    payload: dict[str, object] = dict(detail_payload)
    fixture_audio = (FIXTURES / "media" / "gate-tone.mp3").read_bytes()

    class _RecordedOutbound:
        def request_limited_bytes(self, *_args: object, **_kwargs: object) -> tuple[int, bytes]:
            return 200, json.dumps(payload).encode("utf-8")

        def stream_to_file(self, url: str, target: Path, **kwargs: object) -> int:
            selected_media.append(url)
            target.write_bytes(fixture_audio)
            progress = kwargs["progress"]
            assert callable(progress)
            progress(100.0)
            return target.stat().st_size

    monkeypatch.setattr(
        "chillify.infrastructure.providers.radio_javan.OutboundHttp",
        lambda **_kwargs: _RecordedOutbound(),
    )
    adapter = RadioJavanAcquisitionProvider()

    def acquire(
        workspace: Path, progress: ProgressCallback, cancelled: CancelledCallback
    ) -> AudioArtifact:
        workspace.mkdir()
        return adapter.acquire(_candidate(), str(workspace), PROXY, progress, cancelled)

    _assert_acquisition_contract(acquire, tmp_path)
    assert selected_media == ["https://cdn.radiojavan.test/audio/900001.mp3"]

    payload["id"] = 900002
    failed_workspace = tmp_path / "production-failure"
    failed_workspace.mkdir()
    _assert_safe_detail_failure(
        lambda: adapter.acquire(
            _candidate(),
            str(failed_workspace),
            PROXY,
            lambda _phase, _percent: None,
            lambda: False,
        )
    )


def test_production_transport_failure_is_a_safe_typed_provider_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FailingOutbound:
        def request_limited_bytes(self, *_args: object, **_kwargs: object) -> tuple[int, bytes]:
            raise httpx.ConnectError("upstream body and proxy credentials must not escape")

    monkeypatch.setattr(
        "chillify.infrastructure.providers.radio_javan.OutboundHttp",
        lambda **_kwargs: _FailingOutbound(),
    )

    with pytest.raises(ProviderResponseError) as raised:
        _request_json(f"{_BASE_URL}/search", params={"query": "walking"}, proxy=None)

    assert raised.value.context == {"provider": "radiojavan"}
    assert "credentials" not in raised.value.message
