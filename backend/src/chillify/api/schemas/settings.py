"""Settings request and response shapes.

Every response here is a masked view: `GET /settings` and each mutation return
only the public proxy/provider state and the last test outcome. No shape can
carry a proxy password, a Last.fm key, or a ciphertext — those fields do not
exist on any model in this module.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from chillify.application.settings import (
    ProviderDiagnosis,
    ProviderView,
    ProxyView,
    SettingsView,
)
from chillify.infrastructure.security.outbound import ProxyDiagnosis


class ProxyStateModel(BaseModel):
    """The masked proxy state a browser may see."""

    configured: bool
    scheme: str | None = None
    host: str | None = None
    masked_url: str | None = Field(
        default=None,
        description="Scheme, host, and port with the password removed and the username masked.",
    )
    revision: int

    @classmethod
    def of(cls, view: ProxyView) -> ProxyStateModel:
        return cls(
            configured=view.configured,
            scheme=view.scheme,
            host=view.host,
            masked_url=view.masked_url,
            revision=view.revision,
        )


class ProviderStateModel(BaseModel):
    """One provider's public settings state."""

    name: str
    enabled: bool
    configured: bool
    requires_credential: bool
    has_credential: bool
    revision: int

    @classmethod
    def of(cls, view: ProviderView) -> ProviderStateModel:
        return cls(
            name=view.name,
            enabled=view.enabled,
            configured=view.configured,
            requires_credential=view.requires_credential,
            has_credential=view.has_credential,
            revision=view.revision,
        )


class SettingsModel(BaseModel):
    """The masked settings surface."""

    proxy: ProxyStateModel
    providers: list[ProviderStateModel]

    @classmethod
    def of(cls, view: SettingsView) -> SettingsModel:
        return cls(
            proxy=ProxyStateModel.of(view.proxy),
            providers=[ProviderStateModel.of(provider) for provider in view.providers],
        )


class UpdateProxyRequest(BaseModel):
    """Save or clear the global proxy.

    A blank or null `url` with `clear` unset means "remove the proxy"; a URL
    means "validate and save it". The revision is the one the browser last read.
    """

    url: str | None = Field(
        default=None, max_length=2048, description="Proxy URL, or null to clear."
    )
    clear: bool = Field(default=False, description="Remove the saved proxy.")
    revision: int = Field(ge=1, description="The revision the browser last read.")


class TestProxyRequest(BaseModel):
    """Test the saved proxy, or a supplied one before saving it."""

    url: str | None = Field(
        default=None,
        max_length=2048,
        description="A proxy to test as-is, or null to test the saved proxy.",
    )


class UpdateProviderRequest(BaseModel):
    """Toggle a provider and, for Last.fm, set or clear its API key."""

    enabled: bool | None = Field(default=None, description="Turn the provider on or off.")
    credential: str | None = Field(
        default=None,
        max_length=512,
        description="A new API key for a credentialled provider. Blank means unchanged.",
    )
    clear_secret: bool = Field(default=False, description="Remove the stored credential.")
    revision: int = Field(ge=1, description="The revision the browser last read.")


class ProxyDiagnosisModel(BaseModel):
    """One proxy-test outcome."""

    ok: bool
    code: Literal["ok", "unsupported_scheme", "connection", "authentication", "timeout"]
    message: str

    @classmethod
    def of(cls, diagnosis: ProxyDiagnosis) -> ProxyDiagnosisModel:
        return cls(ok=diagnosis.ok, code=diagnosis.code.value, message=diagnosis.message)


class ProviderDiagnosisModel(BaseModel):
    """One provider-test outcome."""

    ok: bool
    code: Literal["ok", "disabled", "unconfigured"]
    message: str

    @classmethod
    def of(cls, diagnosis: ProviderDiagnosis) -> ProviderDiagnosisModel:
        return cls(ok=diagnosis.ok, code=diagnosis.code.value, message=diagnosis.message)
