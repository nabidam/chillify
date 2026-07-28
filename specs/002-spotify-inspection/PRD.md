---
status: cancelled
cancelled: 2026-07-29
---

# PRD — 002 Fast, legible Spotify link inspection

> **Cancelled 2026-07-29.** The requirements below are preserved as historical
> product reasoning, not active acceptance criteria. A live Spotify API probe
> was rejected with `403 Active premium subscription required for the owner of
> the app`; paying for Premium is explicitly out of scope. See
> [CANCELLATION.md](CANCELLATION.md) before reusing any part of this PRD.

Delta against the 001-core PRD. Requirements here add to, and where stated
override, the existing document; nothing else in it changes.

Revised after the 2026-07-27 architecture review, which found (a) Spotify's
official Web API returns more than the embed payload the first draft proposed
scraping, and (b) Last.fm gap enrichment is specified but never actually runs.

## Settled decisions

**D1 — Timeout defaults bound the fallback worst case.** Fast-first with automatic
fallback pays both timeouts in sequence. Defaults: Spotify API **8s**, spotdl
**150s**, yt-dlp **60s**. Worst case is therefore **158s**, below today's
single-path 180s, so the failure path improves rather than regresses. The 8s fast
timeout sits well above the measured ~1s p95: its job is to fail over quickly, not
to keep trying.

**D2 — An untouched empty field is a gap; an edited one is an answer.** A candidate
field the person never edited is not a reviewed value and stays eligible for
Last.fm enrichment. A field they edited, including one deliberately cleared, is
their answer and is never overwritten. ARCHITECTURE §7's ordering rule is unchanged;
what changes is what counts as *reviewed*. This requires a real touched/untouched
signal from the review form through to the worker — it is not representable today.

**D3 — Credentials absent is a supported state, not an error.** On upgrade nobody
has configured Spotify credentials, so the fast path is simply unavailable and
inspection uses spotdl. Settings states this plainly; Add Music names the fallback.

## Functional requirements

- **FR1** Spotify track links are inspected via the official Web API
  (`GET /v1/tracks/{id}`, Client Credentials) over the existing proxied HTTP
  client, returning title, artist, album, disc number, track number, ISRC,
  duration, release year, and cover art.
- **FR2** Spotify client id and secret are operator settings, stored encrypted with
  the existing Fernet machinery and never echoed back after persistence.
- **FR3** When credentials are absent, the token request fails, or the track
  request fails or times out, inspection falls back to spotdl automatically and
  reports the switch by name in S4. The fallback is never silent.
- **FR4** Inspection mode is an operator setting: `fast` (default) or `thorough`.
  `thorough` uses spotdl first and does not fall back to the API.
- **FR5** Inspect timeouts are configurable per path (spotify, spotdl, ytdlp),
  persisted, and applied without a restart.
- **FR6** S4 reports a named phase and elapsed seconds throughout inspection, and
  offers Cancel at every phase.
- **FR7** Cancel terminates inspection and any provider subprocess by process
  group, and is distinguishable from failure in the error taxonomy.
- **FR8** The download path calls Last.fm gap enrichment, so the `ENRICHING` phase
  performs real work; only fields the person never touched are eligible.
- **FR9** A candidate carries, end to end, which fields the person edited, so
  enrichment can honor D2.
- **FR10** Album, playlist, and artist URLs keep the existing single-track
  rejection, unchanged, on every path.

## Non-functional requirements

| NFR | Budget | Measurement |
|---|---|---|
| NFR-1 | Spotify API inspection p95 < 3s through a proxy | `scripts/verify/nfr.sh` runs 20 sequential inspections against the fixture adapter and the live gate stack; asserts p95 |
| NFR-2 | Fast-then-fallback worst case < 160s | contract test asserts configured defaults sum below 160; e2e forces an API failure and measures wall clock |
| NFR-3 | Cancel leaves no surviving provider process | e2e cancels mid-inspection, then asserts no matching PID in the api container |
| NFR-4 | Inspection never blocks the event loop | integration test issues a second request during an in-flight slow inspection and asserts it is served |
| NFR-5 | The Spotify client secret appears in no API body, log line, or process argv | contract test greps a captured request/response/log/argv corpus for a sentinel secret |

