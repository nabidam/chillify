"""System status and health routes.

`/system/health` is the container liveness/readiness probe: cheap, local, and
free of provider or Redis contact. `/system/status` is the operator and shell
surface that distinguishes readiness from degradation.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import BaseModel, Field

from chillify.api.dependencies import get_composition
from chillify.composition import Composition, Health, SystemStatus

router = APIRouter(tags=["system"])


class ComponentStatusModel(BaseModel):
    name: str = Field(description="Stable component identifier.")
    health: Literal["ok", "degraded", "unavailable"]
    detail: str | None = Field(
        default=None,
        description="Short operator-facing explanation. Never contains a secret or path.",
    )


class ProviderStatusModel(BaseModel):
    name: str
    enabled: bool
    configured: bool


class SystemStatusModel(BaseModel):
    """The documented `GET /system/status` success envelope."""

    ready: bool = Field(
        description="Valid configuration, migrated database, and writable mounted roots."
    )
    degraded: bool = Field(
        description="Acquisition is impaired by Redis or tool state. Local use is unaffected."
    )
    environment: Literal["production", "gate"]
    checked_at: str = Field(description="RFC 3339 UTC timestamp of this evaluation.")
    database: ComponentStatusModel
    storage: list[ComponentStatusModel]
    redis: ComponentStatusModel
    tools: list[ComponentStatusModel]
    providers: list[ProviderStatusModel]


class HealthModel(BaseModel):
    status: Literal["ready", "not_ready"]


def _to_model(source: SystemStatus) -> SystemStatusModel:
    return SystemStatusModel(
        ready=source.ready,
        degraded=source.degraded,
        environment="gate" if source.environment == "gate" else "production",
        checked_at=source.checked_at,
        database=ComponentStatusModel(
            name=source.database.name,
            health=source.database.health.value,
            detail=source.database.detail,
        ),
        storage=[
            ComponentStatusModel(
                name=item.name,
                health=item.health.value,
                detail=item.detail,
            )
            for item in source.storage
        ],
        redis=ComponentStatusModel(
            name=source.redis.name,
            health=source.redis.health.value,
            detail=source.redis.detail,
        ),
        tools=[
            ComponentStatusModel(
                name=item.name,
                health=item.health.value,
                detail=item.detail,
            )
            for item in source.tools
        ],
        providers=[
            ProviderStatusModel(name=item.name, enabled=item.enabled, configured=item.configured)
            for item in source.providers
        ],
    )


@router.get(
    "/system/status",
    response_model=SystemStatusModel,
    summary="Report readiness, degradation, storage, tools, and provider state",
)
def read_system_status(
    composition: Annotated[Composition, Depends(get_composition)],
    refresh_tools: Annotated[
        bool,
        Query(description="Re-probe external tools instead of using the cached result."),
    ] = False,
) -> SystemStatusModel:
    return _to_model(composition.system_status(refresh_tools=refresh_tools))


@router.get(
    "/system/health",
    response_model=HealthModel,
    summary="Container readiness probe",
)
def read_health(
    composition: Annotated[Composition, Depends(get_composition)],
    response: Response,
) -> HealthModel:
    """Readiness only.

    Redis or provider degradation deliberately does not fail this probe: the
    library must stay readable when acquisition cannot run.
    """
    current = composition.system_status()
    ready = current.ready and current.database.health is not Health.UNAVAILABLE
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthModel(status="ready" if ready else "not_ready")
