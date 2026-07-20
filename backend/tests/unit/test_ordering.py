"""Context ordering and keyset-cursor invariants."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from chillify.domain.errors import ValidationFailedError
from chillify.domain.models import Availability, LibrarySort, Track, TrackId
from chillify.domain.ordering import (
    album_sort_key,
    artist_sort_key,
    decode_cursor,
    encode_cursor,
    year_sort_key,
)

pytestmark = pytest.mark.unit

CREATED = datetime(2026, 7, 21, 12, 0, 0, 123000, tzinfo=UTC)


def make_track(
    track_id: str,
    *,
    title: str = "Track",
    artist: str = "Artist",
    album: str | None = "Album",
    release_year: int | None = 2000,
    disc_number: int | None = 1,
    track_number: int | None = 1,
) -> Track:
    return Track(
        id=TrackId(track_id),
        title=title,
        artist=artist,
        album=album,
        release_year=release_year,
        disc_number=disc_number,
        track_number=track_number,
        duration_ms=180_000,
        normalized_artist=artist.casefold(),
        normalized_title=title.casefold(),
        normalized_album=(album or "unknown album").casefold(),
        isrc=None,
        file_relpath=f"Music/{track_id}.mp3",
        artwork_relpath=None,
        mime_type="audio/mpeg",
        file_size_bytes=1024,
        content_sha256="0" * 64,
        availability=Availability.AVAILABLE,
        revision=1,
        created_at=CREATED,
        updated_at=CREATED,
    )


class TestAlbumOrder:
    def test_disc_then_track_then_title_then_id(self) -> None:
        first = make_track("a", disc_number=1, track_number=1)
        second = make_track("b", disc_number=1, track_number=2)
        third = make_track("c", disc_number=2, track_number=1)

        assert sorted([third, second, first], key=album_sort_key) == [first, second, third]

    def test_unknown_disc_and_track_sort_last(self) -> None:
        numbered = make_track("a", disc_number=1, track_number=1)
        unknown_track = make_track("b", disc_number=1, track_number=None)
        unknown_disc = make_track("c", disc_number=None, track_number=1)

        ordered = sorted([unknown_disc, unknown_track, numbered], key=album_sort_key)

        assert ordered == [numbered, unknown_track, unknown_disc]

    def test_identical_metadata_still_orders_by_id(self) -> None:
        first = make_track("aaa")
        second = make_track("bbb")

        assert sorted([second, first], key=album_sort_key) == [first, second]


class TestArtistOrder:
    def test_year_then_album_then_disc_and_track(self) -> None:
        early = make_track("a", release_year=1999, album="Zulu")
        late_alpha = make_track("b", release_year=2005, album="Alpha")
        late_beta = make_track("c", release_year=2005, album="Beta")

        ordered = sorted([late_beta, late_alpha, early], key=artist_sort_key)

        assert ordered == [early, late_alpha, late_beta]

    def test_unknown_year_sorts_last(self) -> None:
        dated = make_track("a", release_year=1900)
        undated = make_track("b", release_year=None)

        assert sorted([undated, dated], key=artist_sort_key) == [dated, undated]


class TestYearOrder:
    def test_artist_then_album_then_disc_and_track(self) -> None:
        first = make_track("a", artist="Aaa", album="Aaa")
        second = make_track("b", artist="Aaa", album="Bbb")
        third = make_track("c", artist="Bbb", album="Aaa")

        assert sorted([third, second, first], key=year_sort_key) == [first, second, third]


class TestCursor:
    def test_a_cursor_round_trips_for_its_own_sort(self) -> None:
        track = make_track("a")

        assert decode_cursor(encode_cursor(track, LibrarySort.TITLE), LibrarySort.TITLE) == (
            "track",
            "a",
        )

    def test_a_recent_cursor_carries_the_stored_timestamp_form(self) -> None:
        key, _ = decode_cursor(
            encode_cursor(make_track("a"), LibrarySort.RECENT), LibrarySort.RECENT
        )

        assert key == "2026-07-21T12:00:00.123Z"

    def test_a_cursor_from_another_sort_is_refused_rather_than_reanchored(self) -> None:
        cursor = encode_cursor(make_track("a"), LibrarySort.TITLE)

        with pytest.raises(ValidationFailedError) as caught:
            decode_cursor(cursor, LibrarySort.ARTIST)

        assert caught.value.field == "cursor"

    @pytest.mark.parametrize("cursor", ["", "not-a-cursor", "eyJhIjoxfQ"])
    def test_an_unreadable_cursor_is_a_field_failure(self, cursor: str) -> None:
        with pytest.raises(ValidationFailedError):
            decode_cursor(cursor, LibrarySort.RECENT)
