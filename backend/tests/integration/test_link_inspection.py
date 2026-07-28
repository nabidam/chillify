"""`POST /links/inspect` through the real app: valid links inspect, bulk and
malformed links are refused, and no inspection ever leaves a durable job behind.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration

INSPECT = "/api/v1/links/inspect"

VIDEO_URL = "https://www.youtube.com/watch?v=u7K72X4eo_s"
TRACK_URL = "https://open.spotify.com/track/2cGxRwrMyEAp8dEbuZaVv6"
ALBUM_URL = "https://open.spotify.com/album/1DFixLWuPkv3KT3TnV35m3"
PLAYLIST_URL = "https://www.youtube.com/playlist?list=PL1234567890"


def _job_count(gate_api: TestClient) -> int:
    response = gate_api.get("/api/v1/downloads")
    assert response.status_code == 200
    return len(response.json()["items"])


def _settle_inspection(gate_api: TestClient, response) -> None:
    """Drain an accepted inspection so its worker exits before teardown."""
    if response.status_code != 202:
        return

    inspection_id = response.json()["inspection_id"]
    with gate_api.stream("GET", f"/api/v1/links/inspect/{inspection_id}/events") as events:
        assert events.status_code == 200
        terminal = False
        for line in events.iter_lines():
            if line.startswith("data: ") and '"terminal":true' in line:
                terminal = True
                break
        assert terminal


class TestValidLinks:
    def test_a_youtube_video_inspects_and_asks_for_review(self, gate_api: TestClient) -> None:
        response = gate_api.post(INSPECT, json={"url": VIDEO_URL})
        assert response.status_code == 202
        assert response.json()["phase"] == "inspecting_youtube"
        _settle_inspection(gate_api, response)

    def test_a_spotify_track_inspects_without_review(self, gate_api: TestClient) -> None:
        response = gate_api.post(INSPECT, json={"url": TRACK_URL})
        assert response.status_code == 202
        assert response.json()["phase"] == "reading_spotify"
        _settle_inspection(gate_api, response)


class TestRejectedLinksLeaveNoJob:
    @pytest.mark.parametrize(
        ("url", "status"),
        [
            (ALBUM_URL, 202),
            (PLAYLIST_URL, 202),
            ("https://example.com/whatever", 400),
            ("not a link at all", 422),
            ("ftp://example.com/track", 422),
        ],
    )
    def test_a_rejected_link_creates_no_download(
        self, gate_api: TestClient, url: str, status: int
    ) -> None:
        assert _job_count(gate_api) == 0

        response = gate_api.post(INSPECT, json={"url": url})
        _settle_inspection(gate_api, response)

        assert response.status_code == status
        assert _job_count(gate_api) == 0

    def test_inspecting_a_valid_link_alone_queues_nothing(self, gate_api: TestClient) -> None:
        """Inspection is a read; only POST /downloads commits work."""
        response = gate_api.post(INSPECT, json={"url": VIDEO_URL})
        assert response.status_code == 202
        _settle_inspection(gate_api, response)

        assert _job_count(gate_api) == 0
