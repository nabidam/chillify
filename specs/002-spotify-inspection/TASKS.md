---
status: ready
---

# TASKS — 002 Fast, legible Spotify link inspection

Delta cycle off `specs/001-core`. **No Task 0**: the repo, verify script, CI,
linters, migrations harness and test harnesses all exist from cycle 001 and are
reused unchanged. Task ids continue from the parent, which ends at Task 20; gate
numbering continues the parent's gates 1–4.

Done-marks reference `specs/002-spotify-inspection/evidence/task-N.txt` per the
Verification Machinery rules.

**Downgrade valve:** 7 feature tasks (21, 22, 23, 24, 25, 27, 28) — under the ~15
threshold, but SPEC.md's `profile: full` rests on the *two subsystems* criterion
(Spotify inspection plus the Last.fm enrichment path), which still fails. Retro-lite
is therefore not offered; the profile stands.

---

## Task 21 — Settings migration, Spotify credentials, inspection settings

```toml
id = 21
type = "feature"
chunk = "C1"
deps = []
skeleton = true
files = [
  "backend/alembic/versions/0002_settings_keys.py",
  "backend/src/chillify/config.py",
  "backend/src/chillify/application/settings.py",
  "backend/src/chillify/api/schemas/settings.py",
  "backend/src/chillify/api/routes/settings.py",
  "backend/tests/integration/test_settings_inspection.py",
]
produces = """
PATCH /settings/inspection  {mode, timeout_spotify_s, timeout_spotdl_s, timeout_ytdlp_s, revision}
PATCH /settings/providers/spotify_api  {client_id, client_secret, clear_secret, revision}
GET /settings -> gains `inspection` block and masked `spotify_api` block
SettingsService.current_inspection() -> InspectionSettings(mode, timeout_spotify_s, timeout_spotdl_s, timeout_ytdlp_s)
SettingsService.current_spotify_credentials() -> tuple[str, str] | None
"""
[[criteria]]
text = "Saving mode and the three timeouts, then reading GET /settings, returns exactly what was saved; a stale revision is refused with the existing record_changed error."
layer = "integration"
[[criteria]]
text = "A timeout outside its range (spotify 1-30, spotdl 30-600, ytdlp 10-300) is refused and nothing is persisted."
layer = "integration"
[[criteria]]
text = "A saved sentinel client secret is absent from every GET /settings body; blank-on-PATCH leaves it unchanged and clear_secret removes it."
layer = "integration"
[[criteria]]
text = "Migration up, down, then up again against fixture data leaves pre-existing settings rows byte-identical, and the down step succeeds with both seeded rows present."
layer = "integration"
[[criteria]]
text = "The produced endpoints and SettingsService signatures are called exactly as quoted and their shapes asserted."
layer = "contract"
```

**Interfaces — CONSUMES:** existing `settings` table and Fernet secret machinery
(ARCHITECTURE §12, §762); existing optimistic-revision and
blank-means-unchanged/`clear_secret` conventions.

**Why the rollback matters:** the `key` CHECK enumerates permitted keys and SQLite
cannot alter a CHECK in place, so the migration rebuilds the table. **The down step
must delete the two seeded rows before narrowing the enumeration**, or its own copy
violates the old constraint. This repo has one prior migration and no table-rebuild
precedent.

**Context pack (hint):** ARCHITECTURE §12, §17.4, §17.8; `application/settings.py`,
`api/schemas/settings.py`, `api/routes/settings.py`, `alembic/versions/0001_core.py`.
Backend only — no DESIGN.md, no UX.md.

- **Done:** `e9299ca` — evidence `specs/002-spotify-inspection/evidence/task-21.txt`

---

## Task 22 — Spotify Web API inspector, fixtures, and the fallback policy

