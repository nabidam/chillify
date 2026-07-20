"""The one API error envelope.

Every failure the browser can see has this shape. `detail` is allowlisted and
redacted: no absolute path, provider body, command line, proxy credential, API
key, ciphertext, or traceback ever reaches it.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ErrorBody(BaseModel):
    code: str = Field(description="Stable machine-readable error code.")
    message: str = Field(description="Safe, operator-facing description of the failure.")
    field: str | None = Field(
        default=None, description="Request field that failed validation, when applicable."
    )
    retryable: bool = Field(description="Whether repeating the same request may succeed.")
    request_id: str = Field(description="Correlates this response with stdout logs.")
    detail: dict[str, Any] = Field(
        default_factory=dict, description="Allowlisted, redacted diagnostic context."
    )


class ErrorResponse(BaseModel):
    """The documented error envelope for every non-2xx API response."""

    error: ErrorBody


def error_payload(
    *,
    code: str,
    message: str,
    request_id: str,
    retryable: bool = False,
    field: str | None = None,
    detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return ErrorResponse(
        error=ErrorBody(
            code=code,
            message=message,
            field=field,
            retryable=retryable,
            request_id=request_id,
            detail=detail or {},
        )
    ).model_dump()
