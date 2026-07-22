"""Request-scoped dependency resolution.

Routes receive the composition root through FastAPI's dependency system so no
module reaches for a global binding, and tests can substitute a composition
built against disposable roots.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from chillify.application.artwork import ArtworkService
from chillify.application.deletion import DeletionService
from chillify.application.downloads import DownloadService, IdempotencyGuard
from chillify.application.library import LibraryService
from chillify.application.links import LinkInspectionService
from chillify.application.metadata import MetadataService
from chillify.application.playlists import PlaylistService
from chillify.application.search import SearchService
from chillify.application.settings import SettingsService
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


def get_link_inspection_service(
    composition: Annotated[Composition, Depends(get_composition)],
) -> LinkInspectionService:
    return composition.link_inspection_service()


def get_download_service(
    composition: Annotated[Composition, Depends(get_composition)],
) -> DownloadService:
    return composition.download_service()


def get_metadata_service(
    composition: Annotated[Composition, Depends(get_composition)],
) -> MetadataService:
    return composition.metadata_service()


def get_deletion_service(
    composition: Annotated[Composition, Depends(get_composition)],
) -> DeletionService:
    return composition.deletion_service()


def get_playlist_service(
    composition: Annotated[Composition, Depends(get_composition)],
) -> PlaylistService:
    return composition.playlist_service()


def get_artwork_service(
    composition: Annotated[Composition, Depends(get_composition)],
) -> ArtworkService:
    return composition.artwork_service()


def get_settings_service(
    composition: Annotated[Composition, Depends(get_composition)],
) -> SettingsService:
    return composition.settings_service()


def get_idempotency_guard(
    composition: Annotated[Composition, Depends(get_composition)],
) -> IdempotencyGuard:
    return IdempotencyGuard(session_factory=composition.session_factory)
