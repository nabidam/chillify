# 004 — Radio Javan discovery and direct acquisition

## 1. Goal & kernel journey

**Core promise:** A household can discover Persian music in a dedicated Radio
Javan experience and download the exact Radio Javan track into Chillify's local
library without an account or a YouTube match.

1. **KJ1** — Open **Radio Javan** from Chillify's persistent sidebar.
2. **KJ2** — Browse the first page of Featured or Trending tracks, or submit a
   title/artist query inside the Radio Javan destination.
3. **KJ3** — Choose one remote track and queue its direct download.
4. **KJ4** — Follow the durable job through download, conversion when needed,
   enrichment, tagging, and organization on the existing Downloads surface.
5. **KJ5** — Play the completed local track through Chillify's persistent player.
6. **KJ6** — Revisit the same Radio Javan result and see the local-library match
   instead of a second Download action.
7. **KJ7** — Disconnect Radio Javan or the configured proxy and confirm that the
   Radio Javan surface fails with a retry while the local library still plays.

## 2. Scope

### In

- [user-stated] Anonymous Radio Javan usage against the contracts exercised by
  the sibling `rjtui` project; no login, cookies, or account mutation.
- [user-stated] A separate top-level Radio Javan destination, separate backend
  routes, and separate frontend feature boundary. Radio Javan results never join
  the MusicBrainz/Apple/Deezer combined search.
- [user-stated] Radio Javan track search plus first-page Featured and Trending
  exploration. Trending replaces the unverified latest-track request in this cycle.
- [user-stated] Direct Radio Javan acquisition; yt-dlp is never invoked for a
  Radio Javan candidate.
- [user-approved] Automatic quality choice in strict order: `hq_link`, then
  `link`, then `lq_link`.
- [kernel-derived] Durable queueing, progress, cancellation, retry, MP3
  conversion/validation, metadata/artwork, publication, local duplicate
  detection, playback, and Radio Javan provenance through Chillify's existing
  pipeline.
- [process-derived] Sanitized fixtures, shared fake/real contracts, migration
  rehearsal, accessibility coverage, composition smoke, and a live canary.

### Out

- Mixing, ranking, or deduplicating Radio Javan remote results with current
  MusicBrainz, Apple, or Deezer remote results.
- Radio Javan authentication, likes, follows, private playlists, or any mutation
  against Radio Javan.
- Videos, podcasts, artists, albums, playlists, bulk import, and submitted Radio
  Javan link inspection.
- yt-dlp fallback when Radio Javan detail or media transfer fails.
- Playing remote Radio Javan media before it is downloaded into the local library.
- A per-download quality picker or provider-specific storage/queue implementation.

### Backlog

- Verify and add the current **Just Released** track contract.
- Paginate Featured and Trending beyond their first pages.
- Artist/album pages, playlist exploration and bulk import, videos, and podcasts.
- Radio Javan URL submission, provider-specific catalog caching, and optional
  quality overrides.
- Authenticated likes, follows, and private playlists, subject to a separate
  authentication and user-data cycle.

## 3. Requirements

- **R1 — Separate destination.** Sidebar navigation exposes **Radio Javan** at
  `/radio-javan`; its active state, history behavior, persistent player, and
  responsive fallback match the shell. Acceptance: the route never requests
  `/api/v1/search/catalog`, and current Search never returns `radiojavan`.
- **R2 — Dedicated search.** Submitting a nonblank query navigates to
  `/radio-javan/search?q={query}` and returns only normalized Radio Javan MP3 rows.
  Acceptance: a fixture containing MP3, video, podcast, artist, and playlist groups
  renders only the MP3 rows and preserves the query across refresh/back navigation.
- **R3 — Featured and Trending.** Explore offers explicit Featured and Trending
  states backed by page 1 of the verified MP3 browse contract. Acceptance: changing
  section changes upstream `type`, keeps search separate, and renders every data state.
