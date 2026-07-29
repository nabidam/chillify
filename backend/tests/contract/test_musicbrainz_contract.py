"""Production MusicBrainz discovery adapter contract, using recorded JSON only."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from chillify.domain.errors import ProviderResponseError
from chillify.infrastructure.providers.musicbrainz import (
    _SEARCH_URL,
    _USER_AGENT,
    MusicBrainzDiscoveryProvider,
)
from chillify.infrastructure.providers.musicbrainz_wire import candidates_from_recording_search
from chillify.infrastructure.security import outbound

pytestmark = pytest.mark.contract

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
_PROXY = "socks5://proxyuser:proxysecretpw@proxy.invalid:1080"


def _recorded_payload() -> dict[str, object]:
    path = FIXTURES / "providers" / "musicbrainz_recording_search.json"
    return json.loads(path.read_text(encoding="utf-8"))


class TestMusicBrainzDiscoveryContract:
    def test_a_match_is_normalized_without_an_artwork_or_audio_claim(self) -> None:
        with respx.mock:
            route = respx.get(_SEARCH_URL).mock(
                return_value=httpx.Response(200, json=_recorded_payload())
            )
            results = MusicBrainzDiscoveryProvider().search("daft punk", 10, None)

        first = results[0]
        assert first.provider == "musicbrainz"
        assert first.source_id == "fd9bc42e-77b0-4c29-a1e0-0a5263f6f72c"
        assert first.source_url == "https://musicbrainz.org/recording/fd9bc42e-77b0-4c29-a1e0-0a5263f6f72c"
        assert first.title == "Instant Crush"
        assert first.artist == "Daft Punk"
        assert first.album == "Random Access Memories"
        assert first.release_year == 2013
        assert first.duration_ms == 337560
        assert first.isrc == "USQX91300108"
        assert first.artwork_url is None
        assert first.acquisition_locator == "ytsearch1:Daft Punk Instant Crush"
        assert all(not candidate.is_playable for candidate in results)

        request = route.calls[0].request
        assert request.url.params["query"] == "daft punk"
        assert request.url.params["limit"] == "10"
        assert request.url.params["fmt"] == "json"
        assert request.headers["user-agent"] == _USER_AGENT

    def test_user_query_is_sent_as_a_parameter_and_limit_is_bounded(self) -> None:
        query = 'title:"safe" & artist:one'
        with respx.mock:
            route = respx.get(_SEARCH_URL).mock(
                return_value=httpx.Response(200, json={"recordings": []})
            )
            assert MusicBrainzDiscoveryProvider().search(query, 999, None) == ()

        request = route.calls[0].request
        assert request.url.params["query"] == query
        assert request.url.params["limit"] == "50"

    def test_empty_results_are_not_an_error(self) -> None:
        with respx.mock:
            respx.get(_SEARCH_URL).mock(return_value=httpx.Response(200, json={"recordings": []}))
            assert MusicBrainzDiscoveryProvider().search("zzzz", 10, None) == ()

    @pytest.mark.parametrize("payload", [None, {}, {"recordings": {}}, {"recordings": ["bad"]}])
    def test_malformed_envelopes_are_typed_errors_or_drop_bad_rows(self, payload: object) -> None:
        with respx.mock:
            respx.get(_SEARCH_URL).mock(return_value=httpx.Response(200, json=payload))
            if payload == {"recordings": ["bad"]}:
                assert MusicBrainzDiscoveryProvider().search("q", 10, None) == ()
            else:
                with pytest.raises(ProviderResponseError):
                    MusicBrainzDiscoveryProvider().search("q", 10, None)

    def test_unreadable_body_and_error_status_are_typed_errors(self) -> None:
        with respx.mock:
            route = respx.get(_SEARCH_URL)
            route.mock(return_value=httpx.Response(200, content=b"not json"))
            with pytest.raises(ProviderResponseError):
                MusicBrainzDiscoveryProvider().search("q", 10, None)
            route.mock(return_value=httpx.Response(503))
            with pytest.raises(ProviderResponseError):
                MusicBrainzDiscoveryProvider().search("q", 10, None)

    def test_release_is_accepted_only_when_its_title_is_unambiguous(self) -> None:
        payload = _recorded_payload()
        recording = payload["recordings"][0]
        assert isinstance(recording, dict)
        recording["releases"] = [{"title": "Album A"}, {"title": "Album B"}]

        candidate = candidates_from_recording_search(payload)[0]
        assert candidate.album is None

    def test_throttle_is_adapter_local_and_clock_testable(self) -> None:
        clock_values = iter((0.0, 0.0, 1.0))
        waits: list[float] = []
        provider = MusicBrainzDiscoveryProvider(
            clock=lambda: next(clock_values), sleeper=waits.append
        )
        with respx.mock:
            respx.get(_SEARCH_URL).mock(return_value=httpx.Response(200, json={"recordings": []}))
            provider.search("one", 10, None)
            provider.search("two", 10, None)

        assert waits == [1.0]


@pytest.mark.integration
class TestMusicBrainzProxyPolicy:
    def test_the_saved_proxy_reaches_the_client_with_no_direct_fallback(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: list[str | None] = []

        def fake_build(*, proxy: str | None, **_kwargs: object) -> httpx.Client:
            captured.append(proxy)
            return _CannedClient(httpx.Response(200, json={"recordings": []}))

        monkeypatch.setattr(outbound, "build_httpx_client", fake_build)
        MusicBrainzDiscoveryProvider().search("q", 5, _PROXY)

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
