"""The gate seed's scenario track sets.

These assert the shape of the fixture data each scenario seeds, without touching
a database: the browse/organize/listen gate needs variety to browse over, and
the earlier gates must keep seeding exactly their two base tracks.
"""

from __future__ import annotations

from chillify.gate_seed import (
    BASE_TRACKS,
    DEFAULT_SCENARIO,
    LISTENING_TRACKS,
    tracks_for_scenario,
)


def test_default_scenario_is_the_two_base_tracks() -> None:
    tracks = tracks_for_scenario(DEFAULT_SCENARIO)
    assert tracks == BASE_TRACKS
    assert len(tracks) == 2
    assert {track.artist for track in tracks} == {"Daft Punk"}
    assert all(track.release_year is not None for track in tracks)


def test_unknown_scenario_falls_back_to_the_base_tracks() -> None:
    # A decorative chunk label such as "recovery" must not change what an
    # earlier gate seeds.
    assert tracks_for_scenario("recovery") == BASE_TRACKS
    assert tracks_for_scenario("nonsense") == BASE_TRACKS


def test_listening_scenario_keeps_the_base_tracks() -> None:
    tracks = tracks_for_scenario("listening")
    assert tracks == LISTENING_TRACKS
    for base in BASE_TRACKS:
        assert base in tracks


def test_listening_scenario_offers_browse_variety() -> None:
    tracks = tracks_for_scenario("listening")

    artists = {track.artist for track in tracks}
    albums = {track.album for track in tracks}
    known_years = {track.release_year for track in tracks if track.release_year is not None}

    assert len(artists) >= 3, "several artists to browse and compare queue order"
    assert len(albums) >= 3, "several albums to browse"
    assert len(known_years) >= 3, "several distinct release years to browse"


def test_listening_scenario_has_exactly_one_unknown_year_track() -> None:
    tracks = tracks_for_scenario("listening")
    unknown = [track for track in tracks if track.release_year is None]
    assert len(unknown) == 1, "a first-class Unknown Year grouping to browse"
