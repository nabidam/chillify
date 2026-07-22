"""Proxy fail-closed and secret masking, end to end.

Two guarantees this milestone must not regress:

- A configured proxy has no direct fallback. When the proxy fails, every client
  the policy builds was built with that proxy, so no request ever slips out to
  the destination directly, and the failure surfaces as a typed proxy error.
- A saved proxy credential or Last.fm key never appears in an API body or, once
  registered, in a Rich log line.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from chillify.domain.errors import ProxyConnectionError
from chillify.infrastructure.logging.setup import redactor
from chillify.infrastructure.security import outbound
from chillify.infrastructure.security.outbound import OutboundHttp
from tests.conftest import (
    SENTINEL_LASTFM_KEY,
    SENTINEL_PROXY_PASSWORD,
    SENTINEL_PROXY_URL,
)

pytestmark = pytest.mark.integration

SETTINGS = "/api/v1/settings"


class _RaisingClient:
    """A client whose every request fails as an unreachable proxy would."""

    def __enter__(self) -> _RaisingClient:
        return self

    def __exit__(self, *_exc: object) -> bool:
        return False

    def request(self, *_args: object, **_kwargs: object) -> httpx.Response:
        raise httpx.ConnectError("proxy unreachable")


def test_a_proxy_failure_never_falls_back_to_a_direct_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[str | None] = []

    def fake_build(*, proxy: str | None, **_kwargs: object) -> httpx.Client:
        captured.append(proxy)
        return _RaisingClient()  # type: ignore[return-value]

    monkeypatch.setattr(outbound, "build_httpx_client", fake_build)

    with pytest.raises(ProxyConnectionError):
        OutboundHttp(proxy=SENTINEL_PROXY_URL).request(
            "GET", "https://api.deezer.com/search", params={"q": "anything"}
        )

    assert captured, "the policy built no client at all"
    assert all(proxy == SENTINEL_PROXY_URL for proxy in captured)
    assert None not in captured  # never a direct-fallback client


def test_testing_a_failing_proxy_reports_connection_through_the_proxy(
    start_api,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[str | None] = []

    def fake_build(*, proxy: str | None, **_kwargs: object) -> httpx.Client:
        captured.append(proxy)
        return _RaisingClient()  # type: ignore[return-value]

    monkeypatch.setattr(outbound, "build_httpx_client", fake_build)
    client: TestClient = start_api()

    result = client.post(f"{SETTINGS}/proxy/test", json={"url": SENTINEL_PROXY_URL})

    assert result.status_code == 200
    body = result.json()
    assert body["ok"] is False
    assert body["code"] == "connection"
    assert SENTINEL_PROXY_PASSWORD not in result.text
    assert captured and all(proxy == SENTINEL_PROXY_URL for proxy in captured)


def test_a_saved_proxy_is_masked_in_every_settings_body(
    start_api,
) -> None:
    client: TestClient = start_api()

    revision = client.get(SETTINGS).json()["proxy"]["revision"]
    saved = client.patch(
        f"{SETTINGS}/proxy", json={"url": SENTINEL_PROXY_URL, "revision": revision}
    )

    assert saved.status_code == 200
    assert SENTINEL_PROXY_PASSWORD not in saved.text
    assert "proxyuser" not in saved.text  # the username is masked to a single character
    proxy = saved.json()
    assert proxy["configured"] is True
    assert proxy["masked_url"].startswith("socks5://p***@proxy.invalid")

    after = client.get(SETTINGS)
    assert SENTINEL_PROXY_PASSWORD not in after.text
    assert after.json()["proxy"]["configured"] is True


def test_a_saved_lastfm_key_is_never_echoed(
    start_api,
) -> None:
    client: TestClient = start_api()

    providers = {p["name"]: p for p in client.get(SETTINGS).json()["providers"]}
    revision = providers["lastfm"]["revision"]
    saved = client.patch(
        f"{SETTINGS}/providers/lastfm",
        json={"enabled": True, "credential": SENTINEL_LASTFM_KEY, "revision": revision},
    )

    assert saved.status_code == 200
    assert SENTINEL_LASTFM_KEY not in saved.text
    state = saved.json()
    assert state["has_credential"] is True
    assert state["configured"] is True

    assert SENTINEL_LASTFM_KEY not in client.get(SETTINGS).text


def test_saving_a_secret_registers_it_for_log_redaction(
    start_api,
) -> None:
    client: TestClient = start_api()

    revision = client.get(SETTINGS).json()["proxy"]["revision"]
    client.patch(f"{SETTINGS}/proxy", json={"url": SENTINEL_PROXY_URL, "revision": revision})

    masked = redactor().redact(f"connecting through {SENTINEL_PROXY_URL}")
    assert SENTINEL_PROXY_PASSWORD not in masked
    assert "proxyuser" not in masked


def test_a_malformed_proxy_is_refused_before_it_is_stored(
    start_api,
) -> None:
    client: TestClient = start_api()

    revision = client.get(SETTINGS).json()["proxy"]["revision"]
    rejected = client.patch(
        f"{SETTINGS}/proxy", json={"url": "ftp://nope.invalid:1", "revision": revision}
    )

    assert rejected.status_code == 422
    assert rejected.json()["error"]["code"] == "proxy_configuration_invalid"
    # Nothing was stored: the proxy is still unconfigured.
    assert client.get(SETTINGS).json()["proxy"]["configured"] is False
