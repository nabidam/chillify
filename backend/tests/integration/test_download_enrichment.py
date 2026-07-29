"""Metadata and cover-art publication on the online-search download path."""

from __future__ import annotations

import io
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path

import pytest
from mutagen.id3 import ID3
from PIL import Image

from chillify.application.downloads import DownloadService
from chillify.composition import Composition
from chillify.domain.jobs import JobId, SourceType
from chillify.domain.protocols import (
    ImageArtifact,
    MetadataPatch,
    TrackCandidate,
)
from chillify.infrastructure.providers.registry import ProviderRegistry

pytestmark = pytest.mark.integration


@dataclass(frozen=True, slots=True)
class _GapEnricher:
    name: str = "test-enricher"

    def enrich(
        self,
        candidate: TrackCandidate,
        missing_fields: Sequence[str],
        proxy: str | None,
    ) -> MetadataPatch:
        assert "album" in missing_fields
        assert "release_year" in missing_fields
        assert "artwork_url" in missing_fields
        return MetadataPatch(
            album="Filled Album",
            release_year=2007,
            duration_ms=187_000,
            artwork_url="https://covers.invalid/filled.jpg",
        )


@dataclass(frozen=True, slots=True)
class _ArtworkFetcher:
    name: str = "test-artwork"

    def fetch(
        self,
        source: str,
        workspace: str,
        proxy: str | None,
    ) -> ImageArtifact:
        assert source == "https://covers.invalid/filled.jpg"
        buffer = io.BytesIO()
        Image.new("RGB", (4, 4), color=(30, 90, 160)).save(buffer, format="JPEG")
        target = Path(workspace) / "cover.jpg"
        target.write_bytes(buffer.getvalue())
        return ImageArtifact(location=str(target), byte_size=target.stat().st_size)


def _online_candidate() -> TrackCandidate:
    return TrackCandidate(
        provider="deezer",
        source_id="online-gap-1",
        source_url="https://www.deezer.com/track/9001",
        title="Catalog Song",
        artist="Catalog Artist",
        album=None,
        release_year=None,
        disc_number=2,
        track_number=4,
        duration_ms=None,
        isrc=None,
        artwork_url=None,
        acquisition_locator="ytsearch1:Catalog Artist Catalog Song",
        raw_fingerprint="fixture-fingerprint",
    )


def _service_with_enrichment(
    gate_downloads: DownloadService,
    gate_composition: Composition,
) -> DownloadService:
    existing = gate_composition.registry
    registry = ProviderRegistry(
        discovery=existing.discovery,
        acquisition=existing.acquisition,
        link_inspectors=existing.link_inspectors,
        spotify_api=existing.spotify_api,
        metadata_enricher=lambda: _GapEnricher(),
        artwork={"url": _ArtworkFetcher()},
    )
    return replace(gate_downloads, registry=registry)


class TestOnlineDownloadEnrichment:
    def test_missing_metadata_and_cover_are_published_and_embedded(
        self,
        gate_downloads: DownloadService,
        gate_composition: Composition,
    ) -> None:
        service = _service_with_enrichment(gate_downloads, gate_composition)
        job = service.request_download(_online_candidate(), SourceType.DEEZER_RESULT)

        service.run_job(JobId(job.id))

        detail = service.get_job(job.id)
        track_id = detail.job.result_track_id
        assert track_id is not None
        track = gate_composition.metadata_service().get_track_detail(track_id)
        assert track.track.album == "Filled Album"
        assert track.track.release_year == 2007
        assert track.track.duration_ms == 187_000
        assert track.track.artwork_relpath is not None

        enriching = [event for event in detail.events if event.phase.value == "enriching"][-1]
        assert enriching.payload == {
            "metadata": "filled",
            "filled_fields": 4,
            "artwork": "fetched",
        }

        cover = gate_composition.metadata_service().open_artwork(track_id)
        assert cover is not None
        assert cover.read_bytes().startswith(b"\xff\xd8")

        audio = next(gate_composition.settings.music_root.glob("Music/**/*.mp3"))
        tags = ID3(audio)
        assert tags.getall("APIC"), "the published MP3 should embed its front cover"
        assert tags.getall("TPOS")[0].text == ["2"]

    def test_enrichment_and_artwork_failures_do_not_fail_the_audio(
        self,
        gate_downloads: DownloadService,
        gate_composition: Composition,
    ) -> None:
        class _FailingEnricher:
            name = "failing-enricher"

            def enrich(self, *_args: object, **_kwargs: object) -> MetadataPatch:
                raise TimeoutError

        existing = gate_composition.registry
        service = replace(
            gate_downloads,
            registry=ProviderRegistry(
                discovery=existing.discovery,
                acquisition=existing.acquisition,
                metadata_enricher=lambda: _FailingEnricher(),
            ),
        )
        job = service.request_download(_online_candidate(), SourceType.DEEZER_RESULT)

        service.run_job(JobId(job.id))

        detail = service.get_job(job.id)
        assert detail.job.state.value == "completed"
        track_id = detail.job.result_track_id
        assert track_id is not None
        track = gate_composition.metadata_service().get_track_detail(track_id)
        assert track.track.album is None
        assert track.track.artwork_relpath is None
