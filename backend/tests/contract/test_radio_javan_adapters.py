"""Shared, offline contracts for the real and fixture Radio Javan adapters."""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
import respx

from chillify.domain.errors import ProviderResponseError
from chillify.domain.protocols import TrackCandidate
from chillify.infrastructure.providers.fixtures import FixtureRadioJavanDiscoveryProvider
from chillify.infrastructure.providers.radio_javan import (
    _BASE_URL,
    RadioJavanDiscoveryProvider,
    _request_json,
)

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
