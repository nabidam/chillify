"""The provider registry.

Adapters are bound here and resolved by capability, never by name, so the
application layer asks "who can acquire a YouTube video" rather than importing
yt-dlp. A provider that is not bound is reported as disabled, which is exactly
what the Settings screen and the degraded-state banner already know how to say.

Production adapters are bound in production mode and the fixture adapters in gate
mode, against the same protocols. A production process never imports fixture
code, and a gate process never imports a real provider package; the two branches
below keep that separation an import-time fact, not a runtime check. The Last.fm
enricher and the Last.fm cover fetcher are not bound here: both need the
DB-stored API key, which this Settings-only builder cannot read.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from dataclasses import dataclass, field

from chillify.config import Settings
from chillify.domain.errors import ProviderDisabledError
from chillify.domain.jobs import JobProvider
from chillify.domain.protocols import (
    AcquisitionProvider,
    ArtworkFetcher,
    DiscoveryProvider,
    LinkInspector,
    MetadataEnricher,
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
    # The official Spotify API is a separate inspection capability. It is kept
    # apart from the SpotDL acquisition inspector so the application policy can
    # order API -> SpotDL without making either adapter know about the other.
    spotify_api: LinkInspector | None = None
    # Built on demand so a Last.fm key changed in Settings is used by the next
    # worker job without restarting the worker process.
    metadata_enricher: Callable[[], MetadataEnricher | None] = lambda: None
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


def build_registry(
    settings: Settings,
    *,
    spotify_credentials_provider: Callable[[], tuple[str, str] | None] | None = None,
    lastfm_api_key_provider: Callable[[], str | None] | None = None,
) -> ProviderRegistry:
    """Bind the adapters this environment is allowed to use.

    The fixture import lives inside the gate branch and the production imports in
    the other: a process only ever imports the adapters it is allowed to bind, so
    it cannot bind the wrong family by accident.
    """
    if settings.is_gate and settings.fixture_root is not None:
        from chillify.infrastructure.providers.fixtures import (
            FixtureAcquisitionProvider,
            FixtureDiscoveryProvider,
        )
        from chillify.infrastructure.providers.spotdl import FixtureSpotdlInspector
        from chillify.infrastructure.providers.spotify_api import FixtureSpotifyApiInspector
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
            spotify_api=FixtureSpotifyApiInspector(fixture_root=fixture_root),
        )

    from chillify.infrastructure.providers.apple_music import AppleMusicDiscoveryProvider
    from chillify.infrastructure.providers.artwork_http import HttpArtworkFetcher
    from chillify.infrastructure.providers.deezer import DeezerDiscoveryProvider
    from chillify.infrastructure.providers.lastfm import LastfmEnricher
    from chillify.infrastructure.providers.musicbrainz import MusicBrainzDiscoveryProvider
    from chillify.infrastructure.providers.spotdl import (
        SpotdlAcquisitionProvider,
        SpotdlInspector,
    )
    from chillify.infrastructure.providers.spotify_api import SpotifyApiInspector
    from chillify.infrastructure.providers.ytdlp import (
        YouTubeInspector,
        YtDlpAcquisitionProvider,
    )

    # SpotDL lives in an isolated environment kept off PATH, reached only through
    # its pinned absolute path; the resolver falls back to the name for local
    # development where it is on PATH.
    spotdl_bin = os.environ.get("CHILLIFY_SPOTDL_BIN", "").strip() or "spotdl"
    logger.info("binding production provider adapters", extra={"environment": "production"})
    return ProviderRegistry(
        discovery={
            "apple": AppleMusicDiscoveryProvider(),
            "deezer": DeezerDiscoveryProvider(),
            "musicbrainz": MusicBrainzDiscoveryProvider(),
        },
        acquisition={
            JobProvider.YT_DLP: YtDlpAcquisitionProvider(),
            JobProvider.SPOTDL: SpotdlAcquisitionProvider(executable=spotdl_bin),
        },
        link_inspectors={
            JobProvider.YT_DLP: YouTubeInspector(),
            JobProvider.SPOTDL: SpotdlInspector(executable=spotdl_bin),
        },
        # Credentials are read through the settings service at inspection time.
        # They are operator-managed secrets, so taking a startup snapshot would
        # make a dashboard save appear successful while the running process
        # continued to behave as if Spotify were unconfigured.
        spotify_api=SpotifyApiInspector(credentials_provider=spotify_credentials_provider),
        metadata_enricher=lambda: LastfmEnricher(
            api_key=None if lastfm_api_key_provider is None else lastfm_api_key_provider()
        ),
        artwork={"url": HttpArtworkFetcher()},
    )
