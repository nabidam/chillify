"""The one outbound HTTP policy.

Every request Chillify makes to the internet — Deezer, Last.fm, and remote
artwork — is built here and nowhere else. There is exactly one `httpx.Client`
factory. When a proxy is saved it is supplied for every HTTP, HTTPS, and SOCKS
request, and there is no second client that could reach the network directly:
the operator chose the proxy precisely so that traffic cannot escape it, and a
"fall back to a direct connection when the proxy is down" path would quietly
undo that choice. A proxy failure therefore surfaces as a typed proxy error,
never as a direct retry.

Timeouts and the bounded retry policy live here too, so an adapter describes
what it wants to fetch and never how the transport behaves under failure.
"""

from __future__ import annotations

import ipaddress
import shutil
import socket
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Final
from urllib.parse import urlsplit

import httpx
from tenacity import (
    RetryCallState,
    Retrying,
    retry_if_exception_type,
    retry_if_result,
    stop_after_attempt,
    wait_exponential_jitter,
)

from chillify.domain.errors import (
    AcquisitionCancelledError,
    AcquisitionFailedError,
    AcquisitionLimitExceededError,
    OutboundTargetRejectedError,
    ProxyAuthenticationError,
    ProxyConfigurationError,
    ProxyConnectionError,
    ProxyTimeoutError,
)
from chillify.infrastructure.logging.setup import redactor

# Schemes httpx can proxy through. SOCKS support comes from the httpx[socks]
# extra pinned in pyproject; anything else is refused before a client is built.
SUPPORTED_PROXY_SCHEMES: Final = frozenset({"http", "https", "socks5", "socks5h"})

# ARCHITECTURE section 6: 5 s connect, 15 s read, 20 s pool/write.
_TIMEOUT: Final = httpx.Timeout(connect=5.0, read=15.0, write=20.0, pool=20.0)

# At most two retries beyond the first attempt.
_MAX_ATTEMPTS: Final = 3

# Transport failures worth repeating: a reset or a timeout may be transient. A
# proxy-authentication rejection is not here — repeating it cannot help.
_RETRYABLE_EXCEPTIONS: Final = (
    httpx.ConnectError,
    httpx.ReadError,
    httpx.WriteError,
    httpx.ConnectTimeout,
    httpx.ReadTimeout,
    httpx.WriteTimeout,
    httpx.PoolTimeout,
)

# Response statuses worth repeating, per ARCHITECTURE section 6.
_RETRYABLE_STATUSES: Final = frozenset({408, 429, 500, 502, 503, 504})

_PROXY_AUTH_STATUS: Final = 407
MEDIA_MAX_BYTES: Final = 256 * 1024 * 1024
MEDIA_MIN_FREE_BYTES: Final = 512 * 1024 * 1024

# ARCHITECTURE section 13: the SSRF containment boundary. `follow_redirects`
# is only ever true for the one adapter that fetches an arbitrary provider or
# user-submitted URL (artwork), so the scheme and every resolved address —
# the initial target and every redirect hop — are checked exactly there.
# Fixed provider hostnames never redirect and pay no DNS-lookup cost for it.
_HOP_SCHEMES: Final = frozenset({"http", "https"})
_REDIRECT_STATUSES: Final = frozenset({301, 302, 303, 307, 308})
_REJECTED_TARGET_MESSAGE: Final = "That URL points to a network location Chillify will not fetch."


def _is_disallowed_address(raw: str) -> bool:
    """True for loopback, link-local, private, multicast, reserved, or unspecified."""
    try:
        address = ipaddress.ip_address(raw)
    except ValueError:
        return False
    return (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )


def default_resolver(host: str) -> Sequence[str]:
    """The production DNS resolver: every address a hostname currently resolves to.

    A lookup failure is not itself a policy violation — refusing loopback is
    about what an address *is*, not about naming a host at all — so it returns
    no addresses rather than raising, and the real connection attempt reports
    its own failure.
    """
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return ()
    return tuple({str(info[4][0]) for info in infos})


def _validate_target(url: str, *, enforce: bool, resolver: Callable[[str], Sequence[str]]) -> None:
    """Refuse a target this policy will not fetch.

    A literal IP in the URL is checked unconditionally, everywhere, since it
    costs no network round trip. The scheme and DNS-resolved addresses are
    checked only when `enforce` is set — the artwork/user-URL flow that follows
    redirects to a target this process does not otherwise control.
    """
    parts = urlsplit(url)
    if enforce and parts.scheme.lower() not in _HOP_SCHEMES:
        raise OutboundTargetRejectedError("That URL must use HTTP or HTTPS.")
    host = parts.hostname
    if not host:
        raise OutboundTargetRejectedError(_REJECTED_TARGET_MESSAGE)
    if _is_disallowed_address(host.strip("[]")):
        raise OutboundTargetRejectedError(_REJECTED_TARGET_MESSAGE)
    if enforce:
        for address in resolver(host):
            if _is_disallowed_address(address):
                raise OutboundTargetRejectedError(_REJECTED_TARGET_MESSAGE)


