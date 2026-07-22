"""The production Deezer discovery adapter.

Deezer is keyless: one `GET /search` returns matching tracks, which are parsed
into `TrackCandidate` by the shared `deezer_wire` functions the fixture adapter
also uses. Nothing Deezer-shaped escapes this module — the wire parser is the
only thing that reads the payload, and it hands back the normalized boundary
type.

All traffic goes through the one outbound policy, so the saved proxy and the
fail-closed rule apply here exactly as they do everywhere else.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Final

from chillify.domain.errors import ProviderResponseError
from chillify.domain.protocols import TrackCandidate
from chillify.infrastructure.providers.deezer_wire import PROVIDER_NAME, candidates_from_search
from chillify.infrastructure.security.outbound import OutboundHttp

logger = logging.getLogger(__name__)

_SEARCH_URL: Final = "https://api.deezer.com/search"


@dataclass(frozen=True, slots=True)
class DeezerDiscoveryProvider:
    """Keyless Deezer search over the shared outbound policy."""

    name: str = PROVIDER_NAME

    def search(self, query: str, limit: int, proxy: str | None) -> tuple[TrackCandidate, ...]:
        """Return normalized, non-playable candidates for one query.

        HTTP failures, an `error` object, or unreadable JSON all become one
        typed provider error: the response body is exactly the thing that must
        not travel back to the browser.
        """
        policy = OutboundHttp(proxy=proxy)
        response = policy.request("GET", _SEARCH_URL, params={"q": query, "limit": str(limit)})
        if response.status_code >= 400:
            logger.info(
                "deezer search returned an error status",
                extra={"provider": self.name, "status": response.status_code},
            )
            raise ProviderResponseError(
                "Deezer could not complete that search.",
                context={"provider": self.name},
            )
        try:
            payload = json.loads(response.content)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ProviderResponseError(
                "Deezer returned a response Chillify could not read.",
                context={"provider": self.name},
            ) from exc
        candidates = candidates_from_search(payload)
        return candidates[:limit]