```toml
id = 22
type = "feature"
chunk = "C1"
deps = [21]
skeleton = true
fake_of = "Spotify Web API"
files = [
  "backend/src/chillify/infrastructure/providers/spotify_api.py",
  "backend/src/chillify/infrastructure/providers/registry.py",
  "backend/src/chillify/application/inspection.py",
  "backend/tests/contract/test_spotify_api_contract.py",
  "backend/tests/integration/test_inspection_fallback.py",
  "backend/tests/fixtures/spotify_api/track_success.json",
  "backend/tests/fixtures/spotify_api/track_missing_optional.json",
  "backend/tests/fixtures/spotify_api/token_401.json",
  "backend/tests/fixtures/spotify_api/track_404.json",
  "backend/tests/fixtures/spotify_api/track_429.json",
]
consumes = """
SettingsService.current_inspection() -> InspectionSettings
SettingsService.current_spotify_credentials() -> tuple[str, str] | None
LinkInspector.inspect(url, proxy) -> TrackCandidate   # ARCHITECTURE line 187
"""
produces = """
SpotifyApiInspector(LinkInspector)  # inspect(url, proxy) -> TrackCandidate
InspectionPolicy.inspect(url, mode, settings) -> TrackCandidate   # ordering + fallback
"""
[[criteria]]
text = "With credentials set, inspecting a Spotify track URL returns a candidate carrying title, artist, album, disc number, track number, ISRC, duration, release year and artwork URL."
layer = "integration"
[[criteria]]
text = "With credentials absent, credentials rejected (401), or the request timing out, the same call returns a candidate produced by spotdl instead, and records which path served it."
layer = "integration"
[[criteria]]
text = "A 404 does not fall back; a 429 honours Retry-After without a retry storm; a response missing title or artist is treated as a failed lookup rather than returned partially."
layer = "integration"
[[criteria]]
text = "One shared LinkInspector protocol suite runs against both the recorded-fixture Spotify adapter and the real adapter's offline request-shape assertions, asserting the ARCHITECTURE section 17.3 wire contract; the fixture adapter rejects exactly what the contract rejects."
layer = "contract"
[[criteria]]
text = "The response body is refused above 1 MiB before parsing, and artwork URLs are handed to the existing ArtworkFetcher rather than fetched here."
layer = "contract"
```

**Interfaces — PRODUCES** as quoted above; the `[contract]` criteria cover both the
protocol suite and the produced signatures.

**Verified-fake rule:** this task produces the Spotify fake. Live Spotify calls
happen only in Task 29's canary through the production composition — never here.

**Context pack (hint):** ARCHITECTURE §6, §17.3, §17.7, protocol line 187;
`infrastructure/security/outbound.py`, `providers/{deezer,spotdl,registry}.py`,
`domain/protocols.py`. Backend only.

- **Done:** `795e29f` — evidence `specs/002-spotify-inspection/evidence/task-22.txt`

---

## Task 23 — Inspection as a tracked, cancellable operation

```toml
id = 23
type = "feature"
chunk = "C2"
deps = [22]
skeleton = true
files = [
  "backend/alembic/versions/0003_inspections.py",
  "backend/src/chillify/infrastructure/db/models.py",
  "backend/src/chillify/infrastructure/db/repositories.py",
  "backend/src/chillify/application/inspection.py",
  "backend/src/chillify/api/schemas/links.py",
  "backend/src/chillify/api/routes/links.py",
  "backend/src/chillify/infrastructure/providers/spotdl.py",
  "backend/tests/integration/test_inspection_lifecycle.py",
]
consumes = """
InspectionPolicy.inspect(url, mode, settings) -> TrackCandidate
"""
produces = """
POST   /links/inspect            -> 202 {inspection_id, phase, started_at}
GET    /links/inspect/{id}/events -> SSE {phase, elapsed_ms, provider, terminal, result?, error?}
DELETE /links/inspect/{id}       -> 204
phases: reading_spotify | matching_spotdl | inspecting_youtube | cancelled | expired | failed | done
"""
[[criteria]]
text = "Submitting a Spotify link returns 202 with an id, and its event stream shows reading_spotify then done with monotonically increasing elapsed_ms and a result."
layer = "integration"
[[criteria]]
text = "DELETE mid-inspection produces a terminal cancelled event distinct from failure, and no spotdl process survives in the container."
layer = "integration"
[[criteria]]
text = "A second API request is served while a slow inspection is in flight, proving inspection does not block the event loop."
layer = "integration"
[[criteria]]
text = "An unknown or expired id returns 404, and a stream open when the TTL fires receives a terminal expired event and closes rather than being abandoned."
layer = "integration"
[[criteria]]
text = "Migration up, down, then up again against fixture data preserves pre-existing rows."
layer = "integration"
[[criteria]]
text = "The three produced endpoints are called exactly as quoted and their shapes and status codes asserted, including the SSE envelope and the closed phase vocabulary."
layer = "contract"
```