class ProxyDiagnosisCode(StrEnum):
    """The distinct outcomes S12 must tell apart when a proxy is tested."""

    OK = "ok"
    UNSUPPORTED_SCHEME = "unsupported_scheme"
    CONNECTION = "connection"
    AUTHENTICATION = "authentication"
    TIMEOUT = "timeout"


@dataclass(frozen=True, slots=True)
class ProxyEndpoint:
    """A parsed proxy URL, split so it can be masked without the password."""

    scheme: str
    host: str
    port: int | None
    username: str | None
    has_password: bool
    raw: str

    @property
    def masked_url(self) -> str:
        """A display form that identifies the proxy but leaks no credential.

        The scheme, host, and port stay readable so the operator recognizes
        their own proxy; the password is dropped entirely and the username is
        reduced to a single leading character, since a username is itself half
        of a credential.
        """
        authority = self.host if self.port is None else f"{self.host}:{self.port}"
        if self.username:
            masked_user = f"{self.username[0]}***@"
            return f"{self.scheme}://{masked_user}{authority}"
        return f"{self.scheme}://{authority}"


@dataclass(frozen=True, slots=True)
class ProxyDiagnosis:
    """One proxy-test result, safe to return verbatim to the browser."""

    ok: bool
    code: ProxyDiagnosisCode
    message: str


def parse_proxy(raw: str) -> ProxyEndpoint:
    """Split and validate a submitted proxy URL.

    A malformed URL or an unsupported scheme is a submitted value that breaks a
    documented rule, so it is refused here before any client is built. The
    error names the rule, never the credential the URL may carry.
    """
    candidate = raw.strip()
    if not candidate:
        raise ProxyConfigurationError("A proxy URL is required.", field="url")
    parts = urlsplit(candidate)
    scheme = parts.scheme.lower()
    if scheme not in SUPPORTED_PROXY_SCHEMES:
        raise ProxyConfigurationError(
            "The proxy scheme must be one of http, https, socks5, or socks5h.",
            field="url",
        )
    if not parts.hostname:
        raise ProxyConfigurationError("The proxy URL must include a host.", field="url")
    return ProxyEndpoint(
        scheme=scheme,
        host=parts.hostname,
        port=parts.port,
        username=parts.username or None,
        has_password=parts.password is not None,
        raw=candidate,
    )