- **R4 — Stable candidates.** Every accepted row becomes a non-playable
  `TrackCandidate` with `provider="radiojavan"`, a stable source ID, canonical
  public source URL, normalized title/artist and optional album/year/duration/art,
  a stable acquisition locator, and a digest of accepted fields. Acceptance: one
  malformed row is omitted without hiding valid siblings; a malformed response
  envelope becomes a typed provider error with no response body in the public error.
- **R5 — Server-owned resolution.** A download request stores the stable candidate,
  but the worker re-fetches `/mp3?id={source_id}` immediately before transfer and
  requires the returned ID to match. Acceptance: a stale URL embedded in the search
  fixture is never fetched, while the current URL from the detail fixture is fetched.
- **R6 — Direct quality policy.** Acquisition chooses the first nonblank HTTPS URL
  from `hq_link`, `link`, `lq_link`; it follows only outbound-policy-approved hops,
  reports real byte progress when total size is known, and leaves no partial file
  after cancellation or failure. Fallback applies only when a field is absent or its
  URL is invalid; once selected, transport retry never silently downgrades quality.
  Acceptance: contracts prove every selection, redirect/proxy failure, unknown-size
  progress, retry ceiling, and cleanup.
- **R7 — Local MP3 publication.** The adapter returns exactly one validated MP3,
  reusing a media conversion helper for non-MP3 audio; the worker retains tagging,
  artwork, organization, recovery, and atomic publication. Acceptance: AAC/M4A
  becomes MP3, native MP3 is not transcoded, both play locally, and durable phase
  events report conversion only while conversion actually runs.
- **R8 — Identity and provenance.** Remote catalogs stay disjoint, while the
  universal local-library duplicate rules still apply by Radio Javan source ID and
  normalized track identity. Acceptance: an existing local match renders **Already
  in your library**, and a completed new track has one `track_sources` row with
  provider `radiojavan` and its canonical public source URL.
- **R9 — Durable behavior.** Radio Javan jobs use the existing job state machine,
  idempotency, reconciliation, retry, cancellation, SSE, and global Downloads UI.
  Acceptance: double queueing produces one job, restart resumes it once, and cancel
  removes its workspace.
- **R10 — Failure isolation.** Radio Javan search, browse, detail, or media failure
  never changes application readiness or hides local content. Acceptance: with the
  Radio Javan fixture failing, Library search/playback succeeds and Radio Javan shows
  a scoped error with Retry.
- **R11 — Accessible content UI.** Remote artwork has reserved geometry and useful
  alternative text, all Download/Retry/section controls are keyboard reachable with
  visible focus, status is conveyed by text as well as color, and reduced motion
  removes translation/scale. Acceptance: component tests cover focus order and
  states; the Radio Javan browser journey has no serious axe finding.
- **R12 — Verified external seam.** Production and fixture adapters satisfy one
  contract suite; ordinary verification makes no live request. Acceptance: fixtures
  cover success, empty, malformed, timeout/proxy, missing URL, cancellation, and
  no-progress; only the canary performs the live Featured probe.
- **R13 — Bounded external content.** Provider JSON and media transfers cannot fill
  memory or disk without bound. Acceptance: JSON over 4 MiB is rejected; declared or
  actual audio over 256 MiB is stopped and cleaned up; acquisition refuses before
  transfer when the workspace filesystem has less than 512 MiB free.

## 4. Active risk modules

### External system

Radio Javan is an anonymous, reverse-engineered runtime dependency. Its accepted
wire contract is deliberately narrower than the broader `rjtui` reference:

- Base URL: `https://rj-deskcloud.com/api2` through Chillify's saved proxy and
  shared outbound HTTP policy. Requests send JSON Accept and a descriptive
  Chillify User-Agent; they send no cookie or authentication header.
- Search: `GET /search?query={1..200 chars}`. The response must be an object and
  `mp3s`, when present, must be an array. Other groups are ignored. A missing
  `mp3s` is treated as an empty result only when the envelope otherwise parses.
- Explore: `GET /mp3s?url=mp3s&type={featured|trending}&page=1`. The response must
  be an array.
