"""The production Last.fm enrichment contract.

Last.fm only ever fills gaps: it returns a patch of exactly the requested
missing fields and nothing else, so a field the caller did not name can never be
touched. Every failure — no key, an API error, an absent track, a network fault
— is a non-fatal empty patch rather than a raised error, because an unreachable
Last.fm must never fail an otherwise complete download. Driven through respx so
no case touches the network.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from chillify.domain.protocols import MetadataPatch, TrackCandidate
from chillify.infrastructure.providers.lastfm import LastfmEnricher
from chillify.infrastructure.security import outbound

pytestmark = pytest.mark.contract

_INFO_URL = "https://ws.audioscrobbler.com/2.0/"
_API_KEY = "an-api-key-value"
_PROXY = "socks5://proxyuser:proxysecretpw@proxy.invalid:1080"


def _candidate() -> TrackCandidate:
    return TrackCandidate(
        provider="deezer",
        source_id="1",
        source_url="https://www.deezer.com/track/1",
        title="Teardrop",
        artist="Massive Attack",
        album=None,
        release_year=None,
        disc_number=None,
        track_number=None,
        duration_ms=None,
        isrc=None,
        artwork_url=None,
        acquisition_locator="ytsearch1:Massive Attack Teardrop",
        raw_fingerprint=None,
    )


def _track_info() -> dict[str, object]:
    return {
        "track": {
            "name": "Teardrop",
            "artist": {"name": "Massive Attack"},
            "album": {
                "title": "Mezzanine",
                "image": [
                    {"#text": "https://img.invalid/small.jpg", "size": "small"},
                    {"#text": "https://img.invalid/extralarge.jpg", "size": "extralarge"},
                    {"#text": "http://img.invalid/insecure.jpg", "size": "mega"},
                ],
            },
            "duration": "331000",
        }
    }


class TestLastfmGapMerge:
    def test_only_the_requested_missing_fields_are_filled(self) -> None:
        with respx.mock:
            respx.get(_INFO_URL).mock(return_value=httpx.Response(200, json=_track_info()))
            patch = LastfmEnricher(api_key=_API_KEY).enrich(
                _candidate(), ["album", "artwork_url"], None
            )

        assert patch.album == "Mezzanine"
        assert patch.artwork_url == "https://img.invalid/extralarge.jpg"
        # Nothing the caller did not name is ever returned, so a populated field
        # can never be overwritten downstream.
        assert patch.title is None
        assert patch.artist is None
        assert patch.duration_ms is None

    def test_the_gap_merge_is_deterministic(self) -> None:
        with respx.mock:
            respx.get(_INFO_URL).mock(return_value=httpx.Response(200, json=_track_info()))
            enricher = LastfmEnricher(api_key=_API_KEY)
            first = enricher.enrich(_candidate(), ["album", "duration_ms"], None)
            second = enricher.enrich(_candidate(), ["album", "duration_ms"], None)

        assert first == second
        assert first.duration_ms == 331000

    def test_the_largest_secure_image_wins_and_insecure_urls_are_dropped(self) -> None:
        with respx.mock:
            respx.get(_INFO_URL).mock(return_value=httpx.Response(200, json=_track_info()))
            patch = LastfmEnricher(api_key=_API_KEY).enrich(_candidate(), ["artwork_url"], None)

        assert patch.artwork_url == "https://img.invalid/extralarge.jpg"

    def test_without_a_key_no_request_is_made_and_the_patch_is_empty(self) -> None:
        with respx.mock as router:
            route = router.get(_INFO_URL)
            patch = LastfmEnricher(api_key=None).enrich(_candidate(), ["album"], None)

        assert patch == MetadataPatch()
        assert route.call_count == 0

    def test_without_missing_fields_no_request_is_made(self) -> None:
        with respx.mock as router:
            route = router.get(_INFO_URL)
            patch = LastfmEnricher(api_key=_API_KEY).enrich(_candidate(), [], None)

        assert patch == MetadataPatch()
        assert route.call_count == 0

    def test_an_api_error_object_is_a_non_fatal_empty_patch(self) -> None:
        with respx.mock:
            respx.get(_INFO_URL).mock(
                return_value=httpx.Response(200, json={"error": 6, "message": "not found"})
            )
            patch = LastfmEnricher(api_key=_API_KEY).enrich(_candidate(), ["album"], None)

        assert patch == MetadataPatch()

    def test_an_absent_track_is_a_non_fatal_empty_patch(self) -> None:
        with respx.mock:
            respx.get(_INFO_URL).mock(return_value=httpx.Response(200, json={"nothing": True}))
            patch = LastfmEnricher(api_key=_API_KEY).enrich(_candidate(), ["album"], None)

        assert patch == MetadataPatch()

    def test_a_network_fault_is_a_non_fatal_empty_patch(self) -> None:
        with respx.mock:
            respx.get(_INFO_URL).mock(side_effect=httpx.ConnectError("down"))
            patch = LastfmEnricher(api_key=_API_KEY).enrich(_candidate(), ["album"], None)

        assert patch == MetadataPatch()


@pytest.mark.integration
class TestLastfmProxyPolicy:
    def test_the_saved_proxy_reaches_the_client_with_no_direct_fallback(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: list[str | None] = []

        def fake_build(*, proxy: str | None, **_kwargs: object) -> httpx.Client:
            captured.append(proxy)
            return _CannedClient(httpx.Response(200, json=_track_info()))

        monkeypatch.setattr(outbound, "build_httpx_client", fake_build)
        LastfmEnricher(api_key=_API_KEY).enrich(_candidate(), ["album"], _PROXY)

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
