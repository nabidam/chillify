"""Production MusicBrainz recording discovery adapter.

MusicBrainz's public service asks anonymous clients to stay at or below one
request per second and to identify themselves.  The small, per-adapter
throttle below is intentionally local rather than process-global: the
composition root owns one production adapter, and keeping this limiter local
makes its clock and sleep behaviour deterministic in contract tests without
introducing a global lock or blocking unrelated providers.

Requests use the common outbound policy, so a configured proxy is always used
and there is no direct-network fallback.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from threading import Lock
from typing import Final

from chillify.domain.errors import ProviderResponseError
from chillify.domain.protocols import DISCOVERY_LIMIT_MAX, TrackCandidate
from chillify.infrastructure.providers.musicbrainz_wire import (
    PROVIDER_NAME,
    candidates_from_recording_search,
)
from chillify.infrastructure.security.outbound import OutboundHttp

logger = logging.getLogger(__name__)

_SEARCH_URL: Final = "https://musicbrainz.org/ws/2/recording/"
_REQUEST_INTERVAL_SECONDS: Final = 1.0
# MusicBrainz asks clients to include an application name/version and contact
# address.  This stable project URL is useful to its operators without exposing
# an installation or its household operator.
_USER_AGENT: Final = "Chillify/0.1.0 (https://github.com/chillify/chillify)"


@dataclass(slots=True)
class MusicBrainzDiscoveryProvider:
    """Keyless MusicBrainz recording search over the shared outbound policy."""

    name: str = PROVIDER_NAME
    clock: Callable[[], float] = time.monotonic
    sleeper: Callable[[float], None] = time.sleep
    _next_request_at: float = field(default=0.0, init=False, repr=False)
    _throttle_lock: Lock = field(default_factory=Lock, init=False, repr=False)

    def search(self, query: str, limit: int, proxy: str | None) -> tuple[TrackCandidate, ...]:
        """Return normalized, non-playable recording candidates for one query."""
        bounded = _bounded_limit(limit)
        self._wait_for_request_slot()
        response = OutboundHttp(proxy=proxy).request(
            "GET",
            _SEARCH_URL,
            # Supplying query through httpx params preserves user punctuation as
            # data rather than letting it change the request URL or syntax.
            params={"query": query, "limit": str(bounded), "fmt": "json"},
            headers={"User-Agent": _USER_AGENT},
        )
        if response.status_code >= 400:
            logger.info(
                "musicbrainz search returned an error status",
                extra={"provider": self.name, "status": response.status_code},
            )
            raise _provider_error("MusicBrainz could not complete that search.")
        try:
            payload = json.loads(response.content)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise _provider_error(
                "MusicBrainz returned a response Chillify could not read."
            ) from exc
        return candidates_from_recording_search(payload)[:bounded]

    def _wait_for_request_slot(self) -> None:
        """Reserve the next adapter-local request slot before opening a client."""
        with self._throttle_lock:
            now = self.clock()
            delay = max(0.0, self._next_request_at - now)
            if delay:
                self.sleeper(delay)
                now = self.clock()
            self._next_request_at = now + _REQUEST_INTERVAL_SECONDS


def _bounded_limit(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return 1
    return max(1, min(value, DISCOVERY_LIMIT_MAX))


def _provider_error(message: str) -> ProviderResponseError:
    return ProviderResponseError(message, context={"provider": PROVIDER_NAME})