- Detail: `GET /mp3?id={source_id}`. The response must be an object whose positive
  string/integer ID equals the requested ID and which contains at least one usable
  URL under `hq_link`, `link`, or `lq_link`.
- Accepted row fields: required positive `id`, `artist`, and title from
  `title|name|song`;
  optional album string/object, `date|created_at`, duration seconds, artwork from
  `photo|thumbnail|photo_thumbnail`, `permlink`, and `share_link`. Unknown fields
  are ignored. Title cleanup removes an exact artist prefix and balanced quotes as
  already exercised by `rjtui`. Search/Featured/Trending contract fixtures and the
  canary must prove scoped MP3 rows carry IDs; rows without one are non-downloadable
  and omitted rather than guessing a detail identifier from `permlink`/`hash`.
- Canonical source URL: an HTTPS `share_link` on `rj.app`, `radiojavan.com`, or a
  subdomain thereof; otherwise `https://play.radiojavan.com/song/{source_id}`. The
  acquisition locator is the stable source ID, never a CDN URL.
- Errors: transport/proxy failures keep their existing typed semantics. HTTP error,
  rejected API payload, invalid JSON, invalid envelope, ID mismatch, or missing
  media URL becomes a safe typed provider error. Bodies, CDN URLs, proxy material,
  and absolute paths never cross the API or logs.
- Transfer: media URLs and redirects must be HTTPS and pass the DNS/IP SSRF policy.
  A new bounded streaming operation on `OutboundHttp` owns per-hop validation, typed
  proxy errors, byte counting, cancellation, and the no-direct-fallback rule; callers
  may not use `open().stream()` directly. It keeps existing timeout/retry budgets,
  resumes only with proven byte-range support, and otherwise restarts from zero.
- Resource budgets: JSON bodies are capped at 4 MiB from declared and actual bytes.
  Audio is capped at 256 MiB from declared and actual bytes; transfer starts only
  with at least 512 MiB free on the workspace filesystem. Exceeding a limit closes
  the response, removes the partial, and raises a typed non-retryable acquisition
  failure.
- Fake/real verification: sanitized search, Featured, Trending, detail, audio, and
  artwork fixtures feed the same wire parsers and capability contract suite as the
  production adapter. The fixture acquisition adapter never imports production
  networking. Production binding and exact URL/parameter construction are
  assertable offline; live success is canary-only.

Failure behavior is scoped: one malformed row is skipped; an invalid envelope fails
that request; detail/transfer failure fails that durable job; no case falls back to
yt-dlp or marks the whole application unready.

### Migration

One Alembic revision widens existing SQLite checks without discarding rows:

- `track_sources.provider` adds `radiojavan`.
- `download_jobs.provider` adds `radiojavan`.
- `download_jobs.source_type` adds `radiojavan_track`.

The migration rebuilds constrained tables with all columns, foreign keys, and indexes
without firing `job_events` cascades or losing `download_jobs.parent_job_id` /
`result_track_id` relationships. Verification snapshots and compares `download_jobs`
and `job_events`, verifies every job index and parent/result foreign key, and runs
`PRAGMA foreign_key_check` after each up → down → up stage over every legacy value.
Downgrade first refuses while Radio Javan sources/jobs exist; after fixture removal it
restores the prior checks with all legacy history intact.

### UI-heavy

The dedicated destination follows the root `DESIGN.md` tokens and shell rather than
introducing a second brand theme.

- **Explore `/radio-javan`:** labeled search first, Featured/Trending Tabs second,
  and an artwork-led grid/list beneath. It has fixed-geometry loading, empty,
  populated, and scoped Retry states.
- **Search `/radio-javan/search?q=`:** visible query field and result count, Radio
  Javan-only results, no-results guidance, loading skeleton, and scoped retry. The
  URL owns the submitted query; browser Back returns to the prior Explore state.
- **Remote track:** artwork, identity, optional metadata, provenance, and exactly one
  primary action: Download or the local-library link. Queueing disables only that
  track and announces success without moving focus; remote Play does not exist.
