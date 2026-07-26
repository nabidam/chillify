"""The CSRF/cross-origin-mutation control ARCHITECTURE section 13 names.

Same-origin nginx routing and the absence of a permissive CORS policy stop a
cross-site script from *reading* Chillify's response, but neither stops a
"simple request" — one whose Content-Type never triggers a CORS preflight —
from reaching a route and mutating state before the browser ever gets that
far. `CORSMiddleware` only decides whether to attach an
`Access-Control-Allow-Origin` header on the way out; the mutation underneath
it has already run.

This module runs before routing and closes that gap directly, for every
mutating method: a request naming another deployment's Origin, or carrying a
body that is neither JSON nor the one route's multipart upload, never reaches
a handler. It is deliberately a single pass over the request headers — no
body is read or buffered — so a rejection costs nothing more than an ordinary
routed request would.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from chillify.api.errors import error_payload

_MUTATING_METHODS: Final = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# The one non-JSON shape a mutation may carry: the artwork upload route's
# multipart file field. Every other route's body is JSON or nothing at all.
_ALLOWED_CONTENT_TYPES: Final = ("application/json", "multipart/form-data")

_ORIGIN_REJECTED = "origin_rejected"
_UNSUPPORTED_MEDIA_TYPE = "unsupported_media_type"


class MutationGuardMiddleware:
    """Refuse a cross-origin or non-JSON mutation before it reaches a route."""

    def __init__(self, app: ASGIApp, *, allowed_origins: Sequence[str] = ()) -> None:
        self._app = app
        # The operator's explicit extra origins, when direct API access is
        # enabled. Same-origin is always allowed and is computed per request
        # from the request's own Host header, never stored here.
        self._allowed_origins = frozenset(allowed_origins)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] not in _MUTATING_METHODS:
            await self._app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        rejection = self._origin_rejection(headers) or self._content_type_rejection(headers)
        if rejection is not None:
            code, status_code, message = rejection
            state = scope.get("state") or {}
            request_id = state.get("request_id")
            response = JSONResponse(
                status_code=status_code,
                content=error_payload(
                    code=code,
                    message=message,
                    request_id=str(request_id) if request_id else "unknown",
                    retryable=False,
                ),
            )
            await response(scope, receive, send)
            return

        await self._app(scope, receive, send)

    def _origin_rejection(self, headers: Headers) -> tuple[str, int, str] | None:
        """A mutation whose declared Origin is not this deployment.

        Absent is allowed: most non-browser clients never send it, and a
        forged Origin is the one thing a cross-site attacker cannot omit while
        still riding the browser's own request.
        """
        origin = headers.get("origin")
        if origin is None or origin in self._allowed_origins:
            return None
        host = headers.get("host")
        if host is not None:
            forwarded_proto = headers.get("x-forwarded-proto", "http")
            if origin == f"{forwarded_proto}://{host}":
                return None
        return (
            _ORIGIN_REJECTED,
            403,
            "This request's Origin is not permitted to change this deployment.",
        )

    def _content_type_rejection(self, headers: Headers) -> tuple[str, int, str] | None:
        if not _declares_a_body(headers):
            return None
        declared = headers.get("content-type", "")
        family = declared.split(";", 1)[0].strip().lower()
        if family in _ALLOWED_CONTENT_TYPES:
            return None
        return (
            _UNSUPPORTED_MEDIA_TYPE,
            415,
            "This request body must be application/json, or multipart/form-data for an upload.",
        )


def _declares_a_body(headers: Headers) -> bool:
    """True when the request announces a body, by the headers alone.

    A `DELETE` with no body sends neither header and must not be required to
    justify a `Content-Type` it has no content for.
    """
    if headers.get("transfer-encoding") is not None:
        return True
    content_length = headers.get("content-length")
    return content_length is not None and content_length != "0"
