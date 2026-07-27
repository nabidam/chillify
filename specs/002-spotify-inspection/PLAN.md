---
status: gate-passed
---

# PLAN — 002 Fast, legible Spotify link inspection

Delta cycle off `specs/001-core`. Root `CONVENTIONS.md`, `DESIGN.md` and
`ARCHITECTURE.md` are living documents patched by this cycle, never regenerated.
ARCHITECTURE §17 is the contract every chunk below implements.

No `SPIKE:` markers exist in ARCHITECTURE §17 — the official Spotify Web API is
documented and its latency was measured live — so there is no spike chunk.

Gate cadence: one mid demo gate after C3 and the release gate at the end, across
~11 feature tasks. Both launch the production entry point with disposable config;
there is no gate-only composition.

---

## C1 — WALKING SKELETON: Spotify credentials and the fast inspection path

The thinnest end-to-end slice that makes the front of the kernel journey real:
configure credentials, paste a Spotify link, get a complete candidate in about a
second, download it, hear it play. Inspection stays synchronous here — phases and
cancel arrive in C2/C3. Ugly is fine; fake is not.

**Files touched**
- `backend/alembic/versions/0002_settings_keys.py` (new)
- `backend/src/chillify/config.py`, `application/settings.py`
- `backend/src/chillify/api/{schemas,routes}/settings.py`
- `backend/src/chillify/infrastructure/providers/spotify_api.py` (new)
- `backend/src/chillify/infrastructure/providers/registry.py`
- `backend/src/chillify/application/inspection.py` (new)
- `backend/tests/contract/test_spotify_api_contract.py` (new)
- `backend/tests/integration/test_inspection_fallback.py` (new)
- `backend/tests/fixtures/spotify_api/*.json` (new)

**Requirements**
- Migration rebuilds `settings` to widen the `key` CHECK with `'inspection'` and
  `'provider.spotify_api'`, seeds both rows (§17.4). **Rollback deletes both rows
  before narrowing the CHECK**, or the copy violates the old constraint.
- `SpotifyApiInspector` implements the existing `LinkInspector` protocol over the
  shared `OutboundHttp` client. Client Credentials token cached until 60s before
  expiry; 401 invalidates and retries once. Response body capped at 1 MiB.
- Field mapping and error semantics exactly per §17.3, including 404 = no
  fallback and 429 = honor `Retry-After` without a retry storm.
- `artwork_url` re-enters the existing `ArtworkFetcher` pipeline; never fetched
  directly here.
- `InspectionPolicy` orders paths by mode and falls back to spotdl on credential
  absence, credential failure, transport failure, or a candidate missing title or
  artist.
- Credentials stored Fernet-encrypted; `GET /settings` returns `configured` only.

**Acceptance**
- With credentials set, `POST /links/inspect` on a Spotify track returns a
  candidate including album, disc, track number and ISRC in under 3s. `[integration]`
- With credentials cleared, the same call returns a candidate via spotdl. `[integration]`
- The shared `LinkInspector` protocol suite passes against the Spotify adapter and
  the fixture adapter alike. `[contract]`
- Migration up → down → up against fixture data leaves pre-existing settings rows
  intact, and down succeeds with the seeded rows present. `[integration]`
- A sentinel secret appears in no `GET /settings` body. `[contract]`

**Do NOT** touch the S4/S5 frontend, the inspections table, cancellation,
`edited_fields`, or enrichment. Do not change `POST /links/inspect`'s response
shape yet.

---

## C2 — Inspection as a tracked, cancellable operation (backend)

**Files touched**
- `backend/alembic/versions/0003_inspections.py` (new)
- `backend/src/chillify/infrastructure/db/{models,repositories}.py`
- `backend/src/chillify/application/inspection.py`
- `backend/src/chillify/api/{schemas,routes}/links.py`
- `backend/src/chillify/infrastructure/providers/spotdl.py` (cancel predicate only)
- `backend/tests/integration/test_inspection_lifecycle.py` (new)

**Requirements**
- `inspections` table exactly per §17.4, with `ix_inspections_expiry` and
  opportunistic cleanup on write, mirroring `artwork_stages`.
- `POST /links/inspect` → `202 {inspection_id, phase, started_at}`.
  `GET /links/inspect/{id}/events` → SSE with the job-event envelope and a
  15-second heartbeat; terminal `expired` event on TTL, never silent abandonment.
  `DELETE /links/inspect/{id}` → `204`.
- Cancellation per §17.2: the trigger is `cancel_requested_at` **on the
  inspection row**, polled by the adapter's existing `cancelled` predicate. The
  job-lease trigger is not reused and must not be referenced.
