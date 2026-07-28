"""The Spotify Web API wire and shared LinkInspector contract."""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
import respx

from chillify.application.settings import InspectionMode, InspectionSettings
from chillify.domain.errors import ProviderResponseError, UnsupportedEntityError
from chillify.domain.protocols import LinkInspector
from chillify.infrastructure.providers.spotify_api import (
    TOKEN_URL,
    TRACK_URL,
    FixtureSpotifyApiInspector,
    SpotifyApiInspector,
    candidate_from_api_payload,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
TRACK_ID = "2cGxRwrMyEAp8dEbuZaVv6"
TRACK_URL_VALUE = f"https://open.spotify.com/track/{TRACK_ID}"
ALBUM_URL = "https://open.spotify.com/album/1DFixLWuPkv3KT3TnV35m3"


def _payload(name: str) -> dict[str, object]:
    return json.loads((FIXTURES / "spotify_api" / name).read_text(encoding="utf-8"))


def _production_factory(root: Path) -> LinkInspector:
    del root
    return SpotifyApiInspector(credentials=("client-id", "client-secret"))


@pytest.fixture
def fixture_root(disposable_root: Path) -> Path:
    root = disposable_root / "fixtures"
    shutil.copytree(FIXTURES, root)
    return root


@pytest.mark.contract
@pytest.mark.parametrize(
    "factory", [lambda root: FixtureSpotifyApiInspector(root), _production_factory]
)
def test_both_adapters_support_one_track_and_reject_collections(
    factory: Callable[[Path], LinkInspector], fixture_root: Path
) -> None:
    inspector = factory(fixture_root)
    assert inspector.supports(TRACK_URL_VALUE)
    assert not inspector.supports("https://www.youtube.com/watch?v=u7K72X4eo_s")
    with pytest.raises(UnsupportedEntityError):
        inspector.inspect(ALBUM_URL, None)


@pytest.mark.contract
def test_fixture_adapter_normalizes_the_documented_track_shape(fixture_root: Path) -> None:
    candidate = FixtureSpotifyApiInspector(fixture_root).inspect(TRACK_URL_VALUE, None)

    assert candidate.provider == "spotify"
    assert candidate.title == "Instant Crush"
    assert candidate.artist == "Daft Punk"
    assert candidate.album == "Random Access Memories"
    assert candidate.release_year == 2013
    assert candidate.disc_number == 1
    assert candidate.track_number == 5
    assert candidate.isrc == "USQX91300108"
    assert candidate.duration_ms == 337560
    assert candidate.artwork_url == "https://i.scdn.co/image/large"


@pytest.mark.contract
def test_missing_optional_fields_are_allowed() -> None:
    candidate = candidate_from_api_payload(
        _payload("track_missing_optional.json"),
        track_id=TRACK_ID,
        canonical_url=TRACK_URL_VALUE,
    )

    assert candidate.title == "Instant Crush"
    assert candidate.artist == "Daft Punk"
    assert candidate.album is None
    assert candidate.disc_number is None
    assert candidate.track_number is None
    assert candidate.isrc is None


@pytest.mark.contract
@respx.mock
def test_api_request_uses_client_credentials_and_caches_the_token() -> None:
    token_route = respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(
            200,
            json={"access_token": "token", "token_type": "Bearer", "expires_in": 3600},
        )
    )
    track_route = respx.get(TRACK_URL.format(TRACK_ID)).mock(
        return_value=httpx.Response(200, json=_payload("track_success.json"))
    )
    inspector = SpotifyApiInspector(credentials=("client-id", "client-secret"))

    inspector.inspect(TRACK_URL_VALUE, None)
    inspector.inspect(TRACK_URL_VALUE, None)

    assert token_route.call_count == 1
    assert track_route.call_count == 2
    assert token_route.calls[0].request.headers["authorization"].startswith("Basic ")
    assert token_route.calls[0].request.content == b"grant_type=client_credentials"
    assert track_route.calls[0].request.headers["authorization"] == "Bearer token"


@pytest.mark.contract
@respx.mock
def test_track_401_refreshes_once() -> None:
    respx.post(TOKEN_URL).mock(
        side_effect=[
            httpx.Response(200, json={"access_token": "old", "expires_in": 3600}),
            httpx.Response(200, json={"access_token": "new", "expires_in": 3600}),
        ]
    )
    track_route = respx.get(TRACK_URL.format(TRACK_ID)).mock(
        side_effect=[
            httpx.Response(401, json=_payload("token_401.json")),
            httpx.Response(200, json=_payload("track_success.json")),
        ]
    )
    candidate = SpotifyApiInspector(credentials=("id", "secret")).inspect(TRACK_URL_VALUE, None)

    assert candidate.title == "Instant Crush"
    assert track_route.call_count == 2


@pytest.mark.contract
@respx.mock
def test_404_is_not_fallback_and_429_waits_once(monkeypatch: pytest.MonkeyPatch) -> None:
    respx.post(TOKEN_URL).respond(200, json={"access_token": "token", "expires_in": 3600})
    track_route = respx.get(TRACK_URL.format(TRACK_ID)).respond(
        404, json=_payload("track_404.json")
    )
    inspector = SpotifyApiInspector(credentials=("id", "secret"))
    with pytest.raises(ProviderResponseError) as not_found:
        inspector.inspect(TRACK_URL_VALUE, None)
    assert not_found.value.context["fallback"] is False
    assert track_route.call_count == 1

    waits: list[int] = []
    monkeypatch.setattr("chillify.infrastructure.providers.spotify_api.time.sleep", waits.append)
    respx.get(TRACK_URL.format(TRACK_ID)).respond(
        429, headers={"Retry-After": "7"}, json=_payload("track_429.json")
    )
    with pytest.raises(ProviderResponseError) as rate_limited:
        inspector.inspect(TRACK_URL_VALUE, None)
    assert waits == [7]
    assert rate_limited.value.context["reason"] == "rate_limited"


@pytest.mark.contract
@respx.mock
def test_response_over_one_mib_is_refused_before_parsing() -> None:
    respx.post(TOKEN_URL).respond(200, json={"access_token": "token", "expires_in": 3600})
    respx.get(TRACK_URL.format(TRACK_ID)).respond(200, content=b"{" + b" " * (1024 * 1024) + b"}")

    with pytest.raises(ProviderResponseError) as excinfo:
        SpotifyApiInspector(credentials=("id", "secret")).inspect(TRACK_URL_VALUE, None)
    assert excinfo.value.context["reason"] == "too_large"


@pytest.mark.contract
def test_default_timeout_budget_is_below_the_fallback_bound() -> None:
    settings = InspectionSettings.create(
        mode=InspectionMode.FAST,
        timeout_spotify_s=8,
        timeout_spotdl_s=150,
        timeout_ytdlp_s=60,
    )
    assert settings.timeout_spotify_s + settings.timeout_spotdl_s < 160