- Below the desktop breakpoint the existing sidebar Sheet remains the navigation
  fallback; media cards become a single readable column, controls remain at least
  the existing large-control height, and no horizontal content scroll is introduced.

### Deployment

The unchanged production Compose entry point binds real Radio Javan adapters in
production/release and fixture adapters only in gate mode. The composition smoke boots
migrations, API, worker, web, Redis seam, real adapter binding, and existing media
roots. A canary-only anonymous Featured request proves live reachability in a
disposable release environment; failure is explicit and never replaced by fixtures.

## 5. Stack & dependencies

The committed stack remains React 19, React Router, TanStack Query, Tailwind v4,
Shadcn/Radix, FastAPI, SQLAlchemy/Alembic, Celery, HTTPX, Tenacity, FFmpeg, Mutagen,
and Pillow. No new runtime dependency is planned: HTTPX can stream the provider media,
the existing media layer owns conversion/tagging, and existing UI primitives cover
Tabs, Card/AspectRatio, Button, Badge, Alert, Empty, Skeleton, and Tooltip.

Before implementation, inspect Shadcn Tabs, AspectRatio, and Card and reuse installed
primitives. Fixtures are test data. `rjtui` is contract provenance, not a dependency.

## 6. Units

### U1 — Walking skeleton

- **Outcome:** From the real Chillify shell, one fixture-backed Radio Javan search
  result with native MP3 media can be queued through the new provider/source types,
  directly acquired, published, and played locally.
- **Deps:** none.
- **Proposed files:** migration, jobs/protocols, registry, minimal adapter/parser and
  fixture, API route/schema, router/sidebar/page, backend integration and browser e2e.
- **Criteria:** R1, R2, R4, R5, R9; KJ1–KJ5 pass through the production entry point
  with injected external fixtures and the real application composition. Conversion,
  fallback, and local-match depth belong to U3/U4.
- **Interfaces:** produces provider `radiojavan`, job provider `radiojavan`, source type
  `radiojavan_track`, `GET /api/v1/radio-javan/search?q&limit`, and the existing
  `POST /api/v1/downloads` accepting that source type.

### U2 — Featured and Trending exploration

- **Outcome:** The dedicated Explore route switches between first-page Featured and
  Trending Radio Javan tracks without contacting current catalog search.
- **Deps:** U1.
- **Proposed files:** provider/application/API explore path, query/page components,
  fixtures and component/contract tests.
- **Criteria:** R3, R4, R10, R11; KJ2 and KJ7 pass.
- **Interfaces:** produces
  `GET /api/v1/radio-javan/tracks?section={featured|trending}` in the standard page
  envelope with `next_cursor=null` because this cycle deliberately serves page 1 only.

### U3 — Hardened direct transfer

- **Outcome:** Direct media acquisition obeys quality fallback, proxy/SSRF policy,
  resource limits, bounded retry/resume, truthful progress/phases, cancellation, MP3
  conversion, and workspace cleanup.
- **Deps:** U1.
- **Proposed files:** shared outbound streaming and media-conversion seams, acquisition
  adapter, media fixtures, contract/unit tests.
- **Criteria:** R5–R7, R9, R12, R13.
- **Interfaces:** consumes U1's `radiojavan` acquisition capability and the External
  system wire contract; produces a revised acquisition callback that reports
  `downloading` and `converting` only while those stages run. DownloadService maps the
  callbacks to durable phases instead of emitting an unconditional post-acquire phase.

### U4 — Search and result-state depth

- **Outcome:** Deep-linked Radio Javan search handles all content states and local
  duplicate actions without merging with the current provider workflow.
- **Deps:** U1, U3.
- **Proposed files:** frontend queries/results, API integration and component tests.
- **Criteria:** R1, R2, R8, R10, R11; KJ6 passes, query survives refresh/back, and only
  the selected result disables while queueing.

### U5 — Provenance and migration assurance

- **Outcome:** Existing databases upgrade safely and completed Radio Javan tracks/jobs
  retain their distinct provider identities.