**Cancellation is new machinery, not reuse.** Section 7's trigger reads
`cancel_requested_at` from a `download_jobs` row under a Celery lease; an inspection
has neither. Only the `os.killpg` primitive transfers. The trigger here is
`cancel_requested_at` **on the inspection row**, polled by the adapter's existing
`cancelled` predicate (ARCHITECTURE §17.2).

**Context pack (hint):** ARCHITECTURE §17.1, §17.2, §17.4, §17.8, and §5 for the
job-event SSE envelope and heartbeat; `api/routes/links.py`, `db/{models,repositories}.py`,
`providers/spotdl.py`, `infrastructure/queue/cancellation.py`. Backend only.

- **Done:** `2ce9adf` — evidence `specs/002-spotify-inspection/evidence/task-23.txt`
  The migration lives at the repository's actual Alembic path,
  `backend/migrations/versions/0003_inspections.py`, rather than the predicted
  `backend/alembic/versions` path. The existing synchronous link-inspection
  tests were updated for the new 202/SSE contract; lifecycle coverage is in
  `backend/tests/integration/test_inspection_lifecycle.py`.

---

## Task 24 — S4 Add Music: phases, elapsed, cancel, fallback

```toml
id = 24
type = "feature"
chunk = "C3"
deps = [23]
skeleton = true
files = [
  "frontend/src/features/acquisition/AddLinkDialog.tsx",
  "frontend/src/features/acquisition/useInspection.ts",
  "frontend/src/api/generated.ts",
  "frontend/tests/component/inspection-feedback.test.tsx",
]
consumes = """
POST   /links/inspect            -> 202 {inspection_id, phase, started_at}
GET    /links/inspect/{id}/events -> SSE {phase, elapsed_ms, provider, terminal, result?, error?}
DELETE /links/inspect/{id}       -> 204
"""
[[criteria]]
text = "Pasting a Spotify link shows named phase text and a rising elapsed counter, with Cancel enabled throughout and no percentage anywhere."
layer = "integration"
[[criteria]]
text = "When the stream reports the spotdl fallback, the phase text names the switch and the elapsed value continues rather than resetting."
layer = "integration"
[[criteria]]
text = "Cancel returns the dialog to the editable URL with the typed input preserved."
layer = "integration"
[[criteria]]
text = "An expired inspection renders as its own state, distinct from a generic failure."
layer = "integration"
[[criteria]]
text = "S4 shows zero critical or serious axe violations during an in-flight inspection."
layer = "e2e"
gate = 5
```

- **Done:** `d9106c5` — evidence `specs/002-spotify-inspection/evidence/task-24.txt`

**Context pack (hint):** UX.md **S4** and flow **F5**; DESIGN.md; ARCHITECTURE
§17.1, §17.8; `AddLinkDialog.tsx`, the existing job-phase presentation components,
`api/generated.ts` (regenerate, never hand-edit).

---

## Task 25 — S12 Settings: Spotify credentials, mode, timeouts

