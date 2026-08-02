"""Radio Javan failures stay scoped to its routes and never change readiness."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from chillify.composition import Composition
from chillify.domain.errors import (
    ChillifyError,
    ProviderResponseError,
    ProxyConnectionError,
    ProxyTimeoutError,
)

pytestmark = pytest.mark.integration


class _FailingRadioJavan:
    name = "radiojavan"

    def __init__(self, error: ChillifyError) -> None:
        self.error = error

    def search(self, _query: str, _limit: int, _proxy: str | None) -> tuple[object, ...]:
        raise self.error

    def browse(self, _section: str, _proxy: str | None) -> tuple[object, ...]:
        raise self.error


def test_radio_javan_provider_failure_is_scoped_and_keeps_local_surfaces_ready(
    gate_api: TestClient, gate_composition: Composition
) -> None:
    failing = _FailingRadioJavan(
        ProviderResponseError(
            "Radio Javan could not complete that request.", context={"provider": "radiojavan"}
        )
    )
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


@pytest.mark.parametrize(
    ("failure", "status_code", "code", "message"),
    [
        (
            ProxyConnectionError("Could not reach the internet through the configured proxy."),
            503,
            "proxy_connection_failed",
            "Could not reach the internet through the configured proxy.",
        ),
        (
            ProxyTimeoutError("The proxy did not respond in time."),
            504,
            "proxy_timeout",
            "The proxy did not respond in time.",
        ),
    ],
)
def test_radio_javan_proxy_failures_are_typed_scoped_and_do_not_change_readiness(
    gate_api: TestClient,
    gate_composition: Composition,
    failure: ChillifyError,
    status_code: int,
    code: str,
    message: str,
) -> None:
    failing = _FailingRadioJavan(failure)
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
        assert response.status_code == status_code
        assert response.json()["error"] == {
            "code": code,
            "message": message,
            "field": None,
            "retryable": True,
            "request_id": response.headers["X-Request-ID"],
            "detail": {},
        }
