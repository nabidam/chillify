"""The production HTTP artwork-fetcher contract.

A cover URL is fetched through the one outbound policy and decoded by the same
normalizer every uploaded cover passes, so what lands in the workspace is always
one bounded baseline JPEG. A non-HTTP(S) scheme, an oversized image, an error
status, and undecodable bytes are all part of the contract, as is the proxy
rule: one client, always with the saved proxy, never a direct fallback. Driven
through respx so no case touches the network.
"""

from __future__ import annotations

import io
from pathlib import Path

import httpx
import pytest
import respx
from PIL import Image

from chillify.domain.errors import ArtworkTooLargeError, ArtworkUnreadableError
from chillify.infrastructure.media.artwork import ARTWORK_MAX_BYTES
from chillify.infrastructure.providers.artwork_http import HttpArtworkFetcher
from chillify.infrastructure.security import outbound

pytestmark = pytest.mark.contract

_COVER_URL = "https://cdn.invalid/cover.png"
_REDIRECT_URL = "https://cdn.invalid/redirect.png"
_PROXY = "socks5://proxyuser:proxysecretpw@proxy.invalid:1080"


def _png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (12, 12), (10, 20, 30)).save(buffer, format="PNG")
    return buffer.getvalue()


class TestArtworkFetchContract:
    def test_a_cover_is_fetched_and_normalized_to_a_jpeg_in_the_workspace(
        self, tmp_path: Path
    ) -> None:
        with respx.mock:
            respx.get(_COVER_URL).mock(return_value=httpx.Response(200, content=_png_bytes()))
            artifact = HttpArtworkFetcher().fetch(_COVER_URL, str(tmp_path), None)

        written = Path(artifact.location)
        assert written.is_file()
        assert written.parent == tmp_path
        assert artifact.byte_size > 0
        with Image.open(written) as image:
            assert image.format == "JPEG"

    def test_a_bounded_redirect_is_followed(self, tmp_path: Path) -> None:
        with respx.mock:
            respx.get(_COVER_URL).mock(
                return_value=httpx.Response(302, headers={"Location": _REDIRECT_URL})
            )
            respx.get(_REDIRECT_URL).mock(return_value=httpx.Response(200, content=_png_bytes()))
            artifact = HttpArtworkFetcher().fetch(_COVER_URL, str(tmp_path), None)

        assert Path(artifact.location).is_file()

    def test_a_non_http_scheme_is_refused_before_any_request(self, tmp_path: Path) -> None:
        with respx.mock as router:
            route = router.get(url__regex=r".*")
            with pytest.raises(ArtworkUnreadableError):
                HttpArtworkFetcher().fetch("ftp://cdn.invalid/cover.png", str(tmp_path), None)

        assert route.call_count == 0

    def test_an_error_status_becomes_an_artwork_error(self, tmp_path: Path) -> None:
        with respx.mock:
            respx.get(_COVER_URL).mock(return_value=httpx.Response(404))
            with pytest.raises(ArtworkUnreadableError):
                HttpArtworkFetcher().fetch(_COVER_URL, str(tmp_path), None)

    def test_an_oversized_image_is_refused(self, tmp_path: Path) -> None:
        oversized = b"\x00" * (ARTWORK_MAX_BYTES + 1)
        with respx.mock:
            respx.get(_COVER_URL).mock(return_value=httpx.Response(200, content=oversized))
            with pytest.raises(ArtworkTooLargeError):
                HttpArtworkFetcher().fetch(_COVER_URL, str(tmp_path), None)

    def test_undecodable_bytes_become_an_artwork_error(self, tmp_path: Path) -> None:
        with respx.mock:
            respx.get(_COVER_URL).mock(return_value=httpx.Response(200, content=b"not an image"))
            with pytest.raises(ArtworkUnreadableError):
                HttpArtworkFetcher().fetch(_COVER_URL, str(tmp_path), None)


@pytest.mark.integration
class TestArtworkProxyPolicy:
    def test_the_saved_proxy_reaches_the_client_with_no_direct_fallback(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: list[str | None] = []

        def fake_build(*, proxy: str | None, **_kwargs: object) -> httpx.Client:
            captured.append(proxy)
            return _CannedClient(httpx.Response(200, content=_png_bytes()))

        monkeypatch.setattr(outbound, "build_httpx_client", fake_build)
        HttpArtworkFetcher().fetch(_COVER_URL, str(tmp_path), _PROXY)

        assert captured, "the adapter built no client at all"
        assert all(proxy == _PROXY for proxy in captured)
        assert None not in captured


class _CannedClient:
    def __init__(self, response: httpx.Response) -> None:
        self._response = response

    def __enter__(self) -> _CannedClient:
        return self

    def __exit__(self, *_exc: object) -> bool:
        return False

    def request(self, *_args: object, **_kwargs: object) -> httpx.Response:
        return self._response
