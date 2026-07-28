"""Provider-agnostic inspection ordering and fallback policy."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from chillify.application.settings import InspectionMode, InspectionSettings
from chillify.domain.errors import ProviderResponseError
from chillify.domain.protocols import LinkInspector, TrackCandidate

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class InspectionPolicy:
    """Choose the configured fast path and make fallback explicit."""

    spotify_api: LinkInspector
    spotdl: LinkInspector
    youtube: LinkInspector | None = None
    proxy_provider: Callable[[], str | None] = lambda: None

    def inspect(
        self,
        url: str,
        mode: InspectionMode | str,
        settings: InspectionSettings,
    ) -> TrackCandidate:
        """Inspect one URL using the selected mode and configured fallback."""
        selected_mode = InspectionMode(mode)
        logger.debug(
            "inspection settings snapshot captured",
            extra={
                "timeout_spotify_s": settings.timeout_spotify_s,
                "timeout_spotdl_s": settings.timeout_spotdl_s,
                "timeout_ytdlp_s": settings.timeout_ytdlp_s,
            },
        )
        proxy = self.proxy_provider()

        if self.spotify_api.supports(url):
            if selected_mode is InspectionMode.THOROUGH:
                return self.spotdl.inspect(url, proxy)
            try:
                return self.spotify_api.inspect(url, proxy)
            except ProviderResponseError as exc:
                if not _may_fallback(exc):
                    raise
                logger.info(
                    "spotify api inspection falling back to spotdl",
                    extra={"reason": exc.context.get("reason", "provider_failure")},
                )
                try:
                    return self.spotdl.inspect(url, proxy)
                except ProviderResponseError as spotdl_error:
                    raise ProviderResponseError(
                        "Spotify and SpotDL could not inspect that link.",
                        context={"provider": "inspection", "fallback": False},
                    ) from spotdl_error

        if self.youtube is not None and self.youtube.supports(url):
            return self.youtube.inspect(url, proxy)
        return self.spotdl.inspect(url, proxy)


def _may_fallback(error: ProviderResponseError) -> bool:
    return error.context.get("fallback", True) is True
