"""Rich stdout logging: correlation context present, secrets absent."""

from __future__ import annotations

import io
import logging

import pytest
from rich.console import Console

from chillify.infrastructure.logging.redaction import REDACTED, RedactingFilter, SecretRedactor
from chillify.infrastructure.logging.setup import (
    SERVICE_API,
    SERVICE_WORKER,
    configure_logging,
    job_context,
    request_context,
)
from tests.conftest import SENTINEL_LASTFM_KEY, SENTINEL_PROXY_PASSWORD, SENTINEL_PROXY_URL

pytestmark = pytest.mark.unit


@pytest.fixture
def captured() -> tuple[Console, io.StringIO]:
    buffer = io.StringIO()
    return Console(file=buffer, width=200, no_color=True), buffer


class TestRecordContext:
    def test_api_records_carry_service_and_request_id(
        self, captured: tuple[Console, io.StringIO]
    ) -> None:
        console, buffer = captured
        handler = configure_logging(service=SERVICE_API, level="INFO", console=console)
        records: list[logging.LogRecord] = []
        handler.addFilter(lambda record: records.append(record) is None)

        with request_context("req-01HZ"):
            logging.getLogger("chillify.api.test").info("served request")

        assert records[0].service == SERVICE_API
        assert records[0].request_id == "req-01HZ"
        assert "req-01HZ" in buffer.getvalue()

    def test_worker_records_carry_job_id_and_phase(
        self, captured: tuple[Console, io.StringIO]
    ) -> None:
        console, buffer = captured
        handler = configure_logging(service=SERVICE_WORKER, level="INFO", console=console)
        records: list[logging.LogRecord] = []
        handler.addFilter(lambda record: records.append(record) is None)

        with job_context("job-42", phase="downloading"):
            logging.getLogger("chillify.worker.test").info("acquiring track")

        assert records[0].service == SERVICE_WORKER
        assert records[0].job_id == "job-42"
        assert records[0].phase == "downloading"
        assert "downloading" in buffer.getvalue()

    def test_context_does_not_leak_past_its_scope(
        self, captured: tuple[Console, io.StringIO]
    ) -> None:
        console, _ = captured
        handler = configure_logging(service=SERVICE_API, level="INFO", console=console)
        records: list[logging.LogRecord] = []
        handler.addFilter(lambda record: records.append(record) is None)

        with request_context("req-inner"):
            pass
        logging.getLogger("chillify.api.test").info("outside any request")

        assert records[-1].request_id is None

    def test_reconfiguring_does_not_log_the_same_failure_twice(
        self, captured: tuple[Console, io.StringIO]
    ) -> None:
        console, buffer = captured
        configure_logging(service=SERVICE_API, level="INFO", console=console)
        configure_logging(service=SERVICE_API, level="INFO", console=console)

        logging.getLogger("chillify.api.test").warning("provider unreachable")

        assert buffer.getvalue().count("provider unreachable") == 1


class TestRedaction:
    def test_registered_sentinel_secrets_never_reach_stdout(
        self, captured: tuple[Console, io.StringIO]
    ) -> None:
        console, buffer = captured
        handler = configure_logging(service=SERVICE_API, level="INFO", console=console)
        redactor = SecretRedactor([SENTINEL_PROXY_PASSWORD, SENTINEL_LASTFM_KEY])
        handler.addFilter(RedactingFilter(redactor))

        logging.getLogger("chillify.test").warning(
            "proxy test failed for %s", SENTINEL_PROXY_URL, extra={"key": SENTINEL_LASTFM_KEY}
        )

        output = buffer.getvalue()
        assert SENTINEL_PROXY_PASSWORD not in output
        assert SENTINEL_LASTFM_KEY not in output
        assert REDACTED in output

    def test_url_credentials_are_masked_without_registration(self) -> None:
        redactor = SecretRedactor()

        result = redactor.redact(f"connecting through {SENTINEL_PROXY_URL}")

        assert SENTINEL_PROXY_PASSWORD not in result
        assert "proxyuser" not in result
        assert "proxy.invalid:1080" in result

    @pytest.mark.parametrize(
        "message",
        [
            "GET /2.0/?method=track.getInfo&api_key=abcdef0123456789&artist=x",
            "authorization: Bearer abcdef0123456789",
            'config {"secret": "abcdef0123456789"}',
            "password=abcdef0123456789",
        ],
    )
    def test_sensitive_key_value_pairs_are_masked(self, message: str) -> None:
        redactor = SecretRedactor()

        result = redactor.redact(message)

        assert "abcdef0123456789" not in result
        assert REDACTED in result

    def test_nested_extra_payloads_are_redacted(self) -> None:
        redactor = SecretRedactor([SENTINEL_LASTFM_KEY])

        result = redactor.redact_value(
            {"provider": "lastfm", "attempts": [{"key": SENTINEL_LASTFM_KEY}]}
        )

        assert result == {"provider": "lastfm", "attempts": [{"key": REDACTED}]}

    def test_ordinary_text_survives_redaction(self) -> None:
        redactor = SecretRedactor([SENTINEL_LASTFM_KEY])

        assert redactor.redact("queued 3 downloads") == "queued 3 downloads"

    def test_short_values_are_not_registered(self) -> None:
        redactor = SecretRedactor(["abc"])

        assert redactor.redact("abc is a common substring") == "abc is a common substring"

    def test_redaction_failure_does_not_break_the_caller(
        self, captured: tuple[Console, io.StringIO]
    ) -> None:
        console, buffer = captured
        handler = configure_logging(service=SERVICE_API, level="INFO", console=console)

        class ExplodingRedactor(SecretRedactor):
            def redact(self, value: str) -> str:
                raise RuntimeError("redaction backend failed")

        handler.addFilter(RedactingFilter(ExplodingRedactor()))

        logging.getLogger("chillify.test").info("work continues")

        assert "redaction failed" in buffer.getvalue()