@dataclass(frozen=True, slots=True)
class OutboundHttp:
    """The bound outbound policy for one process.

    `proxy` is the saved proxy URL, or None when the household reaches the
    internet directly. It is validated and its credential registered for
    redaction the first time a client is opened, so no proxy password can be
    logged before its first use.
    """

    proxy: str | None = None
    follow_redirects: bool = False
    max_redirects: int = 3
    # Overridable only so a test can replace real DNS with a fixed table; the
    # default is the one resolver production ever uses.
    resolver: Callable[[str], Sequence[str]] = field(default=default_resolver)

    def _endpoint(self) -> ProxyEndpoint | None:
        if self.proxy is None:
            return None
        endpoint = parse_proxy(self.proxy)
        if endpoint.has_password or endpoint.username:
            # Register before any request can log the URL. `register` ignores
            # short values, so the raw URL is registered too as a whole.
            redactor().register(endpoint.raw)
        return endpoint

    def open(self) -> httpx.Client:
        """Build the one client this policy allows, always through the proxy.

        Redirects are never left to httpx: `request` walks them itself so the
        SSRF policy can validate every hop before it is fetched, not only the
        first. The client therefore never follows one on its own.
        """
        endpoint = self._endpoint()
        return build_httpx_client(
            proxy=endpoint.raw if endpoint is not None else None,
            timeout=_TIMEOUT,
            follow_redirects=False,
            max_redirects=self.max_redirects,
        )

    def request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """Perform one request under the retry, redirect, and proxy policy.

        A transport failure while a proxy is configured is translated into a
        typed proxy error and never retried directly against the destination.
        Retryable statuses are exhausted and the final response is returned for
        the adapter to interpret; a `4xx` input error is returned unretried. The
        initial target and every redirect hop are validated against the SSRF
        policy before they are fetched.
        """
        proxy_configured = self.proxy is not None
        with self.open() as client:
            try:
                return self._follow(client, method, url, params, headers)
            except httpx.ProxyError as exc:
                raise _proxy_error_for(exc, proxy_configured) from exc
            except (
                httpx.ConnectTimeout,
                httpx.ReadTimeout,
                httpx.WriteTimeout,
                httpx.PoolTimeout,
            ) as exc:
                if proxy_configured:
                    raise ProxyTimeoutError(
                        "The proxy did not respond in time.",
                    ) from exc
                raise
            except (httpx.ConnectError, httpx.ReadError, httpx.WriteError) as exc:
                if proxy_configured:
                    raise ProxyConnectionError(
                        "Could not reach the internet through the configured proxy.",
                    ) from exc
                raise

    def _follow(
        self,
        client: httpx.Client,
        method: str,
        url: str,
        params: dict[str, str] | None,
        headers: dict[str, str] | None,
    ) -> httpx.Response:
        """Fetch `url`, validating and following redirects up to `max_redirects`.

        Every hop is validated with the same `enforce` flag as the first: only
        the adapter that opted into `follow_redirects` pays for scheme and DNS
        checks, and it pays them on every hop a server hands it, not only the
        one it named.
        """
        target = url
        query = params
        hops = 0
        while True:
            _validate_target(target, enforce=self.follow_redirects, resolver=self.resolver)

            def send(hop: str = target, hop_query: dict[str, str] | None = query) -> httpx.Response:
                # Bound as defaults, evaluated fresh each pass through the loop,
                # so a retry of this hop never accidentally sends a later one.
                return client.request(method, hop, params=hop_query, headers=headers)

            response = _with_retries(send)
            if not self.follow_redirects or response.status_code not in _REDIRECT_STATUSES:
                return response
            location = response.headers.get("location")
            if not location:
                return response
            if hops >= self.max_redirects:
                response.close()
                raise OutboundTargetRejectedError(
                    "That URL required more redirects than are allowed."
                )
            hops += 1
            target = str(httpx.URL(target).join(location))
            # The original query belongs to the first hop only; a redirect names
            # its own complete target.
            query = None

    def probe(self, override: str | None = None) -> ProxyDiagnosis:
        """Test the saved proxy, or an operator-supplied one, without leaking it.

        This never bypasses the proxy: a successful result means the request
        went through it, and every failure names the distinct cause S12 shows
        rather than suggesting a direct connection.
        """
        target = override if override is not None else self.proxy
        if target is None:
            return ProxyDiagnosis(
                ok=True,
                code=ProxyDiagnosisCode.OK,
                message="No proxy is configured; Chillify reaches the internet directly.",
            )
        try:
            endpoint = parse_proxy(target)
        except ProxyConfigurationError as exc:
            return ProxyDiagnosis(
                ok=False, code=ProxyDiagnosisCode.UNSUPPORTED_SCHEME, message=exc.message
            )
        if endpoint.has_password or endpoint.username:
            redactor().register(endpoint.raw)
        policy = OutboundHttp(proxy=endpoint.raw)
        try:
            response = policy.request("HEAD", "https://api.deezer.com/")
        except ProxyAuthenticationError as exc:
            return ProxyDiagnosis(
                ok=False, code=ProxyDiagnosisCode.AUTHENTICATION, message=exc.message
            )
        except ProxyTimeoutError as exc:
            return ProxyDiagnosis(ok=False, code=ProxyDiagnosisCode.TIMEOUT, message=exc.message)
        except ProxyConnectionError as exc:
            return ProxyDiagnosis(ok=False, code=ProxyDiagnosisCode.CONNECTION, message=exc.message)
        if response.status_code == _PROXY_AUTH_STATUS:
            return ProxyDiagnosis(
                ok=False,
                code=ProxyDiagnosisCode.AUTHENTICATION,
                message="The proxy rejected the supplied credentials.",
            )
        return ProxyDiagnosis(
            ok=True,
            code=ProxyDiagnosisCode.OK,
            message="The proxy accepted a test request.",
        )

    def stream_to_file(
        self,
        url: str,
        target: Path,
        *,
        headers: dict[str, str],
        cancelled: Callable[[], bool],
        progress: Callable[[float | None], None],
        max_bytes: int = MEDIA_MAX_BYTES,
        min_free_bytes: int = MEDIA_MIN_FREE_BYTES,
    ) -> int:
        """Stream an HTTPS response into ``target`` under the outbound policy.

        Unlike ``request``, this never materializes the response body.  Each
        redirect target is checked before it is opened, and every error removes
        the partial file so a retry starts from a known state.
        """
        if shutil.disk_usage(target.parent).free < min_free_bytes:
            raise AcquisitionLimitExceededError("There is not enough free space to download audio.")
        target.unlink(missing_ok=True)
        current = url
        hops = 0
        try:
            with self.open() as client:
                while True:
                    _validate_target_https(current, resolver=self.resolver)
                    with client.stream("GET", current, headers=headers) as response:
                        if response.status_code in _REDIRECT_STATUSES:
                            location = response.headers.get("location")
                            if location is None or hops >= self.max_redirects:
                                raise AcquisitionFailedError(
                                    "Radio Javan could not download that audio."
                                )
                            current = str(httpx.URL(current).join(location))
                            hops += 1
                            continue
                        if response.status_code >= 400:
                            raise AcquisitionFailedError(
                                "Radio Javan could not download that audio."
                            )
                        declared = _content_length(response.headers.get("content-length"))
                        if declared is not None and declared > max_bytes:
                            raise AcquisitionLimitExceededError(
                                "The audio file is larger than Chillify can download."
                            )
                        written = 0
                        with target.open("wb") as output:
                            for chunk in response.iter_bytes():
                                if cancelled():
                                    raise AcquisitionCancelledError("That download was cancelled.")
                                written += len(chunk)
                                if written > max_bytes:
                                    raise AcquisitionLimitExceededError(
                                        "The audio file is larger than Chillify can download."
                                    )
                                output.write(chunk)
                                progress(None if declared is None else written / declared * 100.0)
                        if written == 0:
                            raise AcquisitionFailedError(
                                "Radio Javan returned an empty audio file."
                            )
                        return written
        except AcquisitionCancelledError, AcquisitionFailedError, AcquisitionLimitExceededError:
            target.unlink(missing_ok=True)
            raise
        except httpx.ProxyError as exc:
            target.unlink(missing_ok=True)
            raise _proxy_error_for(exc, self.proxy is not None) from exc
        except httpx.HTTPError as exc:
            target.unlink(missing_ok=True)
            raise AcquisitionFailedError("Radio Javan could not download that audio.") from exc


