"""SSRF containment, oversized-fetch, and symlink-escape refusals, end to end.

ARCHITECTURE section 13 names three distinct household-facing guarantees this
suite proves through the real API rather than at a unit level: a URL a person
pastes for cover art can never reach the container's own network or the LAN
behind it, even through a redirect a remote server controls; a cover fetch
larger than the documented cap is refused rather than silently truncated or
memory-exhausted; and a managed path corrupted into a symlink that escapes the
music root is refused rather than served.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from sqlalchemy import text

from chillify.domain.models import to_rfc3339
from chillify.infrastructure.db.engine import create_database_engine
from chillify.infrastructure.db.repositories import new_id
from chillify.infrastructure.media.artwork import ARTWORK_MAX_BYTES

pytestmark = pytest.mark.integration

FIXTURE_AUDIO = Path(__file__).resolve().parents[1] / "fixtures" / "media" / "gate-tone.mp3"
STAGE_FROM_URL = "/api/v1/artwork/stages/url"

_COVER_URL = "https://cdn.invalid/cover.jpg"


def _png_bytes(size: tuple[int, int] = (32, 32)) -> bytes:
    import io

    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", size, color=(20, 60, 90)).save(buffer, format="PNG")
    return buffer.getvalue()


class TestPrivateRedirectsAreRefused:
    @pytest.mark.parametrize(
        "private_target",
        [
            "http://127.0.0.1/private.jpg",
            "http://[::1]/private.jpg",
            "http://169.254.169.254/latest/meta-data/",
            "http://10.0.0.5/internal.jpg",
        ],
    )
    def test_a_redirect_to_a_disallowed_target_is_refused(
        self, start_api: Callable[[], TestClient], private_target: str
    ) -> None:
        client = start_api()
        with respx.mock:
            respx.get(_COVER_URL).mock(
                return_value=httpx.Response(302, headers={"Location": private_target})
            )

            response = client.post(STAGE_FROM_URL, json={"url": _COVER_URL})

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "outbound_target_rejected"

    def test_a_direct_loopback_url_is_refused_without_any_request(
        self, start_api: Callable[[], TestClient]
    ) -> None:
        """A literal loopback host in the submitted URL needs no redirect at all."""
        client = start_api()
        with respx.mock(assert_all_called=False) as router:
            route = router.get("http://127.0.0.1/evil.jpg")

            response = client.post(STAGE_FROM_URL, json={"url": "http://127.0.0.1/evil.jpg"})

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "outbound_target_rejected"
        assert route.call_count == 0

    def test_a_safe_redirect_still_succeeds(self, start_api: Callable[[], TestClient]) -> None:
        """The policy refuses unsafe hops, not redirects themselves."""
        client = start_api()
        final_url = "https://cdn.invalid/final.jpg"
        with respx.mock:
            respx.get(_COVER_URL).mock(
                return_value=httpx.Response(302, headers={"Location": final_url})
            )
            respx.get(final_url).mock(return_value=httpx.Response(200, content=_png_bytes()))

            response = client.post(STAGE_FROM_URL, json={"url": _COVER_URL})

        assert response.status_code == 201
        assert response.json()["origin"] == "url"


class TestOversizedArtIsRefused:
    def test_a_cover_larger_than_the_cap_is_refused(
        self, start_api: Callable[[], TestClient]
    ) -> None:
        client = start_api()
        oversized = b"\xff" * (ARTWORK_MAX_BYTES + 1)
        with respx.mock:
            respx.get(_COVER_URL).mock(return_value=httpx.Response(200, content=oversized))

            response = client.post(STAGE_FROM_URL, json={"url": _COVER_URL})

        assert response.status_code == 413
        assert response.json()["error"]["code"] == "artwork_too_large"


class TestSymlinkEscapeIsRefused:
    def test_a_track_whose_stored_path_is_a_symlink_leaving_the_root_is_refused(
        self,
        migrated_environment: dict[str, str],
        start_api: Callable[[], TestClient],
    ) -> None:
        data_root = Path(migrated_environment["CHILLIFY_DATA_ROOT"])
        music_root = Path(migrated_environment["CHILLIFY_MUSIC_ROOT"])

        # A file genuinely outside the music root, and a symlink inside it that
        # points straight at that escape — exactly what `resolve_managed_path`
        # must refuse regardless of how the stored value came to be corrupted.
        outside_root = data_root / "outside-the-music-root"
        outside_root.mkdir(parents=True, exist_ok=True)
        outside_file = outside_root / "not-managed.mp3"
        content = FIXTURE_AUDIO.read_bytes()
        outside_file.write_bytes(content)

        relative_path = "Music/Escape Artist/Escape Album/01 - Escape.mp3"
        symlink_path = music_root / relative_path
        symlink_path.parent.mkdir(parents=True, exist_ok=True)
        symlink_path.symlink_to(outside_file)

        track_id = new_id()
        moment = to_rfc3339(datetime.now(UTC))
        engine = create_database_engine(data_root / "db" / "chillify.sqlite3")
        try:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO tracks (id, title, artist, album, release_year,"
                        " disc_number, track_number, duration_ms, normalized_artist,"
                        " normalized_title, normalized_album, file_relpath, mime_type,"
                        " file_size_bytes, content_sha256, availability, revision,"
                        " created_at, updated_at)"
                        " VALUES (:id, 'Escape', 'Escape Artist', 'Escape Album', 2020, 1, 1,"
                        " 180000, 'escape artist', 'escape', 'escape album', :relpath,"
                        " 'audio/mpeg', :size, :digest, 'available', 1, :moment, :moment)"
                    ),
                    {
                        "id": track_id,
                        "relpath": relative_path,
                        "size": len(content),
                        "digest": hashlib.sha256(content).hexdigest(),
                        "moment": moment,
                    },
                )
        finally:
            engine.dispose()

        client = start_api()
        response = client.get(f"/api/v1/tracks/{track_id}/stream")

        assert response.status_code == 500
        assert response.json()["error"]["code"] == "unsafe_media_path"
        # The symlink itself, and the file it points at, are both untouched:
        # refusal is read-only.
        assert symlink_path.is_symlink()
        assert outside_file.read_bytes() == content