- **Deps:** U1.
- **Proposed files:** migration, repository/duplicate, and source/detail API tests.
- **Criteria:** R8, R9 and every Migration obligation passes.

### U6 — Verified adapters and failure isolation

- **Outcome:** Production and fixture families share behavioral contracts, and every
  documented provider failure stays scoped to its request/job.
- **Deps:** U2, U3.
- **Proposed files:** sanitized fixtures, shared contracts, proxy/error/readiness tests.
- **Criteria:** R4–R6, R10, R12, R13 and every External system failure case passes
  offline, including streaming redirect validation and no proxy bypass.

### U7 — Responsive and accessible design finish

- **Outcome:** Explore and Search achieve the approved artwork-led composition across
  desktop and fallback widths without weakening the existing shell or accessibility.
- **Deps:** U2, U4.
- **Proposed files:** UI compositions and component/a11y/e2e tests; tokens only if an
  existing role is insufficient.
- **Criteria:** R1–R3, R8, R10, R11; 375, 768, 1024, and 1440 pixel viewport captures
  have no horizontal overflow or layout-shift regression.

### U8 — Production composition and release proof

- **Outcome:** Gate proves fixture-backed KJ1–KJ7; release proves real adapter binding
  offline; a live canary reaches Featured through Chillify's real API path.
- **Deps:** U5, U6, U7.
- **Proposed files:** gate scenario, Playwright journey, canary/status assertions,
  README/operator notes.
- **Criteria:** R9–R13; fixture-backed KJ1–KJ7 pass in gate, mocked-HTTP contracts drive
  the real adapters, release binding is offline-assertable, and the in-app Featured
  canary succeeds or fails explicitly with no fallback. Live media download is not a
  release canary because it would acquire third-party content.

## 7. Verification contract

- Canonical command: `./scripts/verify.sh`.
- Kernel e2e: `frontend/tests/e2e/radio-javan.spec.ts`, run against the unchanged
  production Compose entry point with the gate fixture boundary injected.
- Migration rehearsal: focused test performs up → down → up with legacy and Radio
  Javan fixtures, snapshots jobs/events/relationships/indexes, runs foreign-key checks,
  and asserts refusal plus survival rules.
- Provider contracts: focused backend contract suite uses no live network and runs the
  same discovery/acquisition assertions against production adapters with mocked HTTP
  and fixture adapters with recorded payloads.
- Release canary: production composition proves real adapter types offline; explicit
  live-success calls Chillify's Featured API, which invokes the real adapter.
- Definition of done: every requirement maps to passing evidence; KJ1–KJ7 run in gate
  through the shipped composition; no serious axe result, migration loss, partial file,
  provider-body/URL leak, direct-network proxy bypass, or yt-dlp invocation occurs;
  the user completes the walkthrough below.

## 8. Walkthrough script

1. Open Radio Javan from the sidebar; switch Featured → Trending → Featured and
   confirm each keeps its own visible content state.
2. Search for a fixture artist/title, refresh the deep link, navigate Back, and confirm
   query and Explore state remain coherent.
3. Queue the HQ fixture result, watch truthful progress on Downloads, wait for direct
   completion, and play the local MP3.
4. Queue native-only and LQ-only fixtures and confirm the fallback order; confirm the
   AAC/M4A fixture is published as a valid MP3 with a truthful converting phase.
5. Revisit the acquired result and follow **Already in your library** instead of
   creating a duplicate job.
6. Start a slow direct transfer, cancel it, and confirm no workspace/final partial file
   remains; retry it and confirm one new linked durable job completes.
7. Break Radio Javan and then the proxy. Confirm scoped Retry states, safe messages,
   unchanged readiness, usable current Search, and uninterrupted local playback.
8. Exercise oversized JSON/audio and low-disk fixtures; confirm bounded failures and
   complete partial-file cleanup.
9. Restart the production composition during a queued/running fixture acquisition and
   confirm reconciliation completes it once with Radio Javan provenance.
10. Run the production canary in live-success mode and confirm Chillify's Featured API
    uses the real adapter and never falls back to fixtures or yt-dlp.
