"""Request-scoped dependency resolution.

Routes receive the composition root through FastAPI's dependency system so no
module reaches for a global binding, and tests can substitute a composition
built against disposable roots.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from chillify.application.downloads import DownloadService, IdempotencyGuard
from chillify.application.library import LibraryService
from chillify.application.search import SearchService
from chillify.composition import Composition


def get_composition(request: Request) -> Composition:
    composition: Composition = request.app.state.composition
    return composition


def get_library_service(
    composition: Annotated[Composition, Depends(get_composition)],
) -> LibraryService:
    return composition.library_service()


def get_search_service(
    composition: Annotated[Composition, Depends(get_composition)],
) -> SearchService:
    return composition.search_service()


def get_download_service(
    composition: Annotated[Composition, Depends(get_composition)],
) -> DownloadService:
    return composition.download_service()


def get_idempotency_guard(
    composition: Annotated[Composition, Depends(get_composition)],
) -> IdempotencyGuard:
    return IdempotencyGuard(session_factory=composition.session_factory)
