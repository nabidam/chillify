"""Download request and inspection routes.

A request here does two things and in this order: it commits a durable job, and
only then tells the queue about it. Everything the Downloads screen shows comes
back out of that durable record, never out of what the request happened to
know.
"""

from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status
from fastapi.responses import JSONResponse

from chillify.api.dependencies import get_download_service, get_idempotency_guard
from chillify.api.schemas.common import PageModel
from chillify.api.schemas.downloads import (
    CancelRequestModel,
    DownloadRequestModel,
    JobDetailModel,
    JobModel,
    JobStateLiteral,
)
from chillify.application.downloads import DownloadService, IdempotencyGuard
from chillify.domain.jobs import JobId, JobState, SourceType
from chillify.infrastructure.db.repositories import JOB_PAGE_LIMIT_DEFAULT, JOB_PAGE_LIMIT_MAX

router = APIRouter(tags=["downloads"])

# The idempotency scope includes the method and route family, so one key cannot
# authorize a mutation on a different resource.
_DOWNLOAD_SCOPE = "POST /downloads"
_RETRY_SCOPE = "POST /downloads/retry"


@router.post(
    "/downloads",
    response_model=JobModel,
    status_code=status.HTTP_201_CREATED,
    summary="Queue one acquisition",
)
async def create_download(
    request: Request,
    submission: DownloadRequestModel,
    downloads: Annotated[DownloadService, Depends(get_download_service)],
    guard: Annotated[IdempotencyGuard, Depends(get_idempotency_guard)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> Response:
    """Validate, durably queue, and dispatch one download."""
    body = await request.body()

    if idempotency_key:
        replayed = guard.replay(scope=_DOWNLOAD_SCOPE, key=idempotency_key, request_body=body)
        if replayed is not None:
            return JSONResponse(status_code=status.HTTP_201_CREATED, content=json.loads(replayed))

    job = downloads.request_download(
        submission.candidate.to_candidate(), SourceType(submission.source_type)
    )
    payload = JobModel.of(job).model_dump(mode="json")

    if idempotency_key:
        guard.remember(
            scope=_DOWNLOAD_SCOPE,
            key=idempotency_key,
            request_body=body,
            status_code=status.HTTP_201_CREATED,
            response_json=json.dumps(payload, separators=(",", ":"), sort_keys=True),
        )
    return JSONResponse(status_code=status.HTTP_201_CREATED, content=payload)


@router.get(
    "/downloads",
    response_model=PageModel[JobModel],
    summary="List downloads, newest first",
)
def list_downloads(
    downloads: Annotated[DownloadService, Depends(get_download_service)],
    state: Annotated[
        list[JobStateLiteral] | None,
        Query(description="Restrict the listing to these durable states."),
    ] = None,
    cursor: Annotated[str | None, Query(description="Cursor from a previous page.")] = None,
    limit: Annotated[int, Query(ge=1, le=JOB_PAGE_LIMIT_MAX)] = JOB_PAGE_LIMIT_DEFAULT,
) -> PageModel[JobModel]:
    states = tuple(JobState(value) for value in state) if state else None
    page = downloads.list_jobs(states=states, cursor=cursor, limit=limit)
    return PageModel(items=[JobModel.of(job) for job in page.items], next_cursor=page.next_cursor)


@router.get(
    "/downloads/{job_id}",
    response_model=JobDetailModel,
    summary="Read one download and its event history",
)
def read_download(
    job_id: str,
    downloads: Annotated[DownloadService, Depends(get_download_service)],
) -> JobDetailModel:
    return JobDetailModel.of(downloads.get_job(JobId(job_id)))


@router.post(
    "/downloads/{job_id}/cancel",
    response_model=JobModel,
    summary="Cancel one queued or running download",
)
def cancel_download(
    job_id: str,
    submission: CancelRequestModel,
    downloads: Annotated[DownloadService, Depends(get_download_service)],
) -> JobModel:
    """Cancel a queued job outright, or ask a running one to stop."""
    job = downloads.cancel_download(JobId(job_id), expected_version=submission.version)
    return JobModel.of(job)


@router.post(
    "/downloads/{job_id}/retry",
    response_model=JobModel,
    status_code=status.HTTP_201_CREATED,
    summary="Queue a fresh attempt linked to a finished download",
)
async def retry_download(
    job_id: str,
    request: Request,
    downloads: Annotated[DownloadService, Depends(get_download_service)],
    guard: Annotated[IdempotencyGuard, Depends(get_idempotency_guard)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> Response:
    """Create one new linked attempt; a repeated key replays the first result."""
    body = await request.body()
    scope = f"{_RETRY_SCOPE} {job_id}"

    if idempotency_key:
        replayed = guard.replay(scope=scope, key=idempotency_key, request_body=body)
        if replayed is not None:
            return JSONResponse(status_code=status.HTTP_201_CREATED, content=json.loads(replayed))

    job = downloads.retry_download(JobId(job_id))
    payload = JobModel.of(job).model_dump(mode="json")

    if idempotency_key:
        guard.remember(
            scope=scope,
            key=idempotency_key,
            request_body=body,
            status_code=status.HTTP_201_CREATED,
            response_json=json.dumps(payload, separators=(",", ":"), sort_keys=True),
        )
    return JSONResponse(status_code=status.HTTP_201_CREATED, content=payload)
