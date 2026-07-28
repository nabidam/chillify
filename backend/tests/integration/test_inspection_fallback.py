"""InspectionPolicy integration cases for ordering and named fallback."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from chillify.application.inspection import InspectionPolicy
from chillify.application.settings import InspectionMode, InspectionSettings
from chillify.domain.errors import ProviderResponseError
from chillify.domain.protocols import TrackCandidate

pytestmark = pytest.mark.integration

TRACK_URL = "https://open.spotify.com/track/2cGxRwrMyEAp8dEbuZaVv6"


def _candidate(provider: str) -> TrackCandidate:
    return TrackCandidate(
        provider=provider,
        source_id="2cGxRwrMyEAp8dEbuZaVv6",
        source_url=TRACK_URL,
        title="Instant Crush",
        artist="Daft Punk",
        album="Random Access Memories",
        release_year=2013,
        disc_number=1,
        track_number=5,
        duration_ms=337560,
        isrc="USQX91300108",
        artwork_url="https://i.scdn.co/image/large",
        acquisition_locator=TRACK_URL,
        raw_fingerprint=None,
    )


@dataclass
class _StubInspector:
    name: str
    candidate: TrackCandidate | None = None
    error: ProviderResponseError | None = None
    calls: list[str] = field(default_factory=list)

    def supports(self, url: str) -> bool:
        return url == TRACK_URL

    def inspect(self, url: str, proxy: str | None) -> TrackCandidate:
        del proxy
        self.calls.append(url)
        if self.error is not None:
            raise self.error
        assert self.candidate is not None
        return self.candidate


def _settings(mode: InspectionMode = InspectionMode.FAST) -> InspectionSettings:
    return InspectionSettings.create(
        mode=mode,
        timeout_spotify_s=8,
        timeout_spotdl_s=150,
        timeout_ytdlp_s=60,
    )


def test_fast_mode_uses_spotify_and_thorough_mode_skips_it() -> None:
    spotify = _StubInspector("spotify_api", candidate=_candidate("spotify"))
    spotdl = _StubInspector("spotdl", candidate=_candidate("spotdl"))
    policy = InspectionPolicy(spotify_api=spotify, spotdl=spotdl)

    assert policy.inspect(TRACK_URL, InspectionMode.FAST, _settings()).provider == "spotify"
    assert policy.inspect(TRACK_URL, InspectionMode.THOROUGH, _settings()).provider == "spotdl"
    assert len(spotify.calls) == 1
    assert len(spotdl.calls) == 1


def test_expected_spotify_failure_falls_back_to_spotdl() -> None:
    spotify = _StubInspector(
        "spotify_api",
        error=ProviderResponseError(
            "Spotify credentials are not configured.",
            context={
                "provider": "spotify_api",
                "reason": "credentials_missing",
                "fallback": True,
            },
        ),
    )
    spotdl = _StubInspector("spotdl", candidate=_candidate("spotdl"))

    result = InspectionPolicy(spotify_api=spotify, spotdl=spotdl).inspect(
        TRACK_URL, InspectionMode.FAST, _settings()
    )

    assert result.provider == "spotdl"
    assert spotify.calls == [TRACK_URL]
    assert spotdl.calls == [TRACK_URL]


def test_not_found_failure_does_not_fall_back() -> None:
    spotify = _StubInspector(
        "spotify_api",
        error=ProviderResponseError(
            "Spotify could not find that track.",
            context={"provider": "spotify_api", "reason": "not_found", "fallback": False},
        ),
    )
    spotdl = _StubInspector("spotdl", candidate=_candidate("spotdl"))

    with pytest.raises(ProviderResponseError):
        InspectionPolicy(spotify_api=spotify, spotdl=spotdl).inspect(
            TRACK_URL, InspectionMode.FAST, _settings()
        )
    assert spotdl.calls == []
