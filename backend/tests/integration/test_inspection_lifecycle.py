"""The tracked link-inspection lifecycle at the API/application boundary."""

from __future__ import annotations

import time
from dataclasses import dataclass

import pytest

from chillify.api.routes.links import cancel_inspection, inspect_link, stream_inspection
from chillify.api.schemas.links import LinkInspectionRequest
from chillify.application.inspection import InspectionService
from chillify.composition import Composition
from chillify.domain.errors import AcquisitionCancelledError, RecordNotFoundError
from chillify.domain.protocols import CancelledCallback, TrackCandidate

pytestmark = pytest.mark.integration

TRACK_URL = "https://open.spotify.com/track/2cGxRwrMyEAp8dEbuZaVv6"


def _wait_for_terminal(service: InspectionService, inspection_id: str) -> list[str]:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        frames = list(service.event_frames(inspection_id))
        if frames and '"terminal":true' in frames[-1]:
            return frames
        time.sleep(0.02)
    raise AssertionError("inspection did not reach a terminal event")


def test_spotify_inspection_is_accepted_and_streams_named_terminal_events(
    gate_composition: Composition,
) -> None:
    service = gate_composition.inspection_service()
    accepted = inspect_link(LinkInspectionRequest(url=TRACK_URL), service)
    assert accepted.inspection_id
    assert accepted.phase == "reading_spotify"

    frames = _wait_for_terminal(service, accepted.inspection_id)
    assert '"phase":"done"' in frames[-1]
    assert '"terminal":true' in frames[-1]
    assert '"result":' in frames[-1]
    assert '"elapsed_ms":' in frames[-1]


@dataclass(frozen=True, slots=True)
class SlowInspector:
    name: str = "spotify_api"

    def supports(self, url: str) -> bool:
        return url == TRACK_URL

    def inspect(
        self,
        url: str,
        proxy: str | None,
        *,
        cancelled: CancelledCallback | None = None,
    ) -> TrackCandidate:
        del proxy
        while cancelled is None or not cancelled():
            time.sleep(0.02)
        raise AcquisitionCancelledError("cancelled")


def test_delete_cancels_a_slow_inspection_and_the_route_returns_204(
    gate_composition: Composition,
) -> None:
    object.__setattr__(gate_composition.registry, "spotify_api", SlowInspector())
    service = gate_composition.inspection_service()
    accepted = inspect_link(LinkInspectionRequest(url=TRACK_URL), service)

    cancel_response = cancel_inspection(accepted.inspection_id, service)
    assert cancel_response.status_code == 204

    frames = _wait_for_terminal(service, accepted.inspection_id)
    assert '"phase":"cancelled"' in frames[-1]
    assert '"terminal":true' in frames[-1]
    # The durable terminal event is emitted at DELETE time; give the
    # cooperative adapter a moment to unwind before the disposable fixture is
    # torn down.
    time.sleep(0.2)


def test_unknown_or_expired_inspection_ids_return_404(
    gate_composition: Composition,
) -> None:
    service = gate_composition.inspection_service()
    with pytest.raises(RecordNotFoundError):
        stream_inspection("00000000-0000-7000-8000-000000000000", service)
