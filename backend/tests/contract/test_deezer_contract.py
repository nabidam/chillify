"""The production Deezer discovery contract.

The fixture Deezer adapter is held to the discovery protocol in
`test_provider_protocols.py`; this suite holds the production adapter to the
same behaviour, driven by sanitized recorded payloads through respx so no case
touches the network. Success, an empty result, and every malformed-response
outcome are all part of the contract, as is the proxy rule: the adapter builds
one client, always with the saved proxy, never a direct fallback.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from chillify.domain.errors import ProviderResponseError
from chillify.infrastructure.providers.deezer import DeezerDiscoveryProvider
from chillify.infrastructure.security import outbound

pytestmark = pytest.mark.contract

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
_SEARCH_URL = "https://api.deezer.com/search"
_PROXY = "socks5://proxyuser:proxysecretpw@proxy.invalid:1080"


def _recorded_payload() -> dict[str, object]:
    return json.loads((FIXTURES / "providers" / "deezer_search.json").read_text(encoding="utf-8"))


class TestDeezerDiscoveryContract:
    def test_a_match_is_returned_as_a_normalized_unplayable_candidate(self) -> None:
        with respx.mock:
            respx.get(_SEARCH_URL).mock(return_value=httpx.Response(200, json=_recorded_payload()))
            results = DeezerDiscoveryProvider().search("daft punk", 10, None)

        assert results
        first = results[0]
        assert first.provider == "deezer"
        assert first.title and first.artist
        assert first.acquisition_locator.startswith("ytsearch1:")
        assert all(not candidate.is_playable for candidate in results)

    def test_the_requested_limit_bounds_the_returned_candidates(self) -> None:
        with respx.mock:
            respx.get(_SEARCH_URL).mock(return_value=httpx.Response(200, json=_recorded_payload()))
            results = DeezerDiscoveryProvider().search("a", 1, None)

        assert len(results) <= 1

    def test_an_empty_data_array_returns_nothing_rather_than_failing(self) -> None:
        with respx.mock:
            respx.get(_SEARCH_URL).mock(return_value=httpx.Response(200, json={"data": []}))
            assert DeezerDiscoveryProvider().search("zzzz", 10, None) == ()

    def test_a_provider_error_object_becomes_a_typed_error(self) -> None:
        with respx.mock:
            respx.get(_SEARCH_URL).mock(
                return_value=httpx.Response(200, json={"error": {"type": "Exception"}})
            )
            with pytest.raises(ProviderResponseError):
                DeezerDiscoveryProvider().search("daft punk", 10, None)

    def test_an_unreadable_body_becomes_a_typed_error(self) -> None:
        with respx.mock:
            respx.get(_SEARCH_URL).mock(return_value=httpx.Response(200, content=b"not json"))
            with pytest.raises(ProviderResponseError):
                DeezerDiscoveryProvider().search("daft punk", 10, None)

    def test_an_error_status_becomes_a_typed_error(self) -> None:
        with respx.mock:
            respx.get(_SEARCH_URL).mock(return_value=httpx.Response(404))
            with pytest.raises(ProviderResponseError):
                DeezerDiscoveryProvider().search("daft punk", 10, None)

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
        with respx.mock:
            respx.get(_SEARCH_URL).mock(return_value=httpx.Response(200, json=payload))
            candidate = DeezerDiscoveryProvider().search("a", 10, None)[0]

        assert candidate.artwork_url is None


@pytest.mark.integration
class TestDeezerProxyPolicy:
    """The real adapter reaches the network only through the one proxy policy."""

    def test_the_saved_proxy_reaches_the_client_with_no_direct_fallback(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: list[str | None] = []

        def fake_build(*, proxy: str | None, **_kwargs: object) -> httpx.Client:
            captured.append(proxy)
            return _CannedClient(httpx.Response(200, json={"data": []}))

        monkeypatch.setattr(outbound, "build_httpx_client", fake_build)
        DeezerDiscoveryProvider().search("q", 5, _PROXY)

        assert captured, "the adapter built no client at all"
        assert all(proxy == _PROXY for proxy in captured)
        assert None not in captured


class _CannedClient:
    def __init__(self, response: httpx.Response) -> None:
        self._response = response

    def __enter__(self) -> _CannedClient:
        return self

    def __exit__(self, *_exc: object) -> bool:
        return False

    def request(self, *_args: object, **_kwargs: object) -> httpx.Response:
        return self._response
