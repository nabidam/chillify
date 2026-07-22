"""Link inspection rejects unsupported, malformed, and bulk links without touching
the database — the "no durable job" guarantee at its lowest layer.

These are pure: the inspectors are stubs and the session factory is poisoned, so
a rejected link that reached persistence would fail loudly rather than silently
create work.
"""

from __future__ import annotations

import pytest

from chillify.application.links import LinkInspectionService, RegisteredInspector
from chillify.domain.errors import UnsupportedEntityError, ValidationFailedError
from chillify.domain.jobs import JobProvider, SourceType
from chillify.domain.protocols import TrackCandidate


def _candidate() -> TrackCandidate:
    return TrackCandidate(
        provider="youtube",
        source_id="u7K72X4eo_s",
        source_url="https://www.youtube.com/watch?v=u7K72X4eo_s",
        title="Teardrop",
        artist="Massive Attack",
        album=None,
        release_year=None,
        disc_number=None,
        track_number=None,
        duration_ms=None,
        isrc=None,
        artwork_url=None,
        acquisition_locator="https://www.youtube.com/watch?v=u7K72X4eo_s",
        raw_fingerprint=None,
    )


class _StubInspector:
    """Recognizes URLs containing its host token; optionally rejects as bulk."""

    def __init__(self, token: str, *, bulk: bool = False) -> None:
        self._token = token
        self._bulk = bulk

    def supports(self, url: str) -> bool:
        return self._token in url

    def inspect(self, url: str, proxy: str | None) -> TrackCandidate:
        if self._bulk:
            raise UnsupportedEntityError("That is a playlist.", field="url")
        return _candidate()


def _poison_factory():  # type: ignore[no-untyped-def]
    raise AssertionError("a rejected link must not touch the database")


def _service(*inspectors: RegisteredInspector) -> LinkInspectionService:
    return LinkInspectionService(session_factory=_poison_factory, inspectors=tuple(inspectors))


@pytest.mark.unit
class TestRejectionsCreateNoJob:
    def test_an_empty_link_is_a_field_error(self) -> None:
        with pytest.raises(ValidationFailedError):
            _service().inspect("   ")

    def test_a_non_url_is_a_field_error(self) -> None:
        with pytest.raises(ValidationFailedError):
            _service().inspect("just some words")

    def test_a_non_web_scheme_is_a_field_error(self) -> None:
        with pytest.raises(ValidationFailedError):
            _service().inspect("ftp://example.com/track")

    def test_an_over_long_link_is_a_field_error(self) -> None:
        with pytest.raises(ValidationFailedError):
            _service().inspect("https://example.com/" + "a" * 4000)

    def test_an_unrecognized_host_is_unsupported(self) -> None:
        service = _service(RegisteredInspector(JobProvider.YT_DLP, _StubInspector("youtube.com")))

        with pytest.raises(UnsupportedEntityError):
            service.inspect("https://vimeo.com/12345")

    def test_a_recognized_but_bulk_link_is_unsupported(self) -> None:
        service = _service(
            RegisteredInspector(JobProvider.YT_DLP, _StubInspector("youtube.com", bulk=True))
        )

        with pytest.raises(UnsupportedEntityError):
            service.inspect("https://www.youtube.com/playlist?list=PL1")


@pytest.mark.unit
class TestPolicyRouting:
    """A recognized single link carries its provider's source type and review
    requirement — but this path does read the library, so it uses a real DB."""

    def test_youtube_requires_review(self, gate_composition) -> None:  # type: ignore[no-untyped-def]
        service = gate_composition.link_inspection_service()

        inspection = service.inspect("https://www.youtube.com/watch?v=u7K72X4eo_s")

        assert inspection.provider is JobProvider.YT_DLP
        assert inspection.source_type is SourceType.YOUTUBE_VIDEO
        assert inspection.review_required is True
        assert inspection.existing_track_id is None

    def test_spotify_does_not_require_review(self, gate_composition) -> None:  # type: ignore[no-untyped-def]
        service = gate_composition.link_inspection_service()

        inspection = service.inspect("https://open.spotify.com/track/2cGxRwrMyEAp8dEbuZaVv6")

        assert inspection.provider is JobProvider.SPOTDL
        assert inspection.source_type is SourceType.SPOTIFY_TRACK
        assert inspection.review_required is False
