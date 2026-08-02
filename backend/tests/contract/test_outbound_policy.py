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
from collections.abc import Callable, Iterator
from pathlib import Path

import httpx
import pytest
import respx

from chillify.domain.errors import (
    AcquisitionCancelledError,
    AcquisitionLimitExceededError,
    ProviderResponseError,
    ProxyConnectionError,
    ProxyTimeoutError,
)
from chillify.domain.protocols import MetadataPatch, TrackCandidate
from chillify.infrastructure.providers.deezer import DeezerDiscoveryProvider
from chillify.infrastructure.providers.fixtures import FixtureDiscoveryProvider
from chillify.infrastructure.providers.lastfm import LastfmEnricher
from chillify.infrastructure.security import outbound
from chillify.infrastructure.security.outbound import _MAX_ATTEMPTS, MEDIA_MAX_BYTES, OutboundHttp

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


class TestBoundedMediaTransfer:
    def test_streams_without_buffering_and_reports_real_byte_progress(self, tmp_path: Path) -> None:
        target = tmp_path / "audio.mp3"
        reported: list[float | None] = []
        with respx.mock(assert_all_called=True) as router:
            router.get("https://cdn.radiojavan.test/audio.mp3").mock(
                return_value=httpx.Response(200, headers={"content-length": "4"}, content=b"mp3!")
            )
            written = OutboundHttp().stream_to_file(
                "https://cdn.radiojavan.test/audio.mp3",
                target,
                headers={"Accept": "audio/mpeg"},
                cancelled=lambda: False,
                progress=reported.append,
            )

        assert written == 4
        assert target.read_bytes() == b"mp3!"
        assert reported[-1] == 100.0

    def test_removes_a_partial_file_on_cancellation_or_size_limit(self, tmp_path: Path) -> None:
        target = tmp_path / "audio.mp3"
        with respx.mock(assert_all_called=True) as router:
            router.get("https://cdn.radiojavan.test/cancel.mp3").mock(
                return_value=httpx.Response(200, content=b"partial")
            )
            with pytest.raises(AcquisitionCancelledError):
                OutboundHttp().stream_to_file(
                    "https://cdn.radiojavan.test/cancel.mp3",
                    target,
                    headers={"Accept": "audio/mpeg"},
                    cancelled=lambda: True,
                    progress=lambda _percent: None,
                )
        assert not target.exists()

        with respx.mock(assert_all_called=True) as router:
            router.get("https://cdn.radiojavan.test/large.mp3").mock(
                return_value=httpx.Response(
                    200, headers={"content-length": str(MEDIA_MAX_BYTES + 1)}
                )
            )
            with pytest.raises(AcquisitionLimitExceededError):
                OutboundHttp().stream_to_file(
                    "https://cdn.radiojavan.test/large.mp3",
                    target,
                    headers={"Accept": "audio/mpeg"},
                    cancelled=lambda: False,
                    progress=lambda _percent: None,
                )
        assert not target.exists()

    def test_retries_an_interrupted_stream_and_resumes_only_after_a_range_response(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        target = tmp_path / "audio.mp3"
        requested_ranges: list[str | None] = []

        client = _ResumingClient(requested_ranges)
        monkeypatch.setattr(OutboundHttp, "open", lambda _self: client)
        written = OutboundHttp().stream_to_file(
            "https://cdn.radiojavan.test/retry.mp3",
            target,
            headers={"Accept": "audio/mpeg"},
            cancelled=lambda: False,
            progress=lambda _percent: None,
        )

        assert written == 4
        assert target.read_bytes() == b"abcd"
        assert requested_ranges == [None, "bytes=2-"]

    @pytest.mark.parametrize(
        ("failure", "error"),
        [
            (httpx.ConnectTimeout("timed out"), ProxyTimeoutError),
            (httpx.ConnectError("refused"), ProxyConnectionError),
        ],
    )
    def test_streaming_proxy_transport_failures_remain_typed(
        self,
        tmp_path: Path,
        failure: httpx.HTTPError,
        error: type[Exception],
    ) -> None:
        target = tmp_path / "audio.mp3"
        with respx.mock(assert_all_called=True) as router:
            router.get("https://cdn.radiojavan.test/fail.mp3").mock(
                side_effect=[failure] * _MAX_ATTEMPTS
            )
            with pytest.raises(error):
                OutboundHttp(proxy=_PROXY).stream_to_file(
                    "https://cdn.radiojavan.test/fail.mp3",
                    target,
                    headers={"Accept": "audio/mpeg"},
                    cancelled=lambda: False,
                    progress=lambda _percent: None,
                )
        assert not target.exists()


class _ResumingClient:
    def __init__(self, requested_ranges: list[str | None]) -> None:
        self.requested_ranges = requested_ranges
        self.calls = 0

    def __enter__(self) -> _ResumingClient:
        return self

    def __exit__(self, *_exc: object) -> bool:
        return False

    def stream(self, _method: str, _url: str, *, headers: dict[str, str]) -> _ResponseContext:
        self.requested_ranges.append(headers.get("Range"))
        self.calls += 1
        return _ResponseContext(_InterruptedResponse() if self.calls == 1 else _RangeResponse())


class _ResponseContext:
    def __init__(self, response: _InterruptedResponse | _RangeResponse) -> None:
        self.response = response

    def __enter__(self) -> _InterruptedResponse | _RangeResponse:
        return self.response

    def __exit__(self, *_exc: object) -> bool:
        return False


class _InterruptedResponse:
    def __init__(self) -> None:
        self.status_code = 200
        self.headers = {"content-length": "4"}

    def iter_raw(self, *, chunk_size: int) -> Iterator[bytes]:
        del chunk_size
        yield b"ab"
        raise httpx.ReadError("connection lost")


class _RangeResponse:
    def __init__(self) -> None:
        self.status_code = 206
        self.headers = {"content-range": "bytes 2-3/4", "content-length": "2"}

    def iter_raw(self, *, chunk_size: int) -> Iterator[bytes]:
        del chunk_size
        yield b"cd"


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
