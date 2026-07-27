---
status: draft
profile: full
profile-reason: novel bespoke integration — the fast path reads Spotify's undocumented embed payload, which has no published contract and can change without notice
parent: specs/001-core
---

# 002 — Fast, legible Spotify link inspection

## Core promise

Adding a Spotify link is as fast and as legible as adding a YouTube link.

## Context

Parent cycle 001-core is blocked at Gate 4 (v1 exit bar) on this. Measured on the
operator's proxied network:

| Path | Time | Fields |
|---|---|---|
| `spotdl save` (current) | 145–183s | title, artist, album, year, duration, art, track/disc, ISRC |
| Spotify embed payload | ~817ms | title, artist, year, duration, art — **no album, track/disc, ISRC** |

The slowness is per-request latency through the proxy, not one spotdl feature:
disabling its lyrics providers did not reliably help. `8dcda66` raised the inspect
timeout to 180s, which sits inside the observed range — so Add Music fails
intermittently with "That link could not be inspected." YouTube (~4.5s) and Deezer
are unaffected.

## Kernel

1. **Fast Spotify inspection path** over the existing httpx + proxy client.
2. **Automatic fallback to spotdl** when the fast path fails or returns unusable
   data, with the switch named in the UI — never silent.
3. **Operator-configurable inspection mode and per-provider timeouts**, persisted
   like existing proxy/provider settings.
4. **Honest inspection feedback**: named phases, elapsed time, working cancel. No
   fabricated percentage (CONVENTIONS.md).

### Kernel journey

1. Open Add Music, paste a Spotify track link.
2. See a named phase and a running elapsed time; a result returns in ~1s.
3. Review the candidate in S5, download it, and hear it play.
4. Paste a link whose fast lookup is forced to fail. See the phase change to the
   spotdl fallback, and the inspection still succeeds.
5. Start an inspection and press Cancel mid-flight. It stops, and no spotdl
   process survives.
6. Switch the mode to thorough in Settings. The next inspection uses spotdl and
   returns album, track/disc, and ISRC.
7. Restart the containers. The mode and timeouts persist.

## v1

- Fast Spotify inspector (embed payload), behind the shared provider protocol.
- Fallback chain fast → spotdl, with the reason surfaced.
- Settings: inspection mode (`fast` default, `thorough`), per-provider inspect
  timeouts, validated ranges, migration + masked GET, same shape as proxy settings.
- Add Music feedback: named phases, elapsed, cancel that kills the process group.
- Sanitized fixtures for the embed payload: success, changed shape, missing
  fields, timeout — the verified-fake rule applies since the contract is bespoke.
- Revert `8dcda66`'s 180s inspect / 200s nginx values to the configured defaults.

## Backlog (ranked)

1. Per-request mode override in the Add Music dialog.
2. Cached inspection results keyed by canonical URL.
3. Mode governing acquisition, not just inspection.
4. Fast paths for YouTube/Deezer inspection.

## Edge cases

- **Compounded timeouts.** Fast default + auto-fallback means a failure costs both
  timeouts in sequence. Per-provider defaults must bound the worst case below the
  single-provider worst case today, or this regresses the failure path.
- **Album lost permanently.** The worker applies reviewed values before Last.fm
  gap enrichment (ARCHITECTURE §721). A fast-path candidate reviewed with an empty
  album can therefore stay empty even though spotdl would have known it. Decide
  explicitly whether an unedited empty field counts as a gap Last.fm may fill.
- **Cancel during fallback** must terminate the spotdl subprocess by process
  group, reusing Task 7's cancellation machinery.
- Album/playlist/artist URLs keep the existing single-track rejection.
- Embed payload shape change → fallback, and a contract test that fails loudly.

## Non-functional

- Fast path p95 < 3s through a proxy; inspection never blocks the event loop.
- No fabricated progress; every phase name reflects real work.
- Undocumented-endpoint risk is contained to one adapter behind the existing
  `LinkInspector` protocol; provider response types never escape it.

## Tech constraints

Existing stack. `httpx[socks]` for the fast path, existing settings/migration
machinery, existing cancellation machinery. ARCHITECTURE.md is **patched, not
regenerated**. No new dependency is anticipated; one would need the dependency rule.

## Design direction

Inherits DESIGN.md unchanged. The only new surface is inspection feedback: calm,
truthful, legible — phase text plus elapsed seconds plus a real Cancel, matching
the existing job-phase presentation rather than inventing a second progress idiom.

## Out of scope

Bulk/album/playlist import (cycle 003), acquisition-path changes, provider
credentials, proxy performance itself.