## User stories

- As the household operator, I paste a Spotify link and get complete metadata in
  about a second, so adding music does not feel broken.
- As the operator, if I have not set up credentials the app still works and tells
  me why it is slower.
- As the operator, I can see what inspection is doing and stop it.
- As the operator, fields I never filled in get completed for me, and fields I
  deliberately emptied stay empty.

## Acceptance criteria

- **AC1** With credentials configured and mode `fast`, paste a Spotify track link
  in S4; a candidate with title, artist, album, disc, track number, year, duration
  and cover appears in under 3 seconds.
- **AC2** Remove the credentials and paste the same link; S4 visibly names the
  spotdl fallback, the elapsed timer continues rather than resetting, and a
  candidate still appears.
- **AC3** Start an inspection and press Cancel; the dialog returns to the editable
  URL with the input preserved, and no spotdl process remains in the api container.
- **AC4** Set mode to `thorough`, save, and inspect a Spotify link; the phase names
  spotdl and no Spotify API call is made.
- **AC5** Restart the containers and reopen S12; the saved mode, timeouts, and
  credential-configured state are unchanged, and the secret is not echoed.
- **AC6** Inspect a track whose album is unknown, leave album untouched through
  S5, and complete the download; the finished track shows an album filled by
  Last.fm, and the job's `ENRICHING` phase reports real work.
- **AC7** Inspect the same track, deliberately clear the album field in S5, and
  complete the download; the finished track's album remains empty.
- **AC8** Enter a timeout outside its permitted range in S12; the field is rejected
  with the permitted range stated and nothing is saved.
- **AC9** Paste a Spotify album or playlist URL in any mode; the existing
  single-track rejection appears unchanged.
- **AC10** Save a sentinel Spotify secret, exercise inspection, then read
  `GET /settings`, the container logs, and the spotdl argv; the sentinel appears in
  none of them.

## Validation rules

- Timeouts are integers in seconds: spotify 1–30, spotdl 30–600, ytdlp 10–300.
- Mode is exactly `fast` or `thorough`; any other value is rejected at the API.
- A blank credential on PATCH means unchanged; explicit `clear_secret: true`
  removes it — the existing settings convention, unchanged.
- A Spotify response missing title or artist is treated as a failed lookup and
  triggers fallback rather than being returned partially.

## Error cases

- Credentials absent → fast path unavailable; fallback; stated in S12, not an error.
- Token request 400/401 → typed credential error naming Spotify, and fallback.
- Track request 404 → the track does not exist; no fallback, since spotdl cannot
  find it either. Distinct from a transport failure.
- 429 rate limited → typed error honoring `Retry-After` without a retry storm;
  fallback.
- Both paths fail → typed provider error naming both attempts; input preserved.
- Cancellation → distinct from failure in both UI and taxonomy.

## Edge cases

- Mode or timeout changed while an inspection is in flight: the in-flight request
  keeps the values it started with.
- Credentials cleared while an inspection is in flight: the in-flight request
  finishes with the token it already holds.
- Enrichment finds nothing: the field stays empty and the phase still reports
  honestly rather than claiming a fill.
- Enrichment is unavailable (no Last.fm key): the phase reports that it was
  skipped, not that it succeeded.
- Proxy unconfigured: the Spotify API path uses a direct connection exactly as
  other adapters do; proxy-first fail-closed behavior is unchanged.

## Constraints

Existing stack only. ARCHITECTURE.md is patched, not regenerated. The Spotify Web
API is documented and versioned, so its wire contract ships compact (≤1 page); the
verified-fake rule still applies, and the Spotify adapter runs the same shared
`LinkInspector` protocol suite as the spotdl adapter.

## Out of scope

Bulk/album/playlist import, acquisition-path changes, user-account Spotify auth,
per-request mode override, inspection result caching, fast paths for YouTube or
Deezer, proxy performance.

## Future improvements

Backlog order from SPEC.md: per-request override, cached inspection results, mode
governing acquisition, fast paths for other providers.
