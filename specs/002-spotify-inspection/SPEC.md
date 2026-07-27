---
status: draft
profile: full
profile-reason: spans two subsystems — Spotify link inspection and the Last.fm gap-enrichment path, which ARCHITECTURE specifies but which was never wired up and is folded into this cycle
parent: specs/001-core
---

# 002 — Fast, legible Spotify link inspection

## Core promise

Adding a Spotify link is as fast and as legible as adding a YouTube link.

## Context

Parent cycle 001-core is blocked at Gate 4 (v1 exit bar) on this. Measured on the
operator's proxied network, `spotdl save` takes **145–183s** per Spotify link —
per-request latency through the proxy, not one spotdl feature; disabling its lyrics
providers did not reliably help. That range straddles the 180s inspect timeout, so
Add Music fails intermittently. YouTube (~4.5s) and Deezer are unaffected.

The independent architecture review (2026-07-27) overturned two premises of the
first draft of this spec:

- **Spotify publishes an official API for this.** `GET /v1/tracks/{id}` under
  Client Credentials returns title, artist, album, disc/track number, ISRC,
  duration, release date and images — documented and versioned. The first draft
  designed a scraper of Spotify's undocumented embed payload that returned *less*.
- **Last.fm gap enrichment does not exist.** `downloads.py` records an `ENRICHING`
  phase and does nothing; `LastfmEnricher.enrich()` is implemented but called from
  nowhere. The first draft leaned on it to fill fields the scraper missed.

## Kernel

1. **Fast Spotify inspection** via the official Web API over the existing proxied
   HTTP client, using operator-supplied client credentials.
2. **Automatic fallback to spotdl** when credentials are absent or the API call
   fails, with the switch named in the UI — never silent.
3. **Operator-configurable inspection mode and per-provider timeouts**, plus
   Spotify credentials, persisted with the existing settings/Fernet machinery.
4. **Honest inspection feedback**: named phases, elapsed time, working cancel. No
   fabricated percentage (CONVENTIONS.md).
5. **Working Last.fm gap enrichment**, so the `ENRICHING` phase reports real work
   and untouched empty fields are actually filled.

### Kernel journey

1. Open Settings, paste Spotify client credentials, save. They are stored
   encrypted and echoed back only as configured.
2. Open Add Music, paste a Spotify track link.
3. See a named phase and running elapsed seconds; a result returns in ~1s with
   album, disc, and track number present.
4. Review and download it; hear it play.
5. Clear the credentials, paste another link, and watch the phase name the spotdl
   fallback while the elapsed timer continues rather than resetting.
6. Start an inspection and press Cancel mid-phase. It stops, and no spotdl process
   survives.
7. Add a YouTube link whose album is unknown, leave the album untouched through
   review, and download it — the finished track's album is filled by Last.fm.
8. Restart the containers. Credentials, mode, and timeouts persist.

## v1

- Official Spotify Web API inspector behind the existing `LinkInspector` protocol.
- Fallback chain: Spotify API → spotdl, with the reason surfaced.
- Settings: Spotify client credentials (Fernet, masked), inspection mode
  (`fast` default, `thorough`), per-path inspect timeouts, validated ranges,
  migration and rollback.
- Inspection as a tracked, cancellable operation: named phases, elapsed, cancel.
- Last.fm gap enrichment wired into the download path, with a field actually
  distinguishing *never touched* from *deliberately cleared*.
- Revert `8dcda66`'s 180s inspect / 200s nginx stopgaps to configured defaults.

## Backlog (ranked)

1. Per-request mode override in the Add Music dialog.
2. Cached inspection results keyed by canonical URL.
3. Mode governing acquisition, not just inspection.
4. Fast paths for YouTube/Deezer inspection.

## Edge cases

- **Credentials absent** is the default state on upgrade: the fast path is
  unavailable and inspection falls back to spotdl, which must be stated in
  Settings rather than presented as a failure.
- **Compounded timeouts.** Fast + fallback pays both in sequence; per-path
  defaults must bound the worst case below today's single-path 180s.
- **Cancel during fallback** must terminate the spotdl subprocess by process
  group. The existing cancel trigger is a database lease on a persisted job and
  does not apply to an inspection — a real trigger must be designed, not assumed.
- **Enrichment must not overwrite a deliberate clear.** A field the person edited
  is their answer; only a never-touched empty field is a gap.
- Album/playlist/artist URLs keep the existing single-track rejection.
- Spotify API 429/rate limiting → typed error and fallback, never a silent retry
  storm.

## Non-functional

- Fast-path inspection p95 < 3s through a proxy; inspection never blocks the
  event loop.
- No fabricated progress; every phase name reflects real work — which is why the
  dead `ENRICHING` phase is in scope rather than left lying.
- Spotify client secret never appears in an API body, log, or subprocess argv.

## Tech constraints

Existing stack. `httpx[socks]` for the Spotify API over the shared proxied client;
existing settings/Fernet/migration machinery; existing `os.killpg` primitive. The
Spotify Web API is well-known and documented, so its wire contract ships compact
(≤1 page) and the verified-fake rule applies to its fixtures. ARCHITECTURE.md is
**patched, not regenerated**. No new runtime dependency is anticipated; one would
require the dependency rule.

## Design direction

Inherits DESIGN.md unchanged. The only new surfaces are inspection feedback and a
credentials block in Settings: calm, truthful, legible — phase text plus elapsed
seconds plus a real Cancel, matching the existing job-phase presentation rather
than inventing a second progress idiom.

## Out of scope

Bulk/album/playlist import (cycle 003), acquisition-path changes, user-account
Spotify auth (Client Credentials only, no user login), proxy performance itself.
