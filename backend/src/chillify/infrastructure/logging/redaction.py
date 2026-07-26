"""Secret redaction for the Rich stdout logging pipeline.

Redaction runs as a logging filter, so it applies to every record regardless of
which layer emitted it. Two independent passes protect against different
mistakes: registered literal values catch a secret that was interpolated into a
message, and structural patterns catch credentials embedded in a URL or query
string that nobody thought to register.

A logging failure must never fail application work, so every pass is total: it
either redacts or leaves the value alone, and never raises.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable, Mapping
from typing import Any, Final

REDACTED: Final = "***"

# Credentials inside a URL authority: scheme://user:password@host
_URL_CREDENTIALS: Final = re.compile(
    r"(?P<scheme>[a-z][a-z0-9+.\-]*://)(?P<user>[^:/@\s]+)(?::(?P<password>[^@/\s]*))?@",
    re.IGNORECASE,
)

# Sensitive query parameters and key/value pairs in free text.
_SENSITIVE_KEYS: Final = (
    "api_key",
    "apikey",
    "api-key",
    "secret_key",
    "secret",
    "password",
    "passwd",
    "token",
    "authorization",
    "proxy_password",
    "sk",
)
_KEY_VALUE: Final = re.compile(
    r"(?P<key>\b(?:" + "|".join(re.escape(key) for key in _SENSITIVE_KEYS) + r")\b)"
    # A JSON key carries its own closing quote before the separator.
    r"(?P<quote>[\"']?)"
    r"(?P<separator>\s*[=:]\s*)"
    # Quoted values, HTTP auth schemes, then the bare-token fallback.
    r"(?P<value>\"[^\"]*\"|'[^']*'|(?:Bearer|Basic|Token|Digest)\s+\S+|[^\s&,;)\]}\"']+)",
    re.IGNORECASE,
)

# The shortest literal worth registering. Below this, replacement would corrupt
# ordinary text more often than it would protect a secret.
_MINIMUM_LITERAL_LENGTH: Final = 6


class SecretRedactor:
    """Redacts registered literals and structurally sensitive values."""

    def __init__(self, secrets: Iterable[str] = ()) -> None:
        self._literals: set[str] = set()
        for secret in secrets:
            self.register(secret)

    def register(self, secret: str | None) -> None:
        """Register a literal secret. Short or empty values are ignored."""
        if secret and len(secret) >= _MINIMUM_LITERAL_LENGTH:
            self._literals.add(secret)

    def clear(self) -> None:
        self._literals.clear()

    def redact(self, value: str) -> str:
        # Longest first so a secret containing another secret is fully replaced.
        for literal in sorted(self._literals, key=len, reverse=True):
            value = value.replace(literal, REDACTED)
        value = _URL_CREDENTIALS.sub(_mask_url_credentials, value)
        return _KEY_VALUE.sub(
            lambda match: f"{match['key']}{match['quote']}{match['separator']}{REDACTED}",
            value,
        )

    def redact_value(self, value: Any) -> Any:
        """Redact recursively through the containers that appear in log extras."""
        if isinstance(value, str):
            return self.redact(value)
        if isinstance(value, Mapping):
            return {key: self.redact_value(item) for key, item in value.items()}
        if isinstance(value, (list, tuple, set)):
            rebuilt = [self.redact_value(item) for item in value]
            return type(value)(rebuilt) if not isinstance(value, set) else set(rebuilt)
        return value


def _mask_url_credentials(match: re.Match[str]) -> str:
    """Keep the scheme and host readable; remove the identity entirely.

    The username is masked too: a proxy username is itself a credential half and
    is enough to identify an operator account.
    """
    if match["password"] is None:
        return f"{match['scheme']}{REDACTED}@"
    return f"{match['scheme']}{REDACTED}:{REDACTED}@"


# Record attributes owned by logging itself; anything else is caller context.
_RESERVED_ATTRIBUTES: Final = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "message",
        "module",
        "msecs",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "taskName",
        "thread",
        "threadName",
    }
)


class RedactingFilter(logging.Filter):
    """Applies a `SecretRedactor` to a record's message, args, and extras."""

    def __init__(self, redactor: SecretRedactor) -> None:
        super().__init__()
        self._redactor = redactor

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            self._apply(record)
        except Exception:
            record.msg = "log record suppressed: redaction failed"
            record.args = ()
        return True

    def _apply(self, record: logging.LogRecord) -> None:
        if isinstance(record.msg, str):
            record.msg = self._redactor.redact(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(self._redactor.redact_value(arg) for arg in record.args)
        elif isinstance(record.args, Mapping):
            record.args = self._redactor.redact_value(dict(record.args))
        for name, value in list(record.__dict__.items()):
            if name not in _RESERVED_ATTRIBUTES:
                record.__dict__[name] = self._redactor.redact_value(value)
        if record.exc_info:
            record.exc_info = self._redact_exc_info(record.exc_info)

    def _redact_exc_info(
        self, exc_info: tuple[type[BaseException], BaseException, Any] | tuple[None, None, None]
    ) -> Any:
        """Redact the exception's own message before Rich renders its traceback.

        `exc_info` is excluded from the generic attribute pass above (it is
        logging's own bookkeeping, not caller context), but a handler with
        `rich_tracebacks=True` renders the exception's message straight out of
        it. An exception built from a raw secret-bearing string — an httpx or
        OS error embedding a proxied URL, for instance — would otherwise reach
        stdout through the traceback even though the plain message pass above
        catches the same text everywhere else it can appear.
        """
        exc_type, exc_value, exc_tb = exc_info
        if exc_value is None or exc_type is None:
            return exc_info
        original = str(exc_value)
        redacted = self._redactor.redact(original)
        if redacted == original:
            return exc_info
        try:
            replacement: BaseException = exc_type(redacted)
        except Exception:
            replacement = RuntimeError(redacted)
        replacement.__traceback__ = exc_tb
        replacement.__cause__ = exc_value.__cause__
        replacement.__context__ = exc_value.__context__
        return (type(replacement), replacement, exc_tb)