- Inspection runs in a thread executor so the event loop stays responsive.
- Closed phase vocabulary; no percentage field anywhere.
- Timeouts read per-path from settings at inspection start; an in-flight
  inspection keeps the values it started with.

**Acceptance**
- Inspect → stream shows `reading_spotify` then `done` with monotonic
  `elapsed_ms`. `[integration]`
- `DELETE` mid-inspection yields a terminal `cancelled` event, and no spotdl
  process survives. `[integration]`
- A second request is served while a slow inspection is in flight (NFR-4). `[integration]`
- An expired id returns `404`; a stream open at expiry receives `expired` and
  closes. `[integration]`
- Migration up → down → up preserves fixture data. `[integration]`

**Do NOT** build any frontend, `edited_fields`, or enrichment.

---

## C3 — S4 and S12 surfaces

**Files touched**
- `frontend/src/features/acquisition/AddLinkDialog.tsx`
- `frontend/src/features/acquisition/useInspection.ts` (new)
- `frontend/src/features/settings/{SettingsPage,InspectionSettingsCard}.tsx`
- `frontend/src/api/generated.ts` (regenerated, never hand-edited)
- `frontend/tests/component/inspection-feedback.test.tsx` (new)

**Requirements**
- S4 per UX.md: named phase, elapsed seconds, Cancel at every phase, fallback
  named visibly with the timer continuing rather than resetting, input preserved
  on cancel and error. No percentage.
- S4 renders the expired-inspection state distinctly from a generic failure.
- S12 per UX.md: Spotify credentials block (masked, blank-means-unchanged,
  `clear_secret`), mode Fast/Thorough with its one-line trade, three timeouts with
  units, defaults and permitted ranges surfaced on rejection.
- Tokens only; all interactive states per DESIGN.md; axe clean.

**Acceptance**
- Paste a Spotify link: phase text and a rising elapsed counter appear, Cancel is
  enabled. `[integration]`
- Forced fallback: the phase names spotdl and the elapsed value does not reset. `[integration]`
- Cancel restores the editable URL with input intact. `[integration]`
- Out-of-range timeout is rejected at the field, stating the range; nothing saves. `[integration]`
- Zero critical/serious axe violations on S4 and S12. `[e2e@gate-5]`

**Do NOT** implement `edited_fields` or enrichment.

---

## DEMO GATE 5 — inspect fast, fall back, cancel, persist

Numbering continues the parent cycle's gates 1–4.

**Launch (production entry point, disposable config):**
```
./scripts/gate/prepare.sh insp release
docker compose --env-file .gate/insp/.env up --build -d
./scripts/gate/seed.sh insp kernel-500
```
**Seed/fixture data:** the base track set, plus Spotify credentials set through
S12 during the walk (step 1 is the configuration step — do not pre-seed them).

**Journey to walk, and what must be observed**
1. S12: paste Spotify credentials, save → shows configured, secret not echoed. *(C1)*
2. S4: paste a Spotify track link → named phase and rising elapsed. *(C2, C3)*
3. Candidate returns in ~1s **with album, disc and track number**. *(C1)*
4. Download it and play it. *(001-core)*
5. S12: clear credentials. S4: paste a link → phase names the spotdl fallback and
   the elapsed timer continues. *(C1, C3)*
6. S4: start an inspection, press Cancel → stops, input preserved, no spotdl
   process left in the api container. *(C2, C3)*
7. Restart the containers → mode, timeouts and credential state persist. *(C1)*

**Runnability precondition:** `prepare.sh` writes only under `.gate/insp/` and
fails closed against non-disposable targets. Credentials entered here are the
operator's own and live only in the disposable tree.

---

## C4 — `edited_fields` threaded end to end

Without this, D2 is unimplementable and AC6/AC7 cannot both pass.

**Files touched**
- `frontend/src/features/acquisition/YouTubeReviewDialog.tsx`
- `backend/src/chillify/api/schemas/downloads.py`
- `backend/src/chillify/application/downloads.py`
- `backend/tests/integration/test_edited_fields.py` (new)

**Requirements**
- S5 tracks dirty fields and submits an explicit `edited_fields` set.
- `DownloadRequest` carries `edited_fields: list[str]`; it is persisted into
  `request_json` so the worker still sees it after a restart.
- Per §17.5 `TrackCandidate` stays `str | None` — touched-ness belongs to the
  review, not the domain value object.
- S5 marks never-populated fields as not-yet-known, distinct from blank.

**Acceptance**
- Submit with album untouched → `request_json` omits `album` from
  `edited_fields`. `[integration]`