def _content_length(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value)
    except ValueError:
        return None
    return parsed if parsed >= 0 else None


def _validate_target_https(url: str, *, resolver: Callable[[str], Sequence[str]]) -> None:
    if urlsplit(url).scheme.lower() != "https":
        raise OutboundTargetRejectedError("That URL must use HTTPS.")
    _validate_target(url, enforce=True, resolver=resolver)


def build_httpx_client(
    *,
    proxy: str | None,
    timeout: httpx.Timeout,
    follow_redirects: bool,
    max_redirects: int,
) -> httpx.Client:
    """Construct the one client kind this module allows.

    Isolated as a module function so a test can observe the `proxy` every client
    is built with and prove no direct-fallback client is ever created, without
    replacing httpx globally and breaking the in-process test client.
    """
    return httpx.Client(
        proxy=proxy,
        timeout=timeout,
        follow_redirects=follow_redirects,
        max_redirects=max_redirects,
    )


def _proxy_error_for(
    exc: httpx.ProxyError, proxy_configured: bool
) -> httpx.ProxyError | ProxyConnectionError | ProxyAuthenticationError:
    """A proxy tunnel failure. 407 is authentication; everything else is reach."""
    if not proxy_configured:
        return exc
    message = str(exc)
    if str(_PROXY_AUTH_STATUS) in message:
        return ProxyAuthenticationError("The proxy rejected the supplied credentials.")
    return ProxyConnectionError("Could not reach the internet through the configured proxy.")


def _with_retries(send: Callable[[], httpx.Response]) -> httpx.Response:
    """Run `send` under the bounded retry policy and return its response.

    Retryable transport exceptions are re-raised after exhaustion for the
    caller to translate; a retryable status is exhausted and the final response
    returned so the adapter decides what a persistent `5xx` means.
    """
    retrying = Retrying(
        stop=stop_after_attempt(_MAX_ATTEMPTS),
        wait=wait_exponential_jitter(initial=0.1, max=2.0),
        retry=(
            retry_if_exception_type(_RETRYABLE_EXCEPTIONS) | retry_if_result(_is_retryable_response)
        ),
        # On exhaustion, re-raise the last transport exception for the caller to
        # translate, or return the last response so the adapter interprets a
        # persistent retryable status itself. Without this, tenacity would wrap
        # a status-based exhaustion in a RetryError, which no caller expects.
        retry_error_callback=_final_outcome,
    )
    return retrying(send)


def _final_outcome(retry_state: RetryCallState) -> httpx.Response:
    outcome = retry_state.outcome
    assert outcome is not None  # a callback only runs after at least one attempt
    if outcome.failed:
        raise outcome.exception()  # type: ignore[misc]
    response: httpx.Response = outcome.result()
    return response


def _is_retryable_response(response: httpx.Response) -> bool:
    return response.status_code in _RETRYABLE_STATUSES
