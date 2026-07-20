"""The versioned normalizer's documented invariants."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from chillify.domain.errors import ValidationFailedError
from chillify.domain.normalization import (
    UNKNOWN_ALBUM,
    UNKNOWN_ARTIST,
    decode_album_key,
    decode_artist_key,
    encode_album_key,
    encode_artist_key,
    fold_name,
    normalize_album,
    normalize_artist,
    normalize_isrc,
    normalize_title,
    validate_profile_name,
    validate_release_year,
)

pytestmark = pytest.mark.unit

CLOCK = datetime(2026, 7, 21, tzinfo=UTC)


class TestMetadataKeys:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("Björk", "bjork"),
            ("BJÖRK", "bjork"),
            ("  Sigur   Rós  ", "sigur ros"),
            ("Sgt. Pepper", "sgt pepper"),
            ("Sgt Pepper", "sgt pepper"),
            # Fullwidth latin, written as escapes so the source stays ASCII.
            ("\uff21\uff23\uff24\uff23", "acdc"),
        ],
    )
    def test_case_accents_punctuation_and_width_all_fold_together(
        self, value: str, expected: str
    ) -> None:
        assert normalize_artist(value) == expected

    def test_a_value_that_normalizes_away_falls_back_deterministically(self) -> None:
        assert normalize_artist("!!! ???") == UNKNOWN_ARTIST

    def test_an_absent_album_shares_one_unknown_context(self) -> None:
        assert normalize_album(None) == UNKNOWN_ALBUM
        assert normalize_album("   ") == UNKNOWN_ALBUM

    def test_titles_and_artists_use_the_same_rules(self) -> None:
        assert normalize_title("Où Est Ma Tête?") == normalize_artist("ou est ma tete")


class TestNameFolding:
    def test_folding_ignores_case_and_whitespace_runs(self) -> None:
        assert fold_name("  The   HOUSE ") == fold_name("the house")

    def test_folding_keeps_punctuation_that_distinguishes_two_households(self) -> None:
        assert fold_name("DJ K.") != fold_name("DJ K")

    def test_a_stored_name_keeps_its_display_form(self) -> None:
        assert validate_profile_name("  Ada   Lovelace ") == "Ada Lovelace"

    @pytest.mark.parametrize("raw", ["", "   ", "\t\n"])
    def test_an_empty_name_is_a_field_failure(self, raw: str) -> None:
        with pytest.raises(ValidationFailedError) as caught:
            validate_profile_name(raw)

        assert caught.value.field == "name"

    def test_a_name_beyond_the_documented_length_is_rejected(self) -> None:
        with pytest.raises(ValidationFailedError):
            validate_profile_name("x" * 41)


class TestReleaseYear:
    def test_next_year_is_accepted_relative_to_the_injected_clock(self) -> None:
        assert validate_release_year(2027, now=CLOCK) == 2027

    def test_two_years_ahead_of_the_injected_clock_is_rejected(self) -> None:
        with pytest.raises(ValidationFailedError) as caught:
            validate_release_year(2028, now=CLOCK)

        assert caught.value.field == "release_year"

    @pytest.mark.parametrize("year", [999, 0, -1])
    def test_years_below_the_floor_are_rejected(self, year: int) -> None:
        with pytest.raises(ValidationFailedError):
            validate_release_year(year, now=CLOCK)

    def test_an_absent_year_stays_absent(self) -> None:
        assert validate_release_year(None, now=CLOCK) is None


class TestIsrc:
    def test_a_formatted_code_is_canonicalized(self) -> None:
        assert normalize_isrc("us-rc1-72-12345") == "USRC17212345"

    @pytest.mark.parametrize("value", [None, "", "   "])
    def test_absence_is_not_a_malformed_code(self, value: str | None) -> None:
        assert normalize_isrc(value) is None

    @pytest.mark.parametrize("value", ["USRC1721234", "1SRC17212345", "USRC1721234X"])
    def test_a_malformed_code_is_a_field_failure(self, value: str) -> None:
        with pytest.raises(ValidationFailedError) as caught:
            normalize_isrc(value)

        assert caught.value.field == "isrc"


class TestContextKeys:
    def test_an_artist_key_round_trips(self) -> None:
        key = encode_artist_key("sigur ros")

        assert decode_artist_key(key) == "sigur ros"

    def test_an_album_key_carries_both_halves(self) -> None:
        key = encode_album_key("sigur ros", "takk")

        assert decode_album_key(key) == ("sigur ros", "takk")

    def test_same_named_albums_by_different_artists_are_separate_contexts(self) -> None:
        assert encode_album_key("artist one", "greatest hits") != encode_album_key(
            "artist two", "greatest hits"
        )

    def test_keys_carry_no_padding(self) -> None:
        assert "=" not in encode_album_key("a", "b")

    @pytest.mark.parametrize("key", ["not base64!", "YWJj=", "", "IA"])
    def test_a_noncanonical_key_is_refused_before_it_reaches_a_query(self, key: str) -> None:
        with pytest.raises(ValidationFailedError):
            decode_artist_key(key)

    def test_an_artist_key_is_not_accepted_as_an_album_key(self) -> None:
        with pytest.raises(ValidationFailedError):
            decode_album_key(encode_artist_key("sigur ros"))
