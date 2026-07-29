"""Spotify's public oEmbed reference resolver contract."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from chillify.domain.errors import (
    ProviderResponseError,
    UnsupportedEntityError,
    ValidationFailedError,
)
from chillify.infrastructure.providers.spotify_oembed import (
    OEMBED_URL,
    SpotifyOEmbedReferenceResolver,
    canonicalize_track_url,
)
from chillify.infrastructure.security import outbound
from chillify.infrastructure.security.outbound import OutboundHttp

pytestmark = pytest.mark.contract

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
TRACK_ID = "2cGxRwrMyEAp8dEbuZaVv6"
TRACK_URL = f"https://open.spotify.com/track/{TRACK_ID}"
_PROXY = "socks5://proxyuser:proxysecretpw@proxy.invalid:1080"


def _payload() -> dict[str, object]:
    return json.loads((FIXTURES / "spotify_oembed" / "track_success.json").read_text())


class TestSpotifyOEmbedReferenceContract:
    @pytest.mark.parametrize(
        ("submitted", "expected_id", "expected_url"),
        [
            (TRACK_URL, TRACK_ID, TRACK_URL),
            (
                f"https://play.spotify.com/intl-de/track/{TRACK_ID}?si=tracking#share",
                TRACK_ID,
                TRACK_URL,
            ),
        ],
    )
    def test_individual_track_urls_are_canonicalized(
        self, submitted: str, expected_id: str, expected_url: str
    ) -> None:
        assert canonicalize_track_url(submitted) == (expected_id, expected_url)

    @pytest.mark.parametrize(
        "submitted",
        [
            "spotify:track:2cGxRwrMyEAp8dEbuZaVv6",
            "https://example.invalid/track/2cGxRwrMyEAp8dEbuZaVv6",
            "https://open.spotify.com/track/not-a-spotify-id",
            "https://open.spotify.com/track/2cGxRwrMyEAp8dEbuZaVv6/extra",
        ],
    )
    def test_malformed_or_non_spotify_urls_are_rejected(self, submitted: str) -> None:
        with pytest.raises(ValidationFailedError):
            canonicalize_track_url(submitted)

    @pytest.mark.parametrize(
        "submitted",
        [
            "https://open.spotify.com/album/1DFixLWuPkv3KT3TnV35m3",
            "https://play.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M",
        ],
    )
    def test_collections_are_explicitly_rejected(self, submitted: str) -> None:
        with pytest.raises(UnsupportedEntityError):
            canonicalize_track_url(submitted)

    def test_success_is_strictly_reduced_to_a_track_reference(self) -> None:
        with respx.mock:
            route = respx.get(OEMBED_URL).mock(return_value=httpx.Response(200, json=_payload()))
            reference = SpotifyOEmbedReferenceResolver().resolve(TRACK_URL, None)

        assert route.call_count == 1
        assert route.calls[0].request.url.params["url"] == TRACK_URL
        assert reference.spotify_id == TRACK_ID
        assert reference.canonical_url == TRACK_URL
        assert reference.title == "Instant Crush"
        assert reference.thumbnail_url.startswith("https://i.scdn.co/")
        assert not hasattr(reference, "artist")
        assert not hasattr(reference, "album")
        assert not hasattr(reference, "isrc")

    def test_malformed_provider_payload_is_a_typed_provider_error(self) -> None:
        with respx.mock:
            respx.get(OEMBED_URL).mock(
                return_value=httpx.Response(
                    200,
                    json={"thumbnail_url": "https://i.scdn.co/image/reference"},
                )
            )
            with pytest.raises(ProviderResponseError) as excinfo:
                SpotifyOEmbedReferenceResolver().resolve(TRACK_URL, None)

        assert excinfo.value.context["reason"] == "invalid_response"

    def test_a_missing_thumbnail_does_not_hide_a_valid_track_reference(self) -> None:
        with respx.mock:
            respx.get(OEMBED_URL).mock(
                return_value=httpx.Response(200, json={"title": "Artwork-free track"})
            )
            reference = SpotifyOEmbedReferenceResolver().resolve(TRACK_URL, None)

        assert reference.title == "Artwork-free track"
        assert reference.thumbnail_url is None

    def test_a_not_found_track_is_not_a_match_fallback(self) -> None:
        with respx.mock:
            respx.get(OEMBED_URL).mock(return_value=httpx.Response(404))
            with pytest.raises(ProviderResponseError) as excinfo:
                SpotifyOEmbedReferenceResolver().resolve(TRACK_URL, None)

        assert excinfo.value.context == {
            "provider": "spotify_oembed",
            "reason": "not_found",
            "fallback": False,
        }

    def test_timeout_becomes_a_typed_provider_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def timeout(*_args: object, **_kwargs: object) -> httpx.Response:
            raise httpx.ReadTimeout("slow")

        monkeypatch.setattr(OutboundHttp, "request", timeout)
        with pytest.raises(ProviderResponseError) as excinfo:
            SpotifyOEmbedReferenceResolver().resolve(TRACK_URL, None)

        assert excinfo.value.context["reason"] == "timeout"


class TestSpotifyOEmbedProxyContract:
    def test_the_configured_proxy_reaches_the_one_outbound_client(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: list[str | None] = []

        def fake_build(*, proxy: str | None, **_kwargs: object) -> httpx.Client:
            captured.append(proxy)
            return _CannedClient(httpx.Response(200, json=_payload()))

        monkeypatch.setattr(outbound, "build_httpx_client", fake_build)
        SpotifyOEmbedReferenceResolver().resolve(TRACK_URL, _PROXY)

        assert captured == [_PROXY]


class _CannedClient:
    def __init__(self, response: httpx.Response) -> None:
        self._response = response

    def __enter__(self) -> _CannedClient:
        return self

    def __exit__(self, *_exc: object) -> bool:
        return False

    def request(self, *_args: object, **_kwargs: object) -> httpx.Response:
        return self._response
