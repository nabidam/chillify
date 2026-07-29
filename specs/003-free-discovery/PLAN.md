# 003 — Free remote discovery and Spotify references

**Status:** Completed and operator-tested 2026-07-29.

## Goal

Let a household find and acquire music by title, artist, album text, or an
individual Spotify track link without Spotify Premium, Spotify developer
credentials, an Apple account, or a paid metadata API.

## Product flow

1. Typing still searches only the local library.
2. **Search online** explicitly queries MusicBrainz, Apple iTunes Search, and
   Deezer. Results remain non-playable until queued.
3. A Spotify track link is resolved through Spotify's public oEmbed endpoint.
   Because oEmbed does not provide artist, album, duration, or ISRC, Chillify
   searches the independent catalogs by the reference title and requires the
   person to choose a match.
4. Every selected catalog candidate uses the existing yt-dlp acquisition path,
   duplicate checks, durable queue, conversion, tagging, and publication.

## Provider policy

- **MusicBrainz:** primary open metadata; meaningful User-Agent and one request
  per second.
- **Apple:** fast keyless song search. Apple previews are never acquired;
  documented artwork is retained for the selected track, and the store URL is
  retained as provenance.
- **Deezer:** optional additional catalog coverage.
- **Spotify:** oEmbed reference only. No Web API, OAuth, Premium, page scraping,
  private JSON, or Spotify audio.
- **SpotDL:** historical/advanced compatibility code only; not part of the
  supported UI journey.

## Delivery

- No staged demo gates.
- Existing automated backend/frontend verification remains required.
- The operator walks the final journeys against the running application.
- Alembic migration `0004_catalog_track_sources` widens durable source
  provenance to `apple` and `musicbrainz` without rewriting existing rows.
- API, worker, and migration containers share the
  `host.docker.internal:host-gateway` alias for consistent host Redis/proxy
  access on Linux.

## Operator journeys

1. Search a title or artist online, observe results from multiple providers,
   choose one, queue it, and play the completed local track.
2. Paste one Spotify track URL, verify the Spotify reference title, choose the
   correct artist/album from catalog matches, queue it, and play it locally.
3. Disable internet or break the proxy and confirm the local library/player
   remain usable while online search fails clearly.

## Deferred

- Spotify album/playlist expansion: oEmbed cannot enumerate their tracks.
- Cross-provider result deduplication/ranking beyond provider labels.
- Persisted server-side catalog cache.
- Removing the archived Spotify Web API/SpotDL experiment after compatibility
  and migration review.
