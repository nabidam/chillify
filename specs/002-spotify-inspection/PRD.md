---
status: draft
---

# PRD — 002 Fast, legible Spotify link inspection

Delta against the 001-core PRD. Requirements here add to, and where stated
override, the existing document; nothing else in it changes.

## Settled decisions

SPEC.md flagged two consequences for Phase 2 to settle rather than assume.

**D1 — Timeout defaults must bound the fallback worst case.** Fast-first with
automatic fallback means a failure pays both timeouts in sequence. Defaults:
fast **8s**, SpotDL **150s**, yt-dlp **60s**. Fast-then-fallback worst case is
therefore **158s**, below today's single-path 180s, so the failure path improves
rather than regresses. The fast timeout is deliberately near the measured p95
(~1s) with wide margin: its job is to fail over quickly, not to keep trying.

**D2 — An untouched empty field is a gap; an edited one is an answer.** A
fast-path candidate carries album, disc, and track number as *not-yet-known*,
distinct from *known to be empty*. ARCHITECTURE §721 keeps its rule that reviewed
values are applied before Last.fm enrichment — this does not change it. A field
the person never touched is not a reviewed value, so it stays eligible for
enrichment. A field they edited, including one they deliberately cleared, is
their answer and is never overwritten. This makes the fast path's thinner
metadata self-healing instead of permanently lossy.

## Functional requirements

- **FR1** Spotify track links are inspected by a fast path reading Spotify's
  embed payload over the existing proxied HTTP client, returning title, artist,
  release year, duration, and cover art.
- **FR2** When the fast path fails, times out, or yields a candidate missing
  title or artist, the system falls back to SpotDL automatically and reports the
  switch by name in S4. The fallback is never silent.
- **FR3** Inspection mode is an operator setting: `fast` (default) or `thorough`.
  `thorough` uses SpotDL first and does not fall back to the fast path.
- **FR4** Inspect timeouts are configurable per path (fast, spotdl, ytdlp),
  persisted with the existing settings machinery and applied without a restart.
- **FR5** S4 reports a named phase and elapsed seconds throughout inspection, and
  offers Cancel at every phase.
- **FR6** Cancel terminates inspection and any provider subprocess by process
  group, reusing the existing cancellation machinery.
- **FR7** Album, disc, and track number absent from a fast-path candidate are
  marked not-yet-known and remain eligible for Last.fm gap enrichment per D2.
- **FR8** Album, playlist, and artist URLs keep the existing single-track
  rejection, unchanged, on both paths.

## Non-functional requirements

| NFR | Budget | Measurement |
|---|---|---|
| NFR-1 | Fast-path inspection p95 < 3s through a proxy | `scripts/verify/nfr.sh` records 20 sequential fast-path inspections against the fixture adapter and the live gate stack; asserts p95 |
| NFR-2 | Fast-then-fallback worst case < 160s | contract test asserts the sum of configured fast + spotdl defaults; e2e forces a fast failure and measures wall clock |
| NFR-3 | Cancel leaves no surviving provider process | e2e cancels mid-inspection, then asserts no matching PID in the api container |
| NFR-4 | Inspection never blocks the event loop | integration test issues a second request during an in-flight slow inspection and asserts it is served |

## User stories

- As the household operator, I paste a Spotify link and get a result in about a
  second, so adding music does not feel broken.
- As the operator, when the fast lookup stops working I still get my track,
  because the system falls back and tells me it did.
- As the operator, I can see what inspection is actually doing and stop it.
- As the operator, I can choose thorough inspection when I care more about album
  and track numbering than speed.

## Acceptance criteria

- **AC1** Paste a Spotify track link in S4 with mode `fast`; a candidate with
  title, artist, year, duration, and cover appears in under 3 seconds.
- **AC2** With the fast path forced to fail, paste the same link; S4 visibly
  names the SpotDL fallback, the elapsed timer continues rather than resetting,
  and a candidate still appears.
- **AC3** Start an inspection and press Cancel; the dialog returns to the
  editable URL with the input preserved, and no SpotDL process remains running in
  the api container.
- **AC4** Set mode to `thorough` in S12, save, and inspect a Spotify link; the
  returned candidate includes album, disc, and track number.
- **AC5** Restart the containers and reopen S12; the saved mode and all three
  timeouts are unchanged.
- **AC6** Inspect via the fast path, leave album untouched through S5, and
  complete the download; the finished track shows an album filled by Last.fm
  enrichment.
- **AC7** Inspect via the fast path, clear the album field deliberately in S5,
  and complete the download; the finished track's album remains empty.
- **AC8** Enter a timeout outside its permitted range in S12; the field is
  rejected with the permitted range stated and nothing is saved.
- **AC9** Paste a Spotify album or playlist URL in either mode; the existing
  single-track rejection appears unchanged.

## Validation rules

- Timeouts are integers in seconds: fast 1–30, spotdl 30–600, ytdlp 10–300.
- Mode is exactly `fast` or `thorough`; any other value is rejected at the API.
- A fast-path candidate missing title or artist is treated as a failed lookup and
  triggers fallback rather than being returned partially.

## Error cases

- Embed payload unreachable, non-2xx, or unparseable → fallback (mode `fast`) or
  typed provider error (mode `thorough`).
- Embed payload shape changed such that required fields are absent → fallback,
  and the contract test covering the recorded shape fails loudly in CI.
- Both paths fail → typed provider error naming both attempts; input preserved.
- Cancellation → distinct from failure in both the UI and the error taxonomy.

## Edge cases

- Mode changed while an inspection is in flight: the in-flight request keeps the
  mode it started with.
- Timeout lowered below an in-flight inspection's elapsed time: the in-flight
  request keeps its original timeout.
- Fast path succeeds but returns a duplicate of an existing local track: the
  existing duplicate handling applies, unchanged.
- Proxy unconfigured: the fast path uses a direct connection exactly as other
  adapters do; proxy-first fail-closed behavior is unchanged.

## Constraints

Existing stack only. ARCHITECTURE.md is patched, not regenerated. No new runtime
dependency is anticipated; one would require the dependency rule. The embed
payload is undocumented, so the verified-fake rule applies: sanitized fixtures for
success, changed shape, missing fields, and timeout, and the fast adapter runs the
same shared `LinkInspector` protocol suite as the SpotDL adapter.

## Out of scope

Bulk/album/playlist import, acquisition-path changes, per-request mode override,
inspection result caching, fast paths for YouTube or Deezer, proxy performance.

## Future improvements

Backlog order from SPEC.md: per-request override, cached inspection results, mode
governing acquisition, fast paths for other providers.
