"""The capability protocols every provider adapter implements.

These are the only shapes the application layer knows. A new provider satisfies
an existing protocol and is registered at the composition root; importing one
can never change acquisition behaviour, because nothing above this module names
a concrete adapter.

`TrackCandidate` is the single normalized boundary type. A provider response
type never travels past its own adapter.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from chillify.domain.jobs import JobPhase

# Reports downloaded fraction as 0..100, or None when the provider genuinely
# does not know. A None argument means "unknown", never "zero": the UI must not
# invent progress it was not given. A caller with nothing to report passes a
# no-op rather than None, so no adapter has to branch on the callback itself.
# Each progress update belongs to the stage that is actually executing.  This
# keeps durable job history truthful: a native MP3 never briefly appears to be
# converted after it has already been acquired.
ProgressCallback = Callable[[JobPhase, float | None], None]

# Consulted between phases and inside downloader hooks. True means the person
# asked to cancel and the adapter must stop and clean up.
CancelledCallback = Callable[[], bool]

# Maximum results a discovery query may request, matching the Deezer contract.
DISCOVERY_LIMIT_MAX = 50
DISCOVERY_LIMIT_DEFAULT = 25


@dataclass(frozen=True, slots=True)
class TrackCandidate:
    """One normalized remote track, from any provider, in one shape.

    A candidate is never playable: it describes something Chillify could
    acquire, not something it holds. `is_playable` exists so no component has
    to infer that from the absence of a field.
    """

    provider: str
    source_id: str | None
    source_url: str
    title: str
    artist: str
    album: str | None
    release_year: int | None
    disc_number: int | None
    track_number: int | None
    duration_ms: int | None
    isrc: str | None
    artwork_url: str | None
    acquisition_locator: str
    raw_fingerprint: str | None

    @property
    def is_playable(self) -> bool:
        """Always false. A remote candidate has no local file to stream."""
        return False


@dataclass(frozen=True, slots=True)
class AudioArtifact:
    """One acquired MP3 inside a task workspace, before it is published.

    Locations cross this boundary as text. The domain layer describes where a
    file is without owning a filesystem type, which is what keeps it free of
    `pathlib` and therefore free of the filesystem itself.
    """

    location: str
    duration_ms: int | None
    byte_size: int


@dataclass(frozen=True, slots=True)
class MetadataPatch:
    """Gap-fill values from an enricher. Only absent fields are ever merged."""

    title: str | None = None
    artist: str | None = None
    album: str | None = None
    release_year: int | None = None
    duration_ms: int | None = None
    artwork_url: str | None = None


@dataclass(frozen=True, slots=True)
class ImageArtifact:
    """One fetched, validated image inside a workspace."""

    location: str
    byte_size: int


@runtime_checkable
class DiscoveryProvider(Protocol):
    """Keyless search returning normalized, non-playable candidates."""

    # Declared read-only so an immutable adapter satisfies the protocol: an
    # adapter's identity is fixed at binding time and never reassigned.
    @property
    def name(self) -> str: ...

    def search(self, query: str, limit: int, proxy: str | None) -> Sequence[TrackCandidate]: ...


@runtime_checkable
class BrowseProvider(Protocol):
    """One named, first-page remote browse capability."""

    @property
    def name(self) -> str: ...

    def browse(self, section: str, proxy: str | None) -> Sequence[TrackCandidate]: ...


@runtime_checkable
class LinkInspector(Protocol):
    """Recognition and metadata-only inspection of one submitted URL."""

    @property
    def name(self) -> str: ...

    def supports(self, url: str) -> bool: ...

    def inspect(self, url: str, proxy: str | None) -> TrackCandidate: ...


@runtime_checkable
class AcquisitionProvider(Protocol):
    """Retrieval of one candidate's audio into a task-local workspace."""

    @property
    def name(self) -> str: ...

    def acquire(
        self,
        candidate: TrackCandidate,
        workspace: str,
        proxy: str | None,
        progress: ProgressCallback,
        cancelled: CancelledCallback,
    ) -> AudioArtifact: ...


@runtime_checkable
class MetadataEnricher(Protocol):
    """Optional gap fill. Its failure is a warning, never a failed job."""

    @property
    def name(self) -> str: ...

    def enrich(
        self,
        candidate: TrackCandidate,
        missing_fields: Sequence[str],
        proxy: str | None,
    ) -> MetadataPatch: ...


@runtime_checkable
class ArtworkFetcher(Protocol):
    """Retrieval of one cover image through the validated outbound policy."""

    @property
    def name(self) -> str: ...

    def fetch(self, source: str, workspace: str, proxy: str | None) -> ImageArtifact: ...
