"""NFR-11, end to end: a proxy credential or Last.fm key never leaks.

`tests/unit/test_logging.py` proves the redaction primitives — `SecretRedactor`
and `RedactingFilter` — in isolation, against a hand-built handler and buffer.
`tests/integration/test_proxy_fail_closed.py` proves the API response body
never carries a saved secret. Neither exercises the one path both share in a
real household deployment: a secret entered through the real settings API,
registered by the real composition, and then a log line emitted through the
actual process-wide handler `chillify.api.main.create_app` installs — the
handler a real `docker compose logs` reads.

This suite starts the real application, saves a secret through its real
endpoint exactly as a household would, and then confirms that any subsequent
log line naming that secret — including one whose message is folded into an
exception's own traceback rather than a `logger.info(...)` call — never
reaches the process's real stdout.
"""

from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient

from tests.conftest import SENTINEL_LASTFM_KEY, SENTINEL_PROXY_PASSWORD, SENTINEL_PROXY_URL

pytestmark = pytest.mark.integration

SETTINGS = "/api/v1/settings"


def _diagnostic_logger() -> logging.Logger:
    """A logger this suite forces a diagnostic line through.

    `migrated_environment` runs a real Alembic upgrade per test, and Alembic's
    `fileConfig` disables every logger that already exists and is not named in
    `alembic.ini` — including this one, left over from an earlier test in the
    same process. That is a property of re-running Alembic in-process across
    tests, not of the application under test, so it is undone here rather than
    weakening the assertion.
    """
    logger = logging.getLogger("chillify.test.secret_redaction")
    logger.disabled = False
    return logger


def test_a_registered_proxy_secret_is_absent_from_real_stdout(
    start_api,
    capsys: pytest.CaptureFixture[str],
) -> None:
    client: TestClient = start_api()

    # Register the secret the way a household actually does: through the
    # settings API, not by calling the redactor directly.
    revision = client.get(SETTINGS).json()["proxy"]["revision"]
    saved = client.patch(
        f"{SETTINGS}/proxy", json={"url": SENTINEL_PROXY_URL, "revision": revision}
    )
    assert saved.status_code == 200

    # A lower layer that has not internalized the masking convention logs the
    # raw value anyway. The installed filter, not the caller, is what NFR-11
    # actually depends on.
    capsys.readouterr()  # discard startup/request logging from the calls above
    _diagnostic_logger().error("forced diagnostic line naming %s", SENTINEL_PROXY_URL)

    captured = capsys.readouterr().out
    assert "forced diagnostic line" in captured  # the log line really was emitted
    assert SENTINEL_PROXY_PASSWORD not in captured
    assert "proxyuser" not in captured


def test_a_registered_proxy_secret_is_absent_from_a_rendered_traceback(
    start_api,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The Rich traceback renderer reads `record.exc_info` directly.

    An exception's own message is not passed through `record.msg`, so a naive
    filter that only redacts the message and structured extras would still
    leak a secret folded into an exception string — exactly what a raw
    `httpx`/OS-level failure embedding a proxied URL looks like.
    """
    client: TestClient = start_api()

    revision = client.get(SETTINGS).json()["proxy"]["revision"]
    saved = client.patch(
        f"{SETTINGS}/proxy", json={"url": SENTINEL_PROXY_URL, "revision": revision}
    )
    assert saved.status_code == 200

    capsys.readouterr()
    _logger = _diagnostic_logger()
    try:
        raise RuntimeError(f"could not reach the internet through {SENTINEL_PROXY_URL}")
    except RuntimeError as exc:
        _logger.exception("forced unhandled failure", exc_info=exc)

    captured = capsys.readouterr().out
    assert "forced unhandled failure" in captured
    assert "Traceback" in captured
    assert SENTINEL_PROXY_PASSWORD not in captured
    assert "proxyuser" not in captured


def test_a_registered_lastfm_key_is_absent_from_real_stdout(
    start_api,
    capsys: pytest.CaptureFixture[str],
) -> None:
    client: TestClient = start_api()

    providers = {p["name"]: p for p in client.get(SETTINGS).json()["providers"]}
    revision = providers["lastfm"]["revision"]
    saved = client.patch(
        f"{SETTINGS}/providers/lastfm",
        json={"enabled": True, "credential": SENTINEL_LASTFM_KEY, "revision": revision},
    )
    assert saved.status_code == 200

    capsys.readouterr()
    _diagnostic_logger().warning("forced diagnostic line naming key=%s", SENTINEL_LASTFM_KEY)

    captured = capsys.readouterr().out
    assert "forced diagnostic line" in captured
    assert SENTINEL_LASTFM_KEY not in captured


def test_an_unregistered_but_structurally_sensitive_value_is_still_masked(
    start_api,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The structural pass is the backstop for a secret nobody registered.

    Nothing in this test ever calls `redactor().register(...)`; the value is
    caught purely because it is shaped like a credential in free text, proving
    the two redaction passes (literal and structural) are both wired into the
    real process handler, not only into the registered-literal path the other
    tests in this module exercise.
    """
    start_api()

    capsys.readouterr()
    _diagnostic_logger().info(
        "unexpected upstream response: api_key=unregistered-example-secret-999"
    )

    captured = capsys.readouterr().out
    assert "unexpected upstream response" in captured
    assert "unregistered-example-secret-999" not in captured