```toml
id = 25
type = "feature"
chunk = "C3"
deps = [21]
files = [
  "frontend/src/features/settings/SettingsPage.tsx",
  "frontend/src/features/settings/InspectionSettingsCard.tsx",
  "frontend/src/api/generated.ts",
  "frontend/tests/component/inspection-settings.test.tsx",
]
consumes = """
PATCH /settings/inspection  {mode, timeout_spotify_s, timeout_spotdl_s, timeout_ytdlp_s, revision}
PATCH /settings/providers/spotify_api  {client_id, client_secret, clear_secret, revision}
GET /settings -> `inspection` block and masked `spotify_api` block
"""
[[criteria]]
text = "Saving credentials shows the block as configured without ever echoing the secret; clearing them returns it to the unconfigured state, which reads as a normal state explaining that Spotify links will use SpotDL instead."
layer = "integration"
[[criteria]]
text = "Switching mode between Fast and Thorough persists and each option states its trade in one line."
layer = "integration"
[[criteria]]
text = "A timeout outside its range is rejected at the field with the permitted range stated, and nothing is saved."
layer = "integration"
[[criteria]]
text = "S12 shows zero critical or serious axe violations with the inspection card present."
layer = "e2e"
gate = 5
```

**Context pack (hint):** UX.md **S12**; DESIGN.md; ARCHITECTURE §17.8;
`SettingsPage.tsx` and the existing proxy/provider card components for the
credential conventions to mirror.

---

## Task 26 — DEMO GATE 5: inspect fast, fall back, cancel, persist

```toml
id = 26
type = "gate"
chunk = "C3"
deps = [21, 22, 23, 24, 25]
files = [
  "frontend/tests/e2e/gate-5-inspection.spec.ts",
  "specs/002-spotify-inspection/evidence/task-26.txt",
]
[[criteria]]
text = "The walked journey, including its offline step, is encoded and green in frontend/tests/e2e/gate-5-inspection.spec.ts and joins the journey suite."
layer = "e2e"
gate = 5
[[criteria]]
text = "S4 and S12 show zero critical or serious axe violations during the walked journey."
layer = "e2e"
gate = 5
[gate]
n = 5
release = false
launch = "docker compose --env-file .gate/insp/.env up --build -d"
seed = "./scripts/gate/seed.sh insp kernel-500"
unglamorous = "Offline: block the container's egress to Spotify mid-inspection and confirm a typed error and the SpotDL fallback appear, with no hang and no silent direct attempt."
[[gate.journey]]
step = "Paste Spotify client credentials in S12 and save; the block reads configured and the secret is never echoed."
task = 25
[[gate.journey]]
step = "Paste a Spotify track link in S4; named phase text and a rising elapsed counter appear with Cancel enabled."
task = 24
[[gate.journey]]
step = "The candidate returns in about a second carrying album, disc and track number."
task = 22
[[gate.journey]]
step = "Download the track and play it."
task = 23
[[gate.journey]]
step = "Clear the credentials, paste a link, and watch the phase name the SpotDL fallback while the elapsed timer continues rather than resetting."
task = 24
[[gate.journey]]
step = "Start an inspection and press Cancel; it stops, the typed URL is preserved, and no spotdl process remains in the api container."
task = 23
[[gate.journey]]
step = "Restart the containers and reopen Settings; credential state, mode and timeouts are unchanged."
task = 21
[[gate.journey]]
step = "S4 shows zero critical or serious axe violations during an in-flight inspection."
task = 24
[[gate.journey]]
step = "S12 shows zero critical or serious axe violations with the inspection card present."
task = 25
[[gate.journey]]
step = "Offline: block the container's egress to Spotify mid-inspection and confirm a typed error and the SpotDL fallback appear, with no hang and no silent direct attempt."
task = 22
```

**Preflight:** `./scripts/gate/prepare.sh insp release` must write only under
`.gate/insp/` and fail closed against non-disposable targets, then launch and seed
with the commands above. Spotify credentials are **not** pre-seeded — entering them
is journey step 1, and they live only in the disposable tree.

