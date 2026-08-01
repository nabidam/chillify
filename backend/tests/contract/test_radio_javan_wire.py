"""The narrow, offline Radio Javan wire contract used by the walking skeleton."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from chillify.domain.errors import ProviderResponseError
from chillify.infrastructure.providers.radio_javan_wire import (
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


def test_invalid_envelope_or_detail_is_a_safe_provider_error() -> None:
    with pytest.raises(ProviderResponseError):
        candidates_from_search({"mp3s": "not-an-array"})
    with pytest.raises(ProviderResponseError):
        media_url_from_detail({"id": 900002, "hq_link": "https://cdn.invalid/a.mp3"}, "900001")
