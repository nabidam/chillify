"""Household profile routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status

from chillify.api.dependencies import get_library_service
from chillify.api.schemas.common import PageModel
from chillify.api.schemas.profiles import CreateProfileRequest, ProfileModel
from chillify.application.library import LibraryService

router = APIRouter(tags=["profiles"])


@router.get(
    "/profiles",
    response_model=PageModel[ProfileModel],
    summary="List the household profiles",
)
def list_profiles(
    library: Annotated[LibraryService, Depends(get_library_service)],
) -> PageModel[ProfileModel]:
    """Every profile, name-folded order.

    The list is small and bounded by household use, so it is served whole; the
    page envelope is present for shape consistency, never for paging.
    """
    return PageModel(items=[ProfileModel.of(profile) for profile in library.list_profiles()])


@router.post(
    "/profiles",
    response_model=ProfileModel,
    status_code=status.HTTP_201_CREATED,
    summary="Create a household profile",
)
def create_profile(
    request: CreateProfileRequest,
    library: Annotated[LibraryService, Depends(get_library_service)],
) -> ProfileModel:
    return ProfileModel.of(library.create_profile(request.name))