The launch command is the production entry point with disposable config; there is
no gate-only composition. The human walkthrough result is the completion artifact;
the gate is Done only when that result is recorded **and** the crystallized journey
test is green.

---

## Task 27 — `edited_fields` threaded end to end

```toml
id = 27
type = "feature"
chunk = "C4"
deps = [26]
files = [
  "frontend/src/features/acquisition/YouTubeReviewDialog.tsx",
  "backend/src/chillify/api/schemas/downloads.py",
  "backend/src/chillify/application/downloads.py",
  "backend/tests/integration/test_edited_fields.py",
]
produces = """
POST /downloads request gains: edited_fields: list[str]
request_json persists edited_fields alongside the reviewed values
"""
[[criteria]]
text = "Submitting a review with album untouched persists a request_json whose edited_fields omits album; deliberately clearing album persists edited_fields containing album."
layer = "integration"
[[criteria]]
text = "A job whose worker restarts mid-flight still sees the original edited_fields, because it is read from request_json rather than memory."
layer = "integration"
[[criteria]]
text = "S5 marks fields the source never populated as not-yet-known, visibly distinct from a field left blank by the person."
layer = "integration"
[[criteria]]
text = "The extended POST /downloads request shape is called exactly as quoted and asserted, including a request omitting edited_fields entirely for backward compatibility."
layer = "contract"
```

Per ARCHITECTURE §17.5 `TrackCandidate` stays `str | None`: touched-ness is a
property of the *review*, not of the domain value object.

**Context pack (hint):** ARCHITECTURE §17.5, §7; UX.md **S5**; DESIGN.md;
`YouTubeReviewDialog.tsx`, `api/schemas/downloads.py`, `application/downloads.py`.

---

## Task 28 — Last.fm gap enrichment call site

```toml
id = 28
type = "feature"
chunk = "C5"
deps = [27]
files = [
  "backend/src/chillify/application/downloads.py",
  "backend/src/chillify/infrastructure/providers/registry.py",
  "backend/tests/integration/test_enrichment.py",
]
consumes = """
MetadataEnricher.enrich(candidate, missing_fields, proxy) -> MetadataPatch   # ARCHITECTURE line 190
request_json.edited_fields: list[str]
"""
[[criteria]]
text = "A track whose album was never touched and is empty has its album filled by the enricher, and the job's enriching phase records that a real fill happened."
layer = "integration"
[[criteria]]
text = "A track whose album was deliberately cleared in review keeps an empty album after the job completes."
layer = "integration"
[[criteria]]
text = "With no Last.fm key configured, the enriching phase records that enrichment was skipped rather than that it succeeded, and the job still completes."
layer = "integration"
[[criteria]]
text = "An enricher failure or timeout leaves every field unchanged and never fails the job."
layer = "integration"
[[criteria]]
text = "The enricher can never overwrite a populated or edited field, only fill an empty untouched one."
layer = "integration"
```

Interior task: single module, consumes an existing protocol, produces no new
cross-module contract.

**Context pack (hint):** ARCHITECTURE §7, §17.6, protocol line 190;
`application/downloads.py`, `providers/lastfm.py`, `providers/registry.py`.
Backend only.

---

## Task 29 — Production-composition proof, NFR measurements, stopgap revert

```toml
id = 29
type = "proof"
chunk = "C6"
deps = [28]
files = [
  "scripts/verify/nfr.sh",
  "scripts/production_canary.sh",
  "backend/src/chillify/infrastructure/providers/spotdl.py",
  "deploy/nginx.conf",
  "backend/tests/integration/test_production_composition.py",
  "frontend/tests/e2e/inspection.spec.ts",
]
produces = "./scripts/production_canary.sh --env-file .gate/release/.env --no-live-success"
[[criteria]]
text = "The unchanged production composition resolves the real SpotifyApiInspector, asserted directly rather than inferred."
layer = "integration"
[[criteria]]
text = "The canary's live reachability probe runs inside the api container and fails closed when the container cannot reach Spotify, even when the host can."
layer = "contract"
[[criteria]]
text = "Commit 8dcda66's 180s inspect and 200s nginx stopgaps are gone, and both timeouts come from settings."
layer = "contract"
[[criteria]]
text = "NFR-1 p95, NFR-2 worst-case sum, NFR-3 no surviving process, NFR-4 non-blocking and NFR-5 sentinel-secret absence each emit their named measurement."
layer = "e2e"
gate = 6
```

