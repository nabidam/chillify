"""Resolve a public Spotify track reference and find catalog matches."""

from __future__ import annotations

from dataclasses import dataclass

from chillify.application.search import RemoteResult, SearchService
from chillify.infrastructure.providers.spotify_oembed import (
    SpotifyOEmbedReferenceResolver,
    TrackReference,
)


@dataclass(frozen=True, slots=True)
class SpotifyLinkMatches:
    """A limited Spotify reference plus independent metadata candidates."""

    reference: TrackReference
    matches: tuple[RemoteResult, ...]


@dataclass(frozen=True, slots=True)
class SpotifyLinkService:
    """Use Spotify only to name a track, then leave its platform boundary."""

    resolver: SpotifyOEmbedReferenceResolver
    search: SearchService

    def resolve(self, url: str, *, limit: int = 10) -> SpotifyLinkMatches:
        reference = self.resolver.resolve(url, self.search.proxy_provider())
        matches = self.search.search_catalog(reference.title, provider="all", limit=limit)
        return SpotifyLinkMatches(reference=reference, matches=matches)
