"""The narrow, offline Radio Javan wire contract used by the walking skeleton."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from chillify.domain.errors import ProviderResponseError
from chillify.domain.jobs import JobPhase
from chillify.domain.protocols import TrackCandidate
from chillify.infrastructure.providers.radio_javan import (
    _JSON_MAX_BYTES,
    RadioJavanAcquisitionProvider,
    _json_response,
)
from chillify.infrastructure.providers.radio_javan_wire import (
    candidates_from_browse,
    candidates_from_search,
    media_url_from_detail,
)

pytestmark = pytest.mark.contract

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "providers"


def _fixture(name: str) -> object:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_search_normalizes_only_identified_mp3_rows() -> None:
    candidates = candidates_from_search(_fixture("radiojavan_search.json"))

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.provider == "radiojavan"
    assert candidate.source_id == "900001"
    assert candidate.source_url == "https://play.radiojavan.com/song/900001"
    assert candidate.acquisition_locator == "900001"
    assert candidate.is_playable is False


def test_detail_requires_the_requested_id_and_uses_hq_first() -> None:
    assert media_url_from_detail(_fixture("radiojavan_detail.json"), "900001") == (
        "https://cdn.radiojavan.test/audio/900001.mp3"
    )


def test_browse_normalizes_a_first_page_and_skips_malformed_rows() -> None:
    candidates = candidates_from_browse(_fixture("radiojavan_featured.json"))

    assert [candidate.title for candidate in candidates] == ["Featured Fixture"]
    assert candidates[0].source_id == "900002"


def test_invalid_envelope_or_detail_is_a_safe_provider_error() -> None:
    with pytest.raises(ProviderResponseError):
        candidates_from_search({"mp3s": "not-an-array"})
    with pytest.raises(ProviderResponseError):
        candidates_from_browse({"mp3s": []})
    with pytest.raises(ProviderResponseError):
        media_url_from_detail({"id": 900002, "hq_link": "https://cdn.invalid/a.mp3"}, "900001")


def test_declared_oversized_json_is_rejected_without_reading_the_body() -> None:
    response = httpx.Response(
        200,
        headers={"content-length": str(_JSON_MAX_BYTES + 1)},
        content=b"{}",
    )

    with pytest.raises(ProviderResponseError):
        _json_response(response)


def test_valid_non_mp3_is_converted_and_reports_the_phase_only_for_conversion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "work"
    workspace.mkdir()
    source = workspace / "radio-javan.download"
    source.write_bytes(b"valid non-mp3")
    converted = workspace / "radio-javan.mp3"
    phases: list[JobPhase] = []

    class _Stream:
        def request_limited_bytes(self, *_args: object, **_kwargs: object) -> tuple[int, bytes]:
            return 200, b"{}"

        def stream_to_file(self, _url: str, target: Path, **kwargs: object) -> int:
            target.write_bytes(source.read_bytes())
            progress = kwargs["progress"]
            assert callable(progress)
            progress(100.0)
            return target.stat().st_size

    monkeypatch.setattr(
        "chillify.infrastructure.providers.radio_javan.OutboundHttp",
        lambda **_kwargs: _Stream(),
    )
    monkeypatch.setattr(
        "chillify.infrastructure.providers.radio_javan.media_needs_conversion",
        lambda _path: True,
    )

    def convert(input_path: Path, output_path: Path, *, provider: str) -> tuple[Path, int]:
        assert input_path == source
        output_path.write_bytes(b"converted mp3")
        return output_path, 1234

    provider = RadioJavanAcquisitionProvider(converter=convert)
    candidate = TrackCandidate(
        provider="radiojavan",
        source_id="900001",
        source_url="https://rj.app/song/900001",
        title="Fixture",
        artist="Artist",
        album=None,
        release_year=None,
        disc_number=None,
        track_number=None,
        duration_ms=None,
        isrc=None,
        artwork_url=None,
        acquisition_locator="900001",
        raw_fingerprint=None,
    )

    # The detail response itself is intentionally patched: this contract tests
    # the acquired-media seam rather than Radio Javan's independently covered wire parser.
    monkeypatch.setattr(
        "chillify.infrastructure.providers.radio_javan._request_json",
        lambda *_args, **_kwargs: {"id": 900001, "hq_link": "https://cdn.radiojavan.test/audio"},
    )
    monkeypatch.setattr(
        "chillify.infrastructure.providers.radio_javan.media_url_from_detail",
        lambda _payload, _source_id: "https://cdn.radiojavan.test/audio",
    )

    artifact = provider.acquire(
        candidate, str(workspace), None, lambda phase, _percent: phases.append(phase), lambda: False
    )

    assert artifact.location == str(converted)
    assert artifact.duration_ms == 1234
    assert phases == [JobPhase.DOWNLOADING, JobPhase.CONVERTING]
