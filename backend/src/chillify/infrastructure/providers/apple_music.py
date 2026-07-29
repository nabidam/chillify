"""Keyless Apple iTunes Search discovery adapter.

The iTunes Search API is used only to discover catalog metadata.  It does not
provide an acquisition URL: previews and artwork are intentionally excluded
under Apple's promotional-content terms.  Every request uses the shared
outbound policy, retaining proxy fail-closed behaviour.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Final

from chillify.domain.errors import ProviderResponseError
from chillify.domain.protocols import DISCOVERY_LIMIT_MAX, TrackCandidate
from chillify.infrastructure.providers.apple_music_wire import PROVIDER_NAME, candidates_from_search
from chillify.infrastructure.security.outbound import OutboundHttp

logger = logging.getLogger(__name__)

_SEARCH_URL: Final = "https://itunes.apple.com/search"
_DEFAULT_COUNTRY: Final = "US"


@dataclass(frozen=True, slots=True)
class AppleMusicDiscoveryProvider:
    """Search Apple Music catalog metadata through the shared outbound policy."""

    country: str = _DEFAULT_COUNTRY
    name: str = PROVIDER_NAME

    def __post_init__(self) -> None:
        normalized_country = self.country.strip().upper()
        if len(normalized_country) != 2 or not normalized_country.isalpha():
            raise ValueError("Apple Music country must be a two-letter country code.")
        object.__setattr__(self, "country", normalized_country)

    def search(self, query: str, limit: int, proxy: str | None) -> tuple[TrackCandidate, ...]:
        """Return normalized, non-playable song candidates for one search."""
        bounded_limit = min(max(limit, 1), DISCOVERY_LIMIT_MAX)
        policy = OutboundHttp(proxy=proxy)
        response = policy.request(
            "GET",
            _SEARCH_URL,
            params={
                "term": query,
                "media": "music",
                "entity": "song",
                "country": self.country,
                "limit": str(bounded_limit),
            },
        )
        if response.status_code >= 400:
            logger.info(
                "apple music search returned an error status",
                extra={"provider": self.name, "status": response.status_code},
            )
            raise ProviderResponseError(
                "Apple Music could not complete that search.",
                context={"provider": self.name},
            )
        try:
            payload = json.loads(response.content)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ProviderResponseError(
                "Apple Music returned a response Chillify could not read.",
                context={"provider": self.name},
            ) from exc
        return candidates_from_search(payload)[:bounded_limit]
