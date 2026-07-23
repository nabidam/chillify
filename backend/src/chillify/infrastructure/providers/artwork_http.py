"""The production HTTP artwork fetcher.

A cover URL — one a provider handed back, or one a person pasted in S13 — is
retrieved here through the one outbound policy, so the saved proxy, timeout, and
retry rules apply exactly as they do to Deezer and Last.fm. There is no second
HTTP client that could reach the network directly.

What comes back is decoded and re-encoded by `normalize_cover`, the same
validator every uploaded cover passes through, so this adapter can never place
anything but one bounded baseline JPEG into the workspace. Redirects are bounded
and the initial scheme is checked, but the full host/IP SSRF policy belongs to
`security/outbound` and is hardened in a later task.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Final
from urllib.parse import urlsplit

from chillify.domain.errors import ArtworkTooLargeError, ArtworkUnreadableError
from chillify.domain.protocols import ImageArtifact
from chillify.infrastructure.media.artwork import ARTWORK_MAX_BYTES, normalize_cover
from chillify.infrastructure.security.outbound import OutboundHttp

logger = logging.getLogger(__name__)

_PROVIDER_NAME: Final = "artwork_http"
# ARCHITECTURE section 6: at most three redirect hops.
_MAX_REDIRECTS: Final = 3
_ALLOWED_SCHEMES: Final = frozenset({"http", "https"})
_FETCHED_COVER: Final = "cover.jpg"


@dataclass(frozen=True, slots=True)
class HttpArtworkFetcher:
    """Fetch and normalize one cover image through the shared outbound policy."""

    name: str = _PROVIDER_NAME

    def fetch(self, source: str, workspace: str, proxy: str | None) -> ImageArtifact:
        """Retrieve `source`, normalize it, and write one JPEG into `workspace`.

        A non-HTTP(S) scheme, an oversized declaration, an error status, or bytes
        that will not decode are all one safe artwork error: the response body is
        exactly the thing that must not be echoed back to the browser. A proxy
        failure propagates as its own typed error so S12 can name it.
        """
        scheme = (urlsplit(source).scheme or "").lower()
        if scheme not in _ALLOWED_SCHEMES:
            raise ArtworkUnreadableError(
                "Cover art can only be fetched over HTTP or HTTPS.",
                context={"provider": self.name},
            )

        # A cover fetch is the one outbound call that follows redirects; the hop
        # count is capped here rather than left to httpx's default.
        policy = OutboundHttp(proxy=proxy, follow_redirects=True, max_redirects=_MAX_REDIRECTS)
        response = policy.request("GET", source)
        if response.status_code >= 400:
            logger.info(
                "artwork fetch returned an error status",
                extra={"provider": self.name, "status": response.status_code},
            )
            raise ArtworkUnreadableError(
                "That cover image could not be fetched.",
                context={"provider": self.name},
            )

        declared = response.headers.get("content-length")
        if declared is not None and declared.isdigit() and int(declared) > ARTWORK_MAX_BYTES:
            raise ArtworkTooLargeError(
                "That cover image is larger than 10 MB.",
                context={"provider": self.name, "max_bytes": ARTWORK_MAX_BYTES},
            )

        cover = normalize_cover(response.content)
        target = Path(workspace) / _FETCHED_COVER
        target.write_bytes(cover.payload)
        logger.info("artwork fetched", extra={"provider": self.name})
        return ImageArtifact(location=str(target), byte_size=cover.size_bytes)