- Deliberately clear album → `request_json` includes `album` in
  `edited_fields`. `[integration]`
- A job restarted mid-flight still sees the original `edited_fields`. `[integration]`

**Do NOT** call the enricher yet.

---

## C5 — Last.fm gap enrichment call site

`downloads.py` records `ENRICHING` and does nothing today. This makes the phase
honest.

**Files touched**
- `backend/src/chillify/application/downloads.py`
- `backend/src/chillify/infrastructure/providers/registry.py`
- `backend/tests/integration/test_enrichment.py` (new)

**Requirements**
- The worker calls `MetadataEnricher.enrich(candidate, missing_fields, proxy)`
  where `missing_fields` = empty **and** absent from `edited_fields`.
- Best-effort: failure, missing key, or no match leaves fields empty, records the
  honest phase outcome, and never fails the job.
- Gap-fill only: never overwrite a populated or edited field. §7 ordering unchanged.

**Acceptance**
- Untouched empty album → filled by the enricher; phase reports a real fill. `[integration]`
- Deliberately cleared album → stays empty. `[integration]`
- No Last.fm key → phase reports skipped, not succeeded; job completes. `[integration]`
- Enricher failure → job completes, fields unchanged. `[integration]`

**Do NOT** change the ordering rule or let the enricher touch edited fields.

---

## C6 — Production-composition proof, NFR measurements, stopgap revert

**Files touched**
- `scripts/verify/nfr.sh`
- `scripts/production_canary.sh`
- `backend/src/chillify/infrastructure/providers/spotdl.py` (timeout constant)
- `deploy/nginx.conf`
- `backend/tests/integration/test_production_composition.py`
- `frontend/tests/e2e/inspection.spec.ts` (new)

**Requirements**
- Revert `8dcda66`'s 180s inspect and 200s nginx stopgaps to the configured
  defaults (§17.7); timeouts now come from settings.
- The production composition resolves the real `SpotifyApiInspector` — asserted
  directly, as the parent cycle asserts its other real adapters.
- NFR-1 p95, NFR-2 worst-case sum, NFR-3 no surviving process, NFR-4
  non-blocking, NFR-5 sentinel-secret grep all get their named measurement in
  `nfr.sh` or a contract test.
- **The canary's live probe must run inside the api container**, not on the host:
  the parent cycle's host-side probe inherited the host's `http_proxy` and
  reported reachability while the containers had none. This cycle's canary claims
  would be worthless repeating that mistake.

**Acceptance**
- `./scripts/verify.sh` green from a clean checkout. `[contract]`
- Canary reports the real Spotify adapter and fails closed when the **container**
  cannot reach Spotify. `[contract]`
- Each NFR emits its named measurement. `[e2e@gate-6]`

**Do NOT** add features here.

---

## RELEASE GATE 6 — the cycle's exit bar

**Launch (production entry point, release composition):**
```
./scripts/gate/prepare.sh release release
docker compose --env-file .gate/release/.env up --build -d
./scripts/gate/seed.sh release kernel-500
```
**Preflight (run before inviting the walk):** `./scripts/production_canary.sh
--env-file .gate/release/.env --no-live-success` must PASS with the real
`SpotifyApiInspector` reported, and its live probe must run inside the container.

**Journey — the full kernel journey of SPEC.md, each step served by a chunk**
1. Configure Spotify credentials in S12. *(C1)*
2. Paste a Spotify track link; see named phase and elapsed. *(C2, C3)*
3. Candidate returns in ~1s with album, disc and track number. *(C1)*
4. Review and download it; hear it play. *(001-core, C4)*
5. Clear credentials; the phase names the spotdl fallback, timer continuing. *(C1, C3)*
6. Cancel mid-inspection; no spotdl process survives. *(C2, C3)*
7. Add a track with unknown album, leave it untouched, download → Last.fm fills
   it and `ENRICHING` reports real work. *(C4, C5)*
8. Restart the containers; credentials, mode and timeouts persist. *(C1)*
9. Named NFR evidence, Chromium/Firefox smoke, zero critical/serious axe. *(C6)*

**Crystallization:** encode the walked journey as `frontend/tests/e2e/gate-6-release.spec.ts`
joining the journey suite, in the same session as the walk.

---

## Parent-cycle dependency

`specs/001-core` Gate 4 stays BLOCKED until this cycle completes; its preflight
re-runs afterwards. The parent's outstanding canary-namespace defect is carried
here as part of C6 rather than left in the parent's queue, because this cycle's
own release gate depends on the canary telling the truth.
