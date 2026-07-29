"""Contract tests for the keyless Apple iTunes Search discovery adapter."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from chillify.domain.errors import ProviderResponseError
from chillify.infrastructure.providers.apple_music import AppleMusicDiscoveryProvider
from chillify.infrastructure.providers.apple_music_wire import candidates_from_search
from chillify.infrastructure.security import outbound

pytestmark = pytest.mark.contract

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
_SEARCH_URL = "https://itunes.apple.com/search"
_PROXY = "socks5://proxyuser:proxysecretpw@proxy.invalid:1080"


def _recorded_payload() -> dict[str, object]:
    return json.loads(
        (FIXTURES / "providers" / "apple_music_search.json").read_text(encoding="utf-8")
    )


class TestAppleMusicDiscoveryContract:
    def test_a_match_is_normalized_without_promo_preview_or_artwork(self) -> None:
        with respx.mock:
            route = respx.get(_SEARCH_URL).mock(
                return_value=httpx.Response(200, json=_recorded_payload())
            )
            results = AppleMusicDiscoveryProvider().search("daft punk", 10, None)

        assert route.called
        assert results
        first = results[0]
        assert first.provider == "apple"
        assert first.source_id == "5468305"
        assert first.source_url == "https://music.apple.com/us/album/one-more-time/5468303?i=5468305"
        assert first.title == "One More Time"
        assert first.artist == "Daft Punk"
        assert first.album == "Discovery"
        assert first.release_year == 2001
        assert first.disc_number == 1
        assert first.track_number == 1
        assert first.duration_ms == 320000
        assert first.artwork_url is None
        assert first.acquisition_locator == "ytsearch1:Daft Punk One More Time"
        assert "preview" not in first.acquisition_locator.lower()
        assert all(not candidate.is_playable for candidate in results)

    def test_uses_the_song_query_and_bounds_limit_with_configured_country(self) -> None:
        with respx.mock:
            route = respx.get(_SEARCH_URL).mock(
                return_value=httpx.Response(200, json={"results": []})
            )
            assert AppleMusicDiscoveryProvider(country="gb").search("bjork", 999, None) == ()

        request = route.calls[0].request
        assert dict(request.url.params) == {
            "term": "bjork",
            "media": "music",
            "entity": "song",
            "country": "GB",
            "limit": "50",
        }

    def test_an_empty_results_array_returns_nothing_rather_than_failing(self) -> None:
        with respx.mock:
            respx.get(_SEARCH_URL).mock(return_value=httpx.Response(200, json={"results": []}))
            assert AppleMusicDiscoveryProvider().search("zzzz", 10, None) == ()

    @pytest.mark.parametrize("payload", [{}, {"resultCount": 0}, []])
    def test_a_body_without_results_array_becomes_a_typed_error(self, payload: object) -> None:
        with respx.mock:
            respx.get(_SEARCH_URL).mock(return_value=httpx.Response(200, json=payload))
            with pytest.raises(ProviderResponseError):
                AppleMusicDiscoveryProvider().search("daft punk", 10, None)

    def test_an_unreadable_body_becomes_a_typed_error(self) -> None:
        with respx.mock:
            respx.get(_SEARCH_URL).mock(return_value=httpx.Response(200, content=b"not json"))
            with pytest.raises(ProviderResponseError):
                AppleMusicDiscoveryProvider().search("daft punk", 10, None)

    def test_an_error_status_becomes_a_typed_error(self) -> None:
        with respx.mock:
            respx.get(_SEARCH_URL).mock(return_value=httpx.Response(503))
            with pytest.raises(ProviderResponseError):
                AppleMusicDiscoveryProvider().search("daft punk", 10, None)

    def test_malformed_rows_and_insecure_source_urls_are_dropped(self) -> None:
        results = candidates_from_search(
            {
                "results": [
                    {"trackId": 1, "trackName": "No Artist"},
                    {
                        "trackId": 2,
                        "trackName": "Unsafe",
                        "artistName": "Artist",
                        "trackViewUrl": "http://music.apple.com/track/2",
                    },
                ]
            }
        )

        assert results == ()


@pytest.mark.integration
class TestAppleMusicProxyPolicy:
    def test_the_saved_proxy_reaches_the_client_with_no_direct_fallback(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: list[str | None] = []

        def fake_build(*, proxy: str | None, **_kwargs: object) -> httpx.Client:
            captured.append(proxy)
            return _CannedClient(httpx.Response(200, json={"results": []}))

        monkeypatch.setattr(outbound, "build_httpx_client", fake_build)
        AppleMusicDiscoveryProvider().search("q", 5, _PROXY)

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