**Why the canary changes here:** the parent cycle's probe ran on the **host**, which
inherits the host's `http_proxy`, and reported reachability while the containers had
none — a false PASS that let a broken gate through preflight. This cycle's release
gate depends on the canary, so it is fixed here rather than left in the parent queue.

**Context pack (hint):** ARCHITECTURE §17.3, §17.7, §14; `scripts/production_canary.sh`,
`scripts/verify/nfr.sh`, `test_production_composition.py`. Operator surfaces only —
no DESIGN.md.

---

## Task 30 — RELEASE GATE 6: the cycle's exit bar

```toml
id = 30
type = "gate"
chunk = "C6"
deps = [21, 22, 23, 24, 25, 26, 27, 28, 29]
files = [
  "frontend/tests/e2e/gate-6-release.spec.ts",
  "specs/002-spotify-inspection/evidence/task-30.txt",
]
[[criteria]]
text = "The walked kernel journey, including its invalid-input step, is encoded and green in frontend/tests/e2e/gate-6-release.spec.ts and joins the journey suite."
layer = "e2e"
gate = 6
[[criteria]]
text = "Named NFR evidence, Chromium and Firefox smoke, and zero critical or serious axe violations are recorded against the release stack."
layer = "e2e"
gate = 6
[gate]
n = 6
release = true
launch = "docker compose --env-file .gate/release/.env up --build -d"
seed = "./scripts/gate/seed.sh release kernel-500"
unglamorous = "Invalid input: paste a malformed URL, a Spotify album URL, and an out-of-range timeout; each is refused at the right place with its own message, and nothing is persisted."
[[gate.journey]]
step = "Configure Spotify credentials in S12; stored encrypted, reported only as configured."
task = 25
[[gate.journey]]
step = "Paste a Spotify track link in S4; named phase and rising elapsed appear."
task = 24
[[gate.journey]]
step = "The candidate returns in about a second with album, disc and track number."
task = 22
[[gate.journey]]
step = "Review and download it, then hear it play."
task = 27
[[gate.journey]]
step = "Clear the credentials; the phase names the SpotDL fallback and the elapsed timer continues."
task = 24
[[gate.journey]]
step = "Cancel an inspection mid-phase; no spotdl process survives."
task = 23
[[gate.journey]]
step = "Add a track with an unknown album, leave it untouched, and download it; Last.fm fills the album and the enriching phase reports real work."
task = 28
[[gate.journey]]
step = "Restart the containers; credentials, mode and timeouts persist."
task = 21
[[gate.journey]]
step = "NFR-1 p95, NFR-2 worst-case sum, NFR-3 no surviving process, NFR-4 non-blocking and NFR-5 sentinel-secret absence each emit their named measurement."
task = 29
[[gate.journey]]
step = "Invalid input: paste a malformed URL, a Spotify album URL, and an out-of-range timeout; each is refused at the right place with its own message, and nothing is persisted."
task = 25
```

**Preflight:** `./scripts/gate/prepare.sh release release`, then
`./scripts/production_canary.sh --env-file .gate/release/.env --no-live-success`
must PASS with the real `SpotifyApiInspector` reported **and its probe running
inside the container** (Task 29). Both scripts fail closed unless the paths are
under `.gate/release/` and the Redis prefix is `chillify:gate:release:`.

The human walkthrough result and the named NFR evidence are the completion
artifacts. On completion, the parent cycle's Gate 4 preflight re-runs.
