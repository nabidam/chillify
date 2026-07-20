"""The closed set of domain errors.

Every failure the browser can see originates here or is translated into one of
these at an infrastructure boundary. Each error carries a stable code, a safe
message, its retryability, and an allowlisted context whose values are
primitives only — never a path, provider body, command line, or credential.

ARCHITECTURE section 11 enumerates the full closed set; the members below are
the ones this milestone's chunks actually raise. Adding a member is a
deliberate contract change, not an incidental one.
"""

from __future__ import annotations

from typing import ClassVar

# Values allowed inside an error context. Anything richer would eventually
# smuggle a provider payload or a filesystem path into an API response.
ContextValue = str | int | bool


class ChillifyError(Exception):
    """Base class for every closed, typed domain failure."""

    code: ClassVar[str] = "internal_error"
    status_code: ClassVar[int] = 500
    retryable: ClassVar[bool] = False

    def __init__(
        self,
        message: str,
        *,
        field: str | None = None,
        context: dict[str, ContextValue] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.field = field
        self.context: dict[str, ContextValue] = dict(context or {})


class ValidationFailedError(ChillifyError):
    """A submitted value violates a documented domain rule."""

    code = "validation_failed"
    status_code = 422
    retryable = False


class DuplicateRecordError(ChillifyError):
    """A uniqueness invariant already holds for another record."""

    code = "duplicate_record"
    status_code = 409
    retryable = False


class RecordNotFoundError(ChillifyError):
    """The addressed record does not exist."""

    code = "record_not_found"
    status_code = 404
    retryable = False


class UnsafeMediaPathError(ChillifyError):
    """A stored relative path does not resolve inside its managed root.

    This is corruption or tampering, never ordinary input: the message names no
    path, and the condition is logged with the track ID alone.
    """

    code = "unsafe_media_path"
    status_code = 500
    retryable = False


class TrackFileMissingError(ChillifyError):
    """The database knows the track but its managed file is gone."""

    code = "track_file_missing"
    status_code = 410
    retryable = False


class UnsupportedEntityError(ChillifyError):
    """The submitted source names something Chillify does not acquire."""

    code = "unsupported_entity"
    status_code = 400
    retryable = False


class ProviderDisabledError(ChillifyError):
    """The provider the request needs is switched off or not bound."""

    code = "provider_disabled"
    status_code = 503
    retryable = False


class ProviderResponseError(ChillifyError):
    """A provider answered with something outside its documented contract.

    The message names the provider and nothing else: the response body itself
    is exactly the thing that must not be echoed back.
    """

    code = "provider_response_invalid"
    status_code = 502
    retryable = True


class QueueUnavailableError(ChillifyError):
    """Redis could not accept the dispatch. The durable job survives regardless."""

    code = "queue_unavailable"
    status_code = 503
    retryable = True


class AcquisitionFailedError(ChillifyError):
    """An adapter could not produce one valid MP3 for the candidate.

    This is recorded on the job rather than returned to a request, so its safe
    message is written for the Downloads screen.
    """

    code = "acquisition_failed"
    status_code = 502
    retryable = True


class AcquisitionCancelledError(ChillifyError):
    """The person asked to cancel while an adapter was working.

    It is a closed domain value rather than a control-flow exception from
    nowhere: the worker has to tell "stopped on request" apart from "failed",
    and the Downloads screen shows the two differently.
    """

    code = "acquisition_cancelled"
    status_code = 409
    retryable = False


class StorageUnwritableError(ChillifyError):
    """The managed media root refused a write the acquisition needed."""

    code = "storage_unwritable"
    status_code = 503
    retryable = True
