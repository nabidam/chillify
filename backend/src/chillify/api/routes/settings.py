"""Settings routes.

The global proxy is saved and tested here, provider enablement and the optional
Last.fm key are edited here, and every response is a masked view. A proxy test
always goes through the proxy: there is no route that reaches the internet
directly, so the fail-closed rule holds at the transport layer, not by
convention.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from chillify.api.dependencies import get_settings_service
from chillify.api.schemas.settings import (
    ProviderDiagnosisModel,
    ProviderStateModel,
    ProxyDiagnosisModel,
    ProxyStateModel,
    SettingsModel,
    TestProxyRequest,
    UpdateProviderRequest,
    UpdateProxyRequest,
)
from chillify.application.settings import SettingsService

router = APIRouter(tags=["settings"])


@router.get(
    "/settings",
    response_model=SettingsModel,
    summary="Read the masked proxy and provider settings",
)
def read_settings(
    settings: Annotated[SettingsService, Depends(get_settings_service)],
) -> SettingsModel:
    return SettingsModel.of(settings.read())


@router.patch(
    "/settings/proxy",
    response_model=ProxyStateModel,
    summary="Save or clear the global proxy",
)
def update_proxy(
    request: UpdateProxyRequest,
    settings: Annotated[SettingsService, Depends(get_settings_service)],
) -> ProxyStateModel:
    view = settings.save_proxy(request.url, revision=request.revision, clear=request.clear)
    return ProxyStateModel.of(view)


@router.post(
    "/settings/proxy/test",
    response_model=ProxyDiagnosisModel,
    summary="Test the saved or a supplied proxy through the proxy itself",
)
def test_proxy(
    request: TestProxyRequest,
    settings: Annotated[SettingsService, Depends(get_settings_service)],
) -> ProxyDiagnosisModel:
    return ProxyDiagnosisModel.of(settings.test_proxy(request.url))


@router.patch(
    "/settings/providers/{provider}",
    response_model=ProviderStateModel,
    summary="Toggle a provider or set its credential",
)
def update_provider(
    provider: str,
    request: UpdateProviderRequest,
    settings: Annotated[SettingsService, Depends(get_settings_service)],
) -> ProviderStateModel:
    view = settings.save_provider(
        provider,
        revision=request.revision,
        enabled=request.enabled,
        credential=request.credential,
        clear_secret=request.clear_secret,
    )
    return ProviderStateModel.of(view)


@router.post(
    "/settings/providers/{provider}/test",
    response_model=ProviderDiagnosisModel,
    summary="Report a single provider's readiness",
)
def test_provider(
    provider: str,
    settings: Annotated[SettingsService, Depends(get_settings_service)],
) -> ProviderDiagnosisModel:
    return ProviderDiagnosisModel.of(settings.test_provider(provider))
