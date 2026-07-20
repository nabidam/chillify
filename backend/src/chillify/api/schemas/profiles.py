"""Profile request and response shapes.

Profiles separate playlists only. They carry no credential, avatar, or role,
and there is deliberately no rename or delete shape here.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from chillify.domain.models import Profile
from chillify.domain.normalization import PROFILE_NAME_MAX_LENGTH, PROFILE_NAME_MIN_LENGTH


class CreateProfileRequest(BaseModel):
    name: str = Field(
        min_length=PROFILE_NAME_MIN_LENGTH,
        max_length=PROFILE_NAME_MAX_LENGTH,
        description="Household profile name. Unique after case and whitespace folding.",
    )


class ProfileModel(BaseModel):
    """One household profile."""

    id: str
    name: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def of(cls, profile: Profile) -> ProfileModel:
        return cls(
            id=str(profile.id),
            name=profile.name,
            created_at=profile.created_at,
            updated_at=profile.updated_at,
        )
