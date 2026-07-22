"""The provider registry.

Adapters are bound here and resolved by capability, never by name, so the
application layer asks "who can acquire a YouTube video" rather than importing
yt-dlp. A provider that is not bound is reported as disabled, which is exactly
what the Settings screen and the degraded-state banner already know how to say.

Production adapters are not bound in this milestone; the fixture adapters serve
the gate environment while the acquisition machinery is proved. Task 16 binds
the real ones into the same registry, against the same protocols.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from chillify.config import Settings
from chillify.domain.errors import ProviderDisabledError
from chillify.domain.jobs import JobProvider
from chillify.domain.protocols import (
    AcquisitionProvider,
    ArtworkFetcher,
    DiscoveryProvider,
    LinkInspector,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ProviderRegistry:
    """Every bound adapter, keyed by the capability it satisfies."""

    discovery: dict[str, DiscoveryProvider] = field(default_factory=dict)
    acquisition: dict[JobProvider, AcquisitionProvider] = field(default_factory=dict)
    # Keyed by the acquisition provider that later fulfils an inspected link, so
    # the inspection use case routes by capability rather than naming yt-dlp or
    # SpotDL. Empty until an adapter is bound; a submitted link is then reported
    # as unsupported, exactly as a disabled provider already is.
    link_inspectors: dict[JobProvider, LinkInspector] = field(default_factory=dict)
    # Keyed by the artwork origin it serves — `url` for a submitted link,
    # `lastfm` for the enricher's best match — so the staging use case asks for
    # a capability rather than naming an adapter.
    artwork: dict[str, ArtworkFetcher] = field(default_factory=dict)

    def require_discovery(self, name: str) -> DiscoveryProvider:
        provider = self.discovery.get(name)
        if provider is None:
            raise ProviderDisabledError(
                "Online search is unavailable in this deployment.",
                context={"provider": name},
            )
        return provider

    def require_acquisition(self, provider: JobProvider) -> AcquisitionProvider:
        adapter = self.acquisition.get(provider)
        if adapter is None:
            raise ProviderDisabledError(
                "Downloading is unavailable in this deployment.",
                context={"provider": str(provider)},
            )
        return adapter

    def has_acquisition(self, provider: JobProvider) -> bool:
        return provider in self.acquisition


def build_registry(settings: Settings) -> ProviderRegistry:
    """Bind the adapters this environment is allowed to use.

    The fixture import lives inside the gate branch: a production process never
    imports fixture code, so it cannot bind it by accident.
    """
    if not settings.is_gate or settings.fixture_root is None:
        return ProviderRegistry()

    from chillify.infrastructure.providers.fixtures import (
        FixtureAcquisitionProvider,
        FixtureDiscoveryProvider,
    )
    from chillify.infrastructure.providers.spotdl import FixtureSpotdlInspector
    from chillify.infrastructure.providers.ytdlp import FixtureYouTubeInspector

    fixture_root = settings.fixture_root
    acquisition = FixtureAcquisitionProvider(fixture_root=fixture_root)
    logger.info("binding fixture provider adapters", extra={"environment": "gate"})
    return ProviderRegistry(
        discovery={"deezer": FixtureDiscoveryProvider(fixture_root=fixture_root)},
        acquisition={
            JobProvider.YT_DLP: acquisition,
            JobProvider.SPOTDL: acquisition,
        },
        link_inspectors={
            JobProvider.YT_DLP: FixtureYouTubeInspector(fixture_root=fixture_root),
            JobProvider.SPOTDL: FixtureSpotdlInspector(fixture_root=fixture_root),
        },
    )
