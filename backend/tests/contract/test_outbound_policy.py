"""The shared outbound HTTP policy contract.

Every production adapter that reaches the internet — Deezer discovery and
Last.fm enrichment — goes through the one `OutboundHttp` policy, so they share
one retry rule, one rejection rule, and one proxy rule. This suite pins that
shared behaviour once rather than per adapter, and confirms the fixture adapters
make no outbound request at all, which is how they honour the same proxy
contract: they never have traffic to route.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
import respx

from chillify.domain.errors import ProviderResponseError
from chillify.domain.protocols import MetadataPatch, TrackCandidate
from chillify.infrastructure.providers.deezer import DeezerDiscoveryProvider
from chillify.infrastructure.providers.fixtures import FixtureDiscoveryProvider
from chillify.infrastructure.providers.lastfm import LastfmEnricher
from chillify.infrastructure.security import outbound
from chillify.infrastructure.security.outbound import _MAX_ATTEMPTS

pytestmark = pytest.mark.contract

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"

_DEEZER_SEARCH = "https://api.deezer.com/search"
_LASTFM_INFO = "https://ws.audioscrobbler.com/2.0/"

_PROXY = "socks5://proxyuser:proxysecretpw@proxy.invalid:1080"


def _candidate() -> TrackCandidate:
    return TrackCandidate(
        provider="deezer",
        source_id="3135556",
        source_url="https://www.deezer.com/track/3135556",
        title="One More Time",
        artist="Daft Punk",
        album=None,
        release_year=None,
        disc_number=None,
        track_number=None,
        duration_ms=None,
        isrc=None,
        artwork_url=None,
        acquisition_locator="ytsearch1:Daft Punk One More Time",
        raw_fingerprint=None,
    )


# One "make a single outbound call" driver per production adapter. Each returns
# nothing meaningful; the suite asserts on the transport, not the parse.
def _drive_deezer() -> None:
    DeezerDiscoveryProvider().search("daft punk", 5, None)


def _drive_lastfm() -> MetadataPatch:
    return LastfmEnricher(api_key="an-api-key-value").enrich(_candidate(), ["album"], None)


ADAPTER_DRIVERS: list[tuple[str, str, Callable[[], object]]] = [
    ("deezer", _DEEZER_SEARCH, _drive_deezer),
    ("lastfm", _LASTFM_INFO, _drive_lastfm),
]


@pytest.mark.parametrize(("name", "url", "drive"), ADAPTER_DRIVERS)
class TestSharedRejectionPolicy:
    def test_a_retryable_status_is_retried_to_the_attempt_limit(
        self, name: str, url: str, drive: Callable[[], object]
    ) -> None:
        with respx.mock(assert_all_called=False) as router:
            route = router.get(url).mock(
                side_effect=[httpx.Response(503) for _ in range(_MAX_ATTEMPTS)]
            )
            if name == "deezer":
                with pytest.raises(ProviderResponseError):
                    drive()
            else:
                drive()

        assert route.call_count == _MAX_ATTEMPTS

    def test_a_client_input_error_is_not_retried(
        self, name: str, url: str, drive: Callable[[], object]
    ) -> None:
        with respx.mock(assert_all_called=False) as router:
            route = router.get(url).mock(return_value=httpx.Response(400))
            if name == "deezer":
                with pytest.raises(ProviderResponseError):
                    drive()
            else:
                drive()

        assert route.call_count == 1


class TestSharedProxyPolicy:
    """Every adapter builds one client, always with the saved proxy, never direct."""

    @pytest.mark.parametrize(("name", "url", "drive"), ADAPTER_DRIVERS)
    def test_the_configured_proxy_reaches_every_client(
        self,
        name: str,
        url: str,
        drive: Callable[[], object],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        captured: list[str | None] = []

        def fake_build(*, proxy: str | None, **_kwargs: object) -> httpx.Client:
            captured.append(proxy)
            return _CannedClient(httpx.Response(200, json={"data": []}))

        monkeypatch.setattr(outbound, "build_httpx_client", fake_build)

        # Route the driver's single call through a proxy by rebinding it.
        if name == "deezer":
            DeezerDiscoveryProvider().search("q", 5, _PROXY)
        else:
            LastfmEnricher(api_key="an-api-key-value").enrich(_candidate(), ["album"], _PROXY)

        assert captured, "the adapter built no client at all"
        assert all(proxy == _PROXY for proxy in captured)
        assert None not in captured  # no direct-fallback client was ever created


class TestFixtureAdapterMakesNoRequest:
    def test_the_fixture_discovery_adapter_never_reaches_the_network(
        self, disposable_root: Path
    ) -> None:
        root = disposable_root / "fixtures"
        shutil.copytree(FIXTURES, root)

        with respx.mock(assert_all_called=False) as router:
            route = router.get(_DEEZER_SEARCH)
            FixtureDiscoveryProvider(fixture_root=root).search("daft punk", 5, _PROXY)

        assert route.call_count == 0


class _CannedClient:
    """A stand-in httpx client that returns one canned response.

    It supports the context-manager and `request` surface `OutboundHttp` uses,
    so the proxy-threading assertion never needs a real socket.
    """

    def __init__(self, response: httpx.Response) -> None:
        self._response = response

    def __enter__(self) -> _CannedClient:
        return self

    def __exit__(self, *_exc: object) -> bool:
        return False

    def request(self, *_args: object, **_kwargs: object) -> httpx.Response:
        return self._response
