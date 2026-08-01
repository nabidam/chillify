"""Radio Javan failures stay scoped to its routes and never change readiness."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from chillify.composition import Composition
from chillify.domain.errors import ProviderResponseError

pytestmark = pytest.mark.integration


class _FailingRadioJavan:
    name = "radiojavan"

    def search(self, _query: str, _limit: int, _proxy: str | None) -> tuple[object, ...]:
        raise ProviderResponseError(
            "Radio Javan could not complete that request.", context={"provider": self.name}
        )

    def browse(self, _section: str, _proxy: str | None) -> tuple[object, ...]:
        raise ProviderResponseError(
            "Radio Javan could not complete that request.", context={"provider": self.name}
        )


def test_radio_javan_provider_failure_is_scoped_and_keeps_local_surfaces_ready(
    gate_api: TestClient, gate_composition: Composition
) -> None:
    failing = _FailingRadioJavan()
    gate_composition.registry.discovery["radiojavan"] = failing  # type: ignore[assignment]
    gate_composition.registry.browse["radiojavan"] = failing  # type: ignore[assignment]

    before = gate_api.get("/api/v1/system/health")
    search = gate_api.get("/api/v1/radio-javan/search", params={"q": "walking"})
    browse = gate_api.get("/api/v1/radio-javan/tracks", params={"section": "featured"})
    library = gate_api.get("/api/v1/library/tracks")
    after = gate_api.get("/api/v1/system/health")

    assert before.status_code == after.status_code == 200
    assert before.json() == after.json() == {"status": "ready"}
    assert library.status_code == 200
    for response in (search, browse):
        assert response.status_code == 502
        assert response.json()["error"] == {
            "code": "provider_response_invalid",
            "message": "Radio Javan could not complete that request.",
            "field": None,
            "retryable": True,
            "request_id": response.headers["X-Request-ID"],
            "detail": {"provider": "radiojavan"},
        }
