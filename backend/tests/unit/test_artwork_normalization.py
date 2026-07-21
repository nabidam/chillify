"""Cover-image validation and normalization.

Everything that reaches the tag writer or the managed `Artwork` directory has
been through `normalize_cover`, so these are the rules that decide what a
person's chosen image is allowed to become.
"""

from __future__ import annotations

import io

import pytest
from PIL import Image

from chillify.domain.errors import ArtworkTooLargeError, ArtworkUnreadableError
from chillify.infrastructure.media.artwork import (
    ARTWORK_MAX_BYTES,
    ARTWORK_MAX_EDGE,
    artwork_relpath,
    normalize_cover,
    stage_relpath,
)

pytestmark = pytest.mark.unit


def _encoded(width: int, height: int, *, image_format: str = "PNG") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color=(20, 140, 200)).save(buffer, format=image_format)
    return buffer.getvalue()


class TestNormalizeCover:
    def test_a_png_becomes_a_jpeg(self) -> None:
        cover = normalize_cover(_encoded(300, 300))

        with Image.open(io.BytesIO(cover.payload)) as image:
            assert image.format == "JPEG"

    def test_a_transparent_image_is_flattened_rather_than_refused(self) -> None:
        buffer = io.BytesIO()
        Image.new("RGBA", (200, 200), color=(0, 0, 0, 0)).save(buffer, format="PNG")

        cover = normalize_cover(buffer.getvalue())

        with Image.open(io.BytesIO(cover.payload)) as image:
            assert image.mode == "RGB"

    def test_an_oversized_scan_is_bounded_to_the_cover_edge(self) -> None:
        cover = normalize_cover(_encoded(3000, 2000))

        with Image.open(io.BytesIO(cover.payload)) as image:
            assert max(image.size) == ARTWORK_MAX_EDGE

    def test_a_small_image_keeps_its_dimensions(self) -> None:
        cover = normalize_cover(_encoded(240, 240))

        with Image.open(io.BytesIO(cover.payload)) as image:
            assert image.size == (240, 240)

    def test_the_digest_describes_the_re_encoded_bytes(self) -> None:
        cover = normalize_cover(_encoded(300, 300))

        assert cover.size_bytes == len(cover.payload)
        assert len(cover.content_sha256) == 64

    def test_bytes_beyond_the_accepted_size_are_refused_before_decoding(self) -> None:
        with pytest.raises(ArtworkTooLargeError) as failure:
            normalize_cover(b"\x89PNG" + bytes(ARTWORK_MAX_BYTES))

        assert failure.value.status_code == 413

    def test_an_empty_submission_is_reported_as_unreadable(self) -> None:
        with pytest.raises(ArtworkUnreadableError):
            normalize_cover(b"")

    def test_a_non_image_is_reported_without_quoting_the_decoder(self) -> None:
        with pytest.raises(ArtworkUnreadableError) as failure:
            normalize_cover(b"this is a text file, not a cover")

        assert failure.value.status_code == 400
        assert "PIL" not in failure.value.message
        assert "cannot identify" not in failure.value.message.lower()


class TestManagedLocations:
    def test_a_track_cover_is_named_by_its_track_id(self) -> None:
        assert artwork_relpath("019f-abc") == "Artwork/019f-abc.jpg"

    def test_a_stage_lives_under_the_internal_staging_tree(self) -> None:
        relative = stage_relpath("019f-stage")

        assert relative.startswith(".chillify/staging/artwork/")
        assert relative.endswith(".jpg")
