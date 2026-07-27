---
status: ready
---

# Chillify Core Tasks

Tasks are sequential unless their dependencies say otherwise. Completion evidence is recorded in `specs/001-core/evidence/task-N.txt` under the verification machinery in `WORKFLOW.md`. Context packs are implementation hints and must be checked against the working tree; quoted interfaces are the governing contracts.

## Task 0 — Scaffold the production-shaped repository

Objective: create the file tree, pinned tooling, migrations, token source, and documented boot command without feature behavior.

```toml
id = 0
type = "scaffold"
chunk = 1
deps = []
skeleton = true
files = ["compose.yaml", ".env.example", ".gitignore", "biome.json", "backend/pyproject.toml", "backend/uv.lock", "backend/alembic.ini", "backend/migrations/env.py", "backend/migrations/script.py.mako", "backend/migrations/versions/0001_core.py", "frontend/package.json", "frontend/package-lock.json", "frontend/components.json", "frontend/vite.config.ts", "frontend/vitest.config.ts", "frontend/tsconfig.app.json", "frontend/src/main.tsx", "frontend/src/styles/tokens.css", "frontend/src/styles/globals.css", "CONVENTIONS.md"]
produces = ["docker compose --env-file .gate/<name>/.env up --build -d", "frontend/src/styles/tokens.css"]

[[criteria]]
text = "The documented disposable Compose boot command starts the web, API, and serial worker and applies the initial SQLite schema."
layer = "integration"
[[criteria]]
text = "Invalid configuration is rejected before migration with a named error."
layer = "unit"
[[criteria]]
text = "The scaffold contract test invokes docker compose --env-file .gate/<name>/.env up --build -d and asserts the production-shaped service topology and token source path."
layer = "contract"
```

Context pack (hint): `specs/001-core/FILE_STRUCTURE.md`, `CONVENTIONS.md`, `DESIGN.md` token source, and ARCHITECTURE §§2–4, 12, 14. UI screen: persistent shell foundation.

- **Done:** `7a1e852` — evidence `specs/001-core/evidence/task-0.txt`
  Tasks 0 and 1 were implemented as one batch and share this commit; chunk 1 is one coherent outcome under the CONVENTIONS commit rule.

## Task 1 — Boot/status API and persistent household shell

Objective: finish Chunk 1’s validated composition, status envelope, redacted logging, health behavior, and route-outlet shell.

```toml
id = 1
type = "feature"
chunk = 1
deps = [0]
skeleton = true
files = ["backend/src/chillify/config.py", "backend/src/chillify/composition.py", "backend/src/chillify/logging/setup.py", "backend/src/chillify/logging/redaction.py", "backend/src/chillify/api/main.py", "backend/src/chillify/api/routes/system.py", "backend/src/chillify/worker/main.py", "backend/src/chillify/infrastructure/db/engine.py", "deploy/docker/backend.Dockerfile", "deploy/docker/web.Dockerfile", "deploy/nginx.conf", "frontend/src/app/AppProviders.tsx", "frontend/src/app/PersistentShell.tsx", "frontend/src/app/AppSidebar.tsx", "frontend/src/app/TopBar.tsx", "frontend/src/app/Router.tsx", "frontend/src/components/ui/{badge,button,sidebar,sonner,tooltip}.tsx"]
consumes = ["docker compose --env-file .gate/<name>/.env up --build -d", "frontend/src/styles/tokens.css"]
produces = ["GET /system/status"]

[[criteria]]
text = "A disposable production Compose launch exposes readiness and provider/Redis degradation at /api/v1/system/status."
layer = "integration"
[[criteria]]
text = "Rich API and worker records contain request/service context while redacting sentinel proxy and Last.fm secrets."
layer = "unit"
[[criteria]]
text = "The generated OpenAPI test calls GET /system/status and asserts the documented success/error envelope shape."
layer = "contract"
```

Context pack (hint): Task 0 files, `ARCHITECTURE.md` §§5, 11–12, 14–15, `UX.md` persistent shell/operator surfaces, `DESIGN.md`. UI screens: shell/S2–S12.

- **Done:** `7a1e852` — evidence `specs/001-core/evidence/task-1.txt`
  Shares the Task 0 commit; see the note there.

## Task 2 — Profile, library stream, and persistent playback

```toml
id = 2
type = "feature"
chunk = 2
deps = [1]
skeleton = true
files = ["backend/src/chillify/domain/{models,normalization,ordering}.py", "backend/src/chillify/infrastructure/db/{models,repositories}.py", "backend/src/chillify/api/schemas/{profiles,tracks}.py", "backend/src/chillify/api/routes/{profiles,library,tracks}.py", "frontend/src/api/{client,generated}.ts", "frontend/src/features/profiles/ProfileChooser.tsx", "frontend/src/features/library/{LibraryPage,TrackTable}.tsx", "frontend/src/features/player/{playerStore,PersistentPlayer,useAudioController}.ts", "frontend/src/components/ui/{aspect-ratio,dropdown-menu,empty,skeleton,slider,table}.tsx"]
produces = ["POST /profiles", "GET /library/tracks", "GET /tracks/{id}/stream"]

[[criteria]]
text = "A created profile and seeded mounted MP3 survive API restart, and the track stream serves full and byte-range responses."
layer = "integration"
[[criteria]]
text = "Normalization, year validation, context ordering, and path containment obey the documented invariants."
layer = "unit"
[[criteria]]
text = "OpenAPI-generated client calls POST /profiles, GET /library/tracks, and GET /tracks/{id}/stream with the documented response shapes."
layer = "contract"
[[criteria]]
text = "Create/select Household and open the shared library."
layer = "e2e"
gate = 1
```

Context pack (hint): ARCHITECTURE §§4–5, 8–10; `UX.md` S1/S2; `DESIGN.md`.

- **Done:** `150d380` — evidence `specs/001-core/evidence/task-2.txt`
  The `[e2e@gate-1]` criterion is Task 5's demo gate and is not claimed here.
  Two dependency-plan decisions were taken with the user and recorded in the
  ARCHITECTURE Decision log: `typescript` moves to the 5 line, and a scoped
  `js-yaml` override clears GHSA-52cp-r559-cp3m.

## Task 3 — Local-first search and durable serial download queue

```toml
id = 3
type = "feature"
chunk = 3
deps = [2]
skeleton = true
fake_of = "Deezer/acquisition external protocols"
files = ["backend/src/chillify/domain/{jobs,protocols}.py", "backend/src/chillify/application/{search,downloads}.py", "backend/src/chillify/infrastructure/providers/{registry,fixtures}.py", "backend/src/chillify/infrastructure/queue/{celery_app,tasks}.py", "backend/src/chillify/infrastructure/media/storage.py", "backend/src/chillify/api/{schemas/downloads.py,routes/search.py,routes/downloads.py,routes/events.py}", "frontend/src/features/search/{SearchPage,ResultCards}.tsx", "frontend/src/features/downloads/{DownloadsPage,GlobalJobIndicator}.tsx", "frontend/src/app/EventBridge.tsx", "backend/tests/fixtures/providers/deezer_search.json", "backend/tests/fixtures/media/gate-tone.mp3"]
produces = ["GET /search/deezer", "POST /downloads", "GET /events"]

[[criteria]]
text = "Closing the browser does not stop a fixture job; reopening shows its durable completion and mounted track."
layer = "integration"
[[criteria]]
text = "Three fixture jobs run no more than one acquisition phase concurrently."
layer = "integration"
[[criteria]]
text = "One shared protocol suite runs against fixture and production acquisition adapters, including rejected wire inputs."
layer = "contract"
[[criteria]]
text = "Search locally with no provider activity, explicitly search Deezer, and download one non-playable remote result."
layer = "e2e"
gate = 1
```

Context pack (hint): ARCHITECTURE §§5–7, 10–11; `UX.md` S3/S11; `DESIGN.md`.

- **Done:** `1527746` — evidence `specs/001-core/evidence/task-3.txt`
  The `[e2e@gate-1]` criterion is Task 5's demo gate and is not claimed here;
  its behaviour was exercised out of process against the running app (Redis,
  uvicorn, and `python -m chillify.worker.main`) and recorded in the evidence.
  Two adjustments to the predicted file set: the Deezer wire translation lives
  in `infrastructure/providers/deezer_wire.py` so a production adapter and a
  fixture adapter cannot disagree about the payload, and the job/idempotency
  rows joined `infrastructure/db/{models,repositories}.py` rather than growing
  a second persistence path.
  Two defects inherited from earlier tasks were repaired here because this task
  could not be committed correctly without them: the unanchored `media/` ignore
  rule had kept `infrastructure/media/storage.py` out of every commit since
  Task 2, and `scripts/gate/prepare.sh` created an empty fixture root that the
  gate adapters cannot read.

## Task 4 — Atomic correction, playlists, and gate safety scripts

```toml
id = 4
type = "feature"
chunk = 4
deps = [3]
skeleton = true
files = ["backend/src/chillify/application/{artwork,metadata,playlists}.py", "backend/src/chillify/infrastructure/media/{artwork,tags,mutations}.py", "backend/src/chillify/api/{schemas/artwork.py,schemas/playlists.py,routes/artwork.py,routes/playlists.py}", "frontend/src/features/metadata/{TrackEditorDialog,ArtworkPicker}.tsx", "frontend/src/features/playlists/{PlaylistsPage,PlaylistPage,PlaylistEditorDialog}.tsx", "frontend/src/features/library/TrackRow.tsx", "scripts/gate/{prepare,seed,cleanup}.sh", "backend/src/chillify/gate_seed.py", "frontend/src/components/ui/{card,dialog}.tsx"]
produces = ["PATCH /tracks/{id}", "POST /profiles/{profile_id}/playlists", "./scripts/gate/prepare.sh gate-1 kernel"]

[[criteria]]
text = "An artwork/metadata edit updates MP3 tags, mounted path, artwork, and database atomically and restart preserves only the new version."
layer = "integration"
[[criteria]]
text = "Playlist name and track uniqueness are enforced per profile."
layer = "integration"
[[criteria]]
text = "The contract test sends PATCH /tracks/{id} and POST /profiles/{profile_id}/playlists and asserts atomic-edit and playlist response shapes."
layer = "contract"
[[criteria]]
text = "Play, correct metadata/art, create a playlist, add/play the track, and navigate without playback reset."
layer = "e2e"
gate = 1
```

Context pack (hint): ARCHITECTURE §§5, 8, 10; `UX.md` S5/S9/S10/S13/S16; `DESIGN.md`.

- **Done:** `7004f67` — evidence `specs/001-core/evidence/task-4.txt`
  Scope notes, against the task's predicted file list: `TrackRow.tsx` does not
  exist in the tree — its row actions were added to the real `TrackTable.tsx`.
  Registering routes and adding the playlist/artwork/mutation persistence
  required editing `db/{models,repositories}.py`, `api/{main,dependencies}.py`,
  `composition.py`, `domain/{models,errors,normalization}.py`, and
  `api/{routes,schemas}/tracks.py` beyond the listed files. `write_audio_tags`
  moved from `media/storage.py` to the new `media/tags.py`, which the task's
  file list introduces. S5 belongs to Task 6 (`POST /links/inspect` is that
  task's contract), so the reviewed-YouTube editor is not built here; playlist
  reorder, row removal, and drag handles belong to Task 12.

## Task 5 — DEMO GATE 1: walking skeleton

```toml
id = 5
type = "gate"
chunk = 4
deps = [1, 2, 3, 4, 21, 22]
files = ["frontend/tests/e2e/gate-1.spec.ts", "specs/001-core/evidence/task-5.txt"]

[[criteria]]
text = "The scripted Gate 1 journey, including production-container recreation, is encoded and green in frontend/tests/e2e/gate-1.spec.ts."
layer = "e2e"
gate = 1

[gate]
n = 1
release = false
launch = "./scripts/gate/prepare.sh gate-1 gate && docker compose --env-file .gate/gate-1/.env -f compose.yaml -f deploy/compose.gate.yaml up --build -d"
seed = "./scripts/gate/seed.sh gate-1"
unglamorous = "Restart: recreate production containers with the same disposable mounts and verify durable records while the browser session queue is empty."
[[gate.journey]]
step = "Create/select Household and open the shared library."
task = 2
[[gate.journey]]
step = "Search locally with no provider activity, explicitly search Deezer, and download one non-playable remote result."
task = 3
[[gate.journey]]
step = "Close/reopen the browser and observe truthful durable queued-to-completed state."
task = 3
[[gate.journey]]
step = "Play, correct metadata/art, create a playlist, add/play the track, and navigate without playback reset."
task = 4
[[gate.journey]]
step = "Restart: recreate production containers with the same disposable mounts and verify durable records while the browser session queue is empty."
task = 4
```

Preflight: run `./scripts/gate/prepare.sh gate-1 kernel` first; it must reject paths outside `.gate/gate-1/` and a non-gate Redis prefix. Record the human walkthrough outcome in the evidence file before marking this task done.

- **GATE BLOCKED** — the preflight cannot launch the app, so no walkthrough was
  offered. `docker compose --env-file .gate/gate-1/.env up --build -d` fails
  building the `web` image: `npm ci` reports `@emnapi/core@1.11.2` and
  `@emnapi/runtime@1.11.2` missing from `frontend/package-lock.json`. The lock
  pins those transitive wasm dependencies at `1.11.1` under
  `@rolldown/binding-wasm32-wasi`. It is a toolchain split, not a dependency
  change: the same two files pass `npm ci --dry-run` under the host's npm
  11.6.1 and fail under the npm 11.16.0 in `node:24.18.0-trixie-slim`. That
  makes `verify.sh`'s frontend lockfile-drift step a false negative — it
  validates with whatever npm the developer happens to have rather than with
  the one that builds the production image. Fixed by Task 4a; re-run this
  preflight once that lands.
  Two preflight notes recorded while blocked: `prepare.sh`'s second argument is
  the mode (`production|gate`), so the `gate.launch`/`produces` string
  `prepare.sh gate-1 kernel` is not runnable as written — `kernel` is the chunk
  label, and the gate needs `gate` mode for the fixture adapters and the
  `chillify:gate:gate-1:` Redis prefix. The script refused `kernel` with exit 2,
  which is the fail-closed behaviour working. Separately, `compose.yaml` ships
  no Redis service by design, so the preflight must supply one the containers
  can resolve; `REDIS_URL` was set at prepare time to a disposable Redis
  container attached to the compose network.
- **GATE 1 WALKED — PASS** (2026-07-22, user) — evidence `specs/001-core/evidence/task-5.txt`
  Preflight cleared after Tasks 4a and 4b (the gate could not launch before
  either landed). The human walked all five journey steps against the recreated
  production composition and confirmed them (screenshots shared in the review
  session, not committed to the repository). The journey is crystallized as
  `frontend/tests/e2e/gate-1.spec.ts`, which provisions a fresh seeded gate
  stack, walks the whole story, force-recreates the containers for the
  durability step, and tears the stack down — green in one run.
  The gate's recorded `launch`/`seed` were corrected here: the launch overlays
  `deploy/compose.gate.yaml` and prepares the gate env first, and the seed drops
  the spurious `kernel` argument. The original `prepare.sh gate-1 kernel` string
  was never runnable — `kernel` is the chunk label, not a mode.

## Task 4a — Align the frontend lockfile with the image toolchain

```toml
id = 21
type = "fix"
chunk = 4
deps = [4]
files = ["frontend/package-lock.json", "scripts/verify.sh", "CONVENTIONS.md"]

[[criteria]]
text = "`npm ci` succeeds under the npm version in deploy/docker/web.Dockerfile's base image, and the production web image builds."
layer = "integration"
[[criteria]]
text = "The verify script's frontend lockfile-drift step fails when the lockfile would not install in the image, rather than passing on the developer's npm."
layer = "integration"
```

Context pack (hint): `deploy/docker/web.Dockerfile`; `scripts/verify.sh`;
`CONVENTIONS.md` verification section.

- **Done:** `1391e16` — evidence `specs/001-core/evidence/task-4a.txt`
  The lock was regenerated inside the web image's base rather than on the host.
  No dependency version changed: the diff is only the optional wasm entries npm
  expects recorded for `@tailwindcss/oxide-wasm32-wasi` and
  `@rolldown/binding-wasm32-wasi`. The drift step now runs `npm ci --dry-run`
  in that image, reads the image reference out of `web.Dockerfile` so the two
  cannot drift apart, copies the two files in rather than bind-mounting them
  writable, runs `--network none`, and fails closed when docker is absent.
  Verified by restoring the old lock and watching the step fail on exactly what
  it used to pass.
  Two observations recorded rather than acted on, both outside this fix's
  scope: `package.json` pins `engines.npm` to 12.0.1 while the image base ships
  11.16.0, so every `npm` call in the build logs an `EBADENGINE` warning; and
  `npm audit` now reports 3 moderate advisories against
  `@modelcontextprotocol/sdk` via `shadcn` that were absent earlier the same
  day. Neither is caused by the lock change — the package versions are
  unchanged — and `--audit-level=high` passes moderate by design.

## Task 4b — Make gate containment expressible in the production containers

```toml
id = 22
type = "fix"
chunk = 4
deps = [4]
files = ["backend/src/chillify/config.py", "backend/tests/unit/test_config.py", "backend/tests/conftest.py", "deploy/compose.gate.yaml", "scripts/gate/prepare.sh", "ARCHITECTURE.md"]

[[criteria]]
text = "A gate launched through the production Compose file starts, with the fixture payloads mounted read-only and the gate-safety check satisfied."
layer = "integration"
[[criteria]]
text = "Production still refuses a fixture root, a gate containment root, and the gate Redis namespace; gate mode still refuses roots outside its declared containment root, split storage roots, and an undeclared containment root."
layer = "unit"
```

Context pack (hint): ARCHITECTURE §12 and the gate paragraph; `compose.yaml`;
`scripts/gate/*.sh`.

- **Done:** `c69d83c` — evidence `specs/001-core/evidence/task-4b.txt`
  The containerized-launch criterion, blocked earlier on an unreachable
  registry mirror, was exercised once the mirror returned: the production
  Compose file plus `deploy/compose.gate.yaml` now brings the gate up with
  migrate completing (it exited 1 before), `env=gate`, `ready=true`, and Redis
  reachable. The gate-safety unit criterion is covered by
  `tests/unit/test_config.py`. The disposable overlay Redis that makes the
  launch a single reproducible command landed in `475431a`. The whole path is
  additionally proven end to end by the green `gate-1.spec.ts` (Task 5), whose
  global setup provisions this exact stack.
  What changed and why: the old rule required `CHILLIFY_FIXTURE_ROOT` and both
  storage roots to resolve beneath *the repository's* `.gate/`. Gates are
  specified to run through the production Compose file, where the process sees
  `/var/lib/chillify` bind mounts and no repository, so that rule could never
  hold — and would not have been worth holding, because inside the container a
  gate and a household deployment present identical paths. Containment is now
  declared by `CHILLIFY_GATE_ROOT` and enforced in two places: the host scripts
  keep the tree beneath the repository's `.gate/`, and the process checks that
  every gate root agrees with the declared boundary. `deploy/compose.gate.yaml`
  overlays the fixture mount, read-only, so production never mounts fixtures.
  This patched the ARCHITECTURE gate paragraph, triggering the stale-plan rule;
  the scoped re-gate has since run clean (`brana-gate tasks` — 0 findings), so
  the `ready` stamp stands.

## Task 6 — Direct-link inspection and reviewed YouTube acquisition

```toml
id = 6
type = "feature"
chunk = 5
deps = [5]
fake_of = "yt-dlp/SpotDL external protocols"
files = ["backend/src/chillify/application/links.py", "backend/src/chillify/api/{schemas/links.py,routes/links.py}", "backend/src/chillify/infrastructure/providers/{ytdlp,spotdl}.py", "frontend/src/features/acquisition/{AddLinkDialog,YouTubeReviewDialog}.tsx", "frontend/src/components/ui/label.tsx", "backend/tests/contract/{test_ytdlp_contract,test_spotdl_contract}.py"]
produces = ["POST /links/inspect"]
[[criteria]]
text = "Unsupported, malformed, and bulk links create no durable job."
layer = "unit"
[[criteria]]
text = "Shared fixture/production protocol suites normalize yt-dlp and SpotDL candidates and errors."
layer = "contract"
[[criteria]]
text = "Inspect valid Spotify/YouTube links and reject bulk variants without jobs; review and download a YouTube candidate."
layer = "e2e"
gate = 2
```

- **Done:** `7c50e8d` — evidence `specs/001-core/evidence/task-6.txt`
  The `[e2e@gate-2]` criterion is Task 10's demo gate and is not claimed here;
  the unit and contract criteria are demonstrated by tests that drive the real
  route and adapters (`tests/integration/test_link_inspection.py` posts
  `/links/inspect` and asserts `GET /downloads` stays empty for every rejected
  link; `tests/{unit/test_link_inspection,contract/test_ytdlp_contract,
  contract/test_spotdl_contract}.py` cover the rest).
  Deviations from the predicted file set, all additive: `label.tsx` already
  existed from an earlier Shadcn install, so nothing was added there. Wiring the
  new route and inspection use case required editing `composition.py`,
  `api/{main,dependencies}.py`, and `infrastructure/providers/registry.py`
  beyond the listed files (registry gained a `link_inspectors` capability, bound
  to fixtures only in gate — the production adapters join it in Task 16, which
  already lists `registry.py`). The wire-normalization functions live inside
  `providers/{ytdlp,spotdl}.py` themselves rather than a separate `*_wire.py`,
  matching how `deezer_wire.py` is shared. Two frontend files not in the list
  were added to make the flow reachable and typed: the acquisition public module
  `features/acquisition/acquisitionQueries.ts` and the sidebar Add-music button
  in `app/AppSidebar.tsx` that opens S4. Two recorded fixtures were added under
  `tests/fixtures/providers/` (`ytdlp_inspect.json`, `spotdl_metadata.json`),
  which `scripts/gate/prepare.sh` already copies into every gate tree.

## Task 7 — Cancellation, retry, restart recovery, and deduplication

```toml
id = 7
type = "feature"
chunk = 6
deps = [6]
files = ["backend/src/chillify/application/reconciliation.py", "backend/src/chillify/infrastructure/queue/{reconciliation,cancellation}.py", "backend/src/chillify/infrastructure/media/workspaces.py", "frontend/src/features/downloads/DownloadRow.tsx", "backend/tests/integration/{test_queue_recovery,test_duplicates}.py"]
[[criteria]]
text = "Killing a worker mid-download requeues/restarts it and completes once with no duplicate file."
layer = "integration"
[[criteria]]
text = "Cancel cleans workspaces and advances the queue; retry creates a linked attempt; duplicate races yield one track/file."
layer = "integration"
[[criteria]]
text = "Queue three jobs, cancel/retry/interupt one worker, and resubmit duplicates to reach the existing track."
layer = "e2e"
gate = 2
```

- **Done:** `8d8ccef` — evidence `specs/001-core/evidence/task-7.txt`
  The `[e2e@gate-2]` criterion is Task 10's demo gate and is not claimed here;
  both integration criteria are demonstrated by tests that drive the real
  services against a migrated SQLite and mounted temp files
  (`tests/integration/test_queue_recovery.py` strands a running job by ageing
  its lease, reconciles, and runs it to a single track/file;
  `tests/integration/test_duplicates.py` covers duplicate races, the
  queued/mid-download cancel with workspace cleanup, and the parent-linked
  retry). The cooperative mid-download cancel is exercised across two threads —
  worker and canceller — the same split the request and worker are in
  production.
  Deviations from the predicted file set, all additive wiring the criteria and
  the ARCHITECTURE routes table (`POST /downloads/{id}/cancel` and `/retry`,
  §5) require: cancel/retry needed repository methods, `DownloadService`
  use cases, schema (`CancelRequestModel`), and routes in
  `api/{routes,schemas}/downloads.py` and `db/repositories.py`; the recovery
  triggers needed a `reconciliation_service()` factory in `composition.py`,
  a `worker_ready`/lifespan hook in `worker/main.py` and `api/main.py`, and the
  regenerated `frontend/src/api/generated.ts`. `DownloadRow.tsx` is reached by
  swapping the inline active-queue row in `DownloadsPage.tsx` and adding a
  Retry action to its finished-job diagnostics; the two mutation hooks live in
  the feature's public module `downloadJobs.ts`.
  One internal-ambiguity choice, noted in code: cancellation has two channels —
  the durable `cancel_requested_at` flag for the cross-process case and an
  in-process `ActiveAcquisitions` signal (plus the process-group teardown the
  real subprocess adapters will use in Task 16) for the same-process fast path.

## Task 8 — Proxy-first settings and degraded local behavior

```toml
id = 8
type = "feature"
chunk = 7
deps = [7]
fake_of = "Deezer/Last.fm outbound HTTP"
files = ["backend/src/chillify/application/settings.py", "backend/src/chillify/infrastructure/security/{secrets,outbound}.py", "backend/src/chillify/infrastructure/providers/{deezer,lastfm}.py", "backend/src/chillify/api/{schemas/settings.py,routes/settings.py}", "frontend/src/features/settings/{SettingsPage,ProviderCard,StorageDiagnostics}.tsx", "frontend/src/components/ui/{select,switch}.tsx", "backend/tests/integration/test_proxy_fail_closed.py"]
produces = ["PATCH /settings/proxy", "GET /settings"]
[[criteria]]
text = "Invalid proxy traffic has zero direct fallback attempts and sentinel secrets appear in no API body or Rich log."
layer = "integration"
[[criteria]]
text = "The shared HTTP adapter contract suite exercises fixture and production adapters with the same proxy/rejection policy."
layer = "contract"
[[criteria]]
text = "Force proxy failure, inspect masked diagnostics, toggle a provider, and retain local behavior through Redis loss and recovery."
layer = "e2e"
gate = 2
```

- **Done:** `75b6a38` — evidence `specs/001-core/evidence/task-8.txt`
  - The `[e2e@gate-2]` criterion is deferred to Task 10 (DEMO GATE 2); this task
    delivers the integration and contract acceptance. Backend: one fail-closed
    `OutboundHttp` policy (proxy-first, no direct fallback, bounded retry),
    Fernet secret encryption, masked settings CRUD (`GET /settings`,
    `PATCH /settings/proxy`, `POST /settings/proxy/test`,
    `PATCH/POST /settings/providers/{provider}`), and production Deezer/Last.fm
    adapters over the shared policy. Frontend: S12 SettingsPage with proxy,
    provider cards, and storage/tool diagnostics; `switch` primitive added.
  - Verified: `./scripts/verify.sh` → all checks passed (365 backend, 67
    frontend). Acceptance evidence in `task-8.txt` (28 tests: proxy fail-closed
    integration + shared outbound-policy contract).

```toml
id = 9
type = "feature"
chunk = 8
deps = [8]
files = ["backend/src/chillify/application/deletion.py", "backend/src/chillify/infrastructure/media/recovery.py", "backend/src/chillify/api/{schemas/deletion.py,routes/tracks.py}", "frontend/src/features/metadata/DeleteTrackDialog.tsx", "frontend/src/components/ui/alert-dialog.tsx", "backend/tests/integration/{test_media_edit_recovery,test_media_delete_recovery}.py"]
produces = ["DELETE /tracks/{id}"]
[[criteria]]
text = "Every injected edit/delete failure recovers to one authoritative playable state."
layer = "integration"
[[criteria]]
text = "Successful deletion removes files, records, playlist/session references, and identifying history metadata."
layer = "integration"
[[criteria]]
text = "The DELETE /tracks/{id} contract test asserts a no-content response and anonymous history behavior."
layer = "contract"
[[criteria]]
text = "Inject edit failure, successfully edit, then delete a playing playlist track with restart-safe anonymous history."
layer = "e2e"
gate = 2
```

- **Done:** `ab97fd9` — evidence `specs/001-core/evidence/task-9.txt`
  The `[e2e@gate-2]` criterion is Task 10's demo gate and is not claimed here;
  the two integration criteria and the contract criterion are demonstrated by
  tests that drive the real DELETE route and services against a migrated SQLite
  and mounted temp files (`tests/integration/test_media_delete_recovery.py`
  covers the successful deletion — files/records/playlist refs removed and the
  completed job reduced to an anonymous shell — plus the interrupted
  before/after-commit recovery paths; `tests/integration/test_media_edit_recovery.py`
  covers edit finalize-after-commit and rollback-before-commit, including the
  real API boot running recovery in its lifespan; `tests/contract/test_deletion_contract.py`
  asserts the documented 204 no-content shape and the anonymous-history served
  behavior). `./scripts/verify.sh` → all checks passed (380 backend, 67
  frontend).
  Deviations from the predicted file set, all additive wiring the criteria and
  the ARCHITECTURE §8 deletion/recovery contracts require: `DELETE /tracks/{id}`
  and `GET /tracks/{id}/delete-impact` (the S15 impact endpoint from the routes
  table) needed repository methods (`begin_deletion`, `delete`,
  `playlist_reference_count`, `anonymize_for_deleted_track`, `open_delete`,
  `list_recoverable`), a `DeletionService`/`MediaRecoveryService` factory pair in
  `composition.py`, a `get_deletion_service` dependency, a `MediaMutationJournal`
  domain value object in `domain/models.py`, and a media-recovery lifespan hook
  in `api/main.py`. Startup recovery covers edit journals too — the edit
  in-request path (Task 4) already rolls itself back while the process lives; the
  crash-recovery half was deferred here alongside deletion, matching the
  ARCHITECTURE two-stage-deletion/edit-recovery paragraphs. Frontend: the
  `DeleteTrackDialog` (S15) and `alert-dialog` primitive are listed; reaching S15
  from S13 required a Delete action in `TrackEditorDialog.tsx`, and the regenerated
  `frontend/src/api/generated.ts` plus a `DeleteImpact` client type and a
  `deleteImpact` query key. Player-on-delete continuity (advance/stop when the
  current track is deleted) is Task 13's `playerStore` resilience and is not built
  here; the dialog invalidates library/playlist queries on success.

## Task 9a — Reach an operator proxy on the Docker host

```toml
id = 23
type = "fix"
chunk = 8
deps = [8]
files = ["compose.yaml"]

[[criteria]]
text = "`host.docker.internal` resolves inside the api and worker containers, so a proxy the operator runs on the Docker host is reachable and `POST /settings/proxy/test` against `socks5://host.docker.internal:PORT` gets past DNS to the proxy itself."
layer = "integration"
```

Context pack (hint): `compose.yaml` backend services; `deploy/compose.gate.yaml`;
Task 8 outbound policy.

- **Done:** `4da9cd2` — evidence `specs/001-core/evidence/task-9a.txt`
  Gate 2 preflight finding (user, 2026-07-22): the proxy test failed on a host
  proxy at `socks5://host.docker.internal:10808`. On Linux that name does not
  resolve inside a container without an explicit host-gateway mapping, so the
  outbound policy failed on DNS before reaching the operator's (working) proxy —
  a container-networking gap, not an app defect. Fixed by mapping
  `host.docker.internal:host-gateway` on api and worker (the two outbound
  services); migrate and web make no proxy calls. Verified against the live gate
  stack: the name resolves to the host gateway and the proxy test returns
  `{"ok":true,"code":"ok"}` through the container to the real host proxy.

## Task 10 — DEMO GATE 2: acquisition and recovery

```toml
id = 10
type = "gate"
chunk = 8
deps = [6, 7, 8, 9]
files = ["frontend/tests/e2e/gate-2.spec.ts", "specs/001-core/evidence/task-10.txt"]
[[criteria]]
text = "The complete Gate 2 acquisition/recovery journey, including Redis degradation, is encoded and green in frontend/tests/e2e/gate-2.spec.ts."
layer = "e2e"
gate = 2
[gate]
n = 2
release = false
launch = "docker compose --env-file .gate/gate-2/.env up --build -d"
seed = "./scripts/gate/seed.sh gate-2 recovery"
unglamorous = "Offline: stop Redis, browse/search/play local content, restore Redis, and observe unfinished work requeue without web restart."
[[gate.journey]]
step = "Inspect valid Spotify/YouTube links and reject bulk variants without jobs; review and download a YouTube candidate."
task = 6
[[gate.journey]]
step = "Queue three jobs, cancel/retry/interupt one worker, and resubmit duplicates to reach the existing track."
task = 7
[[gate.journey]]
step = "Force proxy failure, inspect masked diagnostics, toggle a provider, and retain local behavior through Redis loss and recovery."
task = 8
[[gate.journey]]
step = "Inject edit failure, successfully edit, then delete a playing playlist track with restart-safe anonymous history."
task = 9
[[gate.journey]]
step = "Offline: stop Redis, browse/search/play local content, restore Redis, and observe unfinished work requeue without web restart."
task = 8
```

Preflight: `./scripts/gate/prepare.sh gate-2 recovery` must establish `.gate/gate-2/` roots and its isolated Redis prefix before launch. Record the human walkthrough result in the evidence file.

- **GATE 2 WALKED — PASS** (2026-07-22, user) — evidence `specs/001-core/evidence/task-10.txt`
  The human walked all five journey steps against the recreated gate
  composition and confirmed them. The journey is crystallized as
  `frontend/tests/e2e/gate-2.spec.ts`, which reprovisions a fresh seeded gate
  stack, walks the whole story — bulk-link rejection, YouTube review, a
  worker-stopped cancel/retry and duplicate-reaches-existing-track, proxy
  fail-closed with credential masking and a provider toggle, a household
  deletion, and Redis stop/start with local playback retained — and tears the
  stack down. Green in two consecutive runs (31–35s).
  Recorded `launch`/`seed` were corrected here, the same overlay/label bug
  caught at Gate 1: a gate launches the production composition **plus** the
  fixture overlay in `gate` mode, so the runnable launch is
  `./scripts/gate/prepare.sh gate-2 gate && docker compose --env-file
  .gate/gate-2/.env -f compose.yaml -f deploy/compose.gate.yaml up --build -d`,
  and the seed is `./scripts/gate/seed.sh gate-2` — `recovery` is the chunk
  label, not a mode or a seed argument, and `seed.sh` takes only the gate name.
  Two preflight findings, both non-blocking and user-triaged: the "Downloads
  degraded" header is the real tools probe reporting spotdl absent from the
  image (expected; the binary ships in Task 16), and a host proxy at
  `socks5://host.docker.internal:PORT` was unreachable on Linux until Task 9a
  mapped the host gateway.
  The two browser-undrivable fault-injection guarantees the journey names — a
  worker killed mid-download, and an edit that fails after writing its files
  with restart-safe anonymous history — are asserted by the backend integration
  suites (`test_queue_recovery`, `test_media_edit_recovery`,
  `test_media_delete_recovery`) rather than re-driven through the browser.

- **Done:** `dca6211` — evidence `specs/001-core/evidence/task-10.txt`

## Task 11 — Artist, album, and year contexts

```toml
id = 11
type = "feature"
chunk = 9
deps = [10]
files = ["backend/src/chillify/application/library.py", "backend/src/chillify/api/{schemas/library.py,routes/library.py}", "frontend/src/features/library/{ContextPage,ContextGrid,contextQueue}.tsx", "frontend/src/components/ui/tabs.tsx", "backend/tests/integration/test_context_ordering.py"]
produces = ["GET /library/artists/{artist_key}", "GET /library/albums/{album_key}", "GET /library/years/{year_key}"]
[[criteria]]
text = "Seeded contexts return exact documented artist/album/year order including unknown values."
layer = "integration"
[[criteria]]
text = "Context keys round-trip canonically and albums with equal names but different artists remain separate."
layer = "unit"
[[criteria]]
text = "The context endpoint contract test calls each documented context endpoint and asserts ordered track-array shapes."
layer = "contract"
[[criteria]]
text = "Browse seeded Tracks, Artists, Albums, and Years including Unknown Year; play each and compare Queue order."
layer = "e2e"
gate = 3
```

- **Done:** `868446c` — evidence `specs/001-core/evidence/task-11.txt`
  The `[e2e@gate-3]` criterion is Task 15's demo gate and is not claimed here;
  the integration, unit, and contract criteria are demonstrated by tests that
  drive the real routes against migrated SQLite and mounted files
  (`tests/integration/test_context_ordering.py` seeds out-of-order tracks and
  asserts the exact artist/album/year order including Unknown Year, empty
  contexts, and same-named-albums separation; `tests/unit/test_normalization.py`
  covers the year-key round trip and canonical rejection; the context assertions
  in `tests/contract/test_openapi_contract.py` call each documented endpoint and
  assert the ordered track-array shapes). `./scripts/verify.sh --fast` → all
  checks passed; `vite build` green.
  Deviations from the predicted file set, all additive: `produces` names only
  the three `{key}` detail endpoints, but ARCHITECTURE §5 also defines the three
  collection endpoints (`GET /library/{artists,albums,years}`) that the listed
  `ContextGrid` + `tabs` browse UI needs, so all six were built. Following the
  `/profiles` precedent, the collections are bounded by household use and served
  whole with an optional `q` filter and no cursor param (the routes table lists
  `q, cursor`; omitting the cursor changes no user-visible result at household
  scale). The year key lives beside the artist/album keys in the versioned
  `domain/normalization.py`; the grouping summaries live in `domain/models.py`
  and the context aggregates in `application/library.py` (like `StreamTarget`);
  wiring the routes touched `db/repositories.py`, `api/schemas/tracks.py`
  imports, `api/client.ts`, `api/queryKeys.ts`, `app/{routes,Router}.tsx`, and
  the regenerated `frontend/src/api/generated.ts` beyond the listed files. `tabs`
  was added with `npx shadcn@latest add tabs` (new-york), not hand-written.

## Task 12 — Playlist ownership, reorder, and row actions

```toml
id = 12
type = "feature"
chunk = 10
deps = [11]
files = ["backend/src/chillify/application/playlists.py", "backend/src/chillify/api/routes/playlists.py", "frontend/src/features/playlists/{PlaylistPage,SortablePlaylistRow}.tsx", "frontend/src/features/library/AddToPlaylistMenu.tsx", "backend/tests/integration/test_playlists.py"]
[[criteria]]
text = "Profile isolation, duplicate rejection, contiguous reorder, and remove-without-delete survive restart."
layer = "integration"
[[criteria]]
text = "Playlist mutation conflicts return record_changed and restore confirmed UI order."
layer = "contract"
[[criteria]]
text = "Create profile-specific playlists, add/reorder/remove shared tracks, and play them in exact order."
layer = "e2e"
gate = 3
```

- **Done:** `6b90cc0` — evidence `specs/001-core/evidence/task-12.txt`
  The `[e2e@gate-3]` criterion is Task 15's demo gate and is not claimed here;
  the integration and contract criteria are demonstrated by tests that drive
  the real routes against migrated SQLite (`tests/integration/test_playlists.py`
  adds `TestPlaylistReorder`, `TestPlaylistRemoval`, and a reorder+removal
  restart case covering profile isolation, contiguous reorder, remove-without-
  delete, membership-mismatch rejection, and `record_changed` on stale reorder
  and removal; `tests/contract/test_openapi_contract.py` asserts the PUT order
  and DELETE track routes plus the reorder body shape) and by the S10 component
  tests in `tests/component/playlists.test.tsx` (reorder handles per row and
  their disabled single-track state, removal under the revision `If-Match`, and
  the conflict path that keeps the confirmed row and warns). `./scripts/verify.sh
  --fast` → all checks passed; full backend suite 412 passed; `vite build` green.
  Deviations from the predicted file set, all additive: `remove_track`/`reorder`
  and the contiguous `_renumber` helper live in `db/repositories.py` (the
  positions carry a `CHECK (>= 0)`, so renumber parks rows above the current
  maximum, not below zero, to avoid a mid-update `UNIQUE(playlist_id, position)`
  collision); the reorder request schema is in `api/schemas/playlists.py`; the
  DELETE/PUT routes and an `If-Match` parser are in `api/routes/playlists.py`;
  the two mutations are in `playlistQueries.ts`; regenerating `api/generated.ts`
  and wiring the new `AddToPlaylistMenu` into the existing `TrackTable.tsx`
  (which the task's file list does not name) removed the duplicated add-to-
  playlist block. `tests/setup.ts` gained a module-scope `ResizeObserver` stub
  because `@dnd-kit` reads it at import. Drag reconciliation is hand-rolled over
  the assigned `@dnd-kit/react@0.5.0` (no `@dnd-kit/helpers` is in the dependency
  plan); the real browser drag journey is the gate-3 concern, not a jsdom one.

## Task 13 — Session queue and resilient persistent player

```toml
id = 13
type = "feature"
chunk = 11
deps = [12]
files = ["frontend/src/features/player/{QueueDrawer,SortableQueueRow,playerStore,useAudioController,PersistentPlayer}.tsx", "frontend/src/components/ui/{scroll-area,sheet}.tsx", "frontend/tests/component/player-continuity.test.tsx"]
[[criteria]]
text = "Queue reducers apply all context/session rules and handle deleted or missing tracks deterministically."
layer = "unit"
[[criteria]]
text = "Reorder/remove upcoming session items, navigate primary routes, refresh, and switch profile without leaking session state."
layer = "e2e"
gate = 3
```

- **Done:** `c3233c5` — evidence `specs/001-core/evidence/task-13.txt`

  The unit criterion is met by `player-continuity.test.tsx`: reducer tests drive
  `reorderUpcoming` (upcoming-only; refuses the current/played region) and
  `removeFromQueue` (played-item index shift, current-track advance, unplayable-
  successor skip, and stop-and-clear when nothing playable remains), plus drawer
  tests for render/remove/clear and the deleted-track fallback. The e2e criterion
  is the Gate 3 journey and is deferred to Task 15. Real tree: `playerStore.ts`
  (not `.tsx`); `sheet.tsx` already existed; `scroll-area.tsx` added via
  `shadcn add` (unified `radix-ui`, no new dependency). `useAudioController.ts`
  was left unchanged — its existing audio-error path already advances past a
  current track whose file is gone, so no edit was needed for delete continuity.

## Task 14 — Complete visual states and accessibility

```toml
id = 14
type = "feature"
chunk = 12
deps = [13]
files = ["frontend/src/app/{Router,RouteErrorBoundary,PersistentShell}.tsx", "frontend/src/features/shared/{DataState,DegradedBanner}.tsx", "frontend/src/components/ui/{accordion,breadcrumb,navigation-menu}.tsx", "frontend/tests/e2e/accessibility.spec.ts", "frontend/tests/component/screen-states.test.tsx"]
[[criteria]]
text = "Component tests cover every enumerated screen state and modal focus return."
layer = "unit"
[[criteria]]
text = "Walk keyboard focus, reduced motion, and representative empty/loading/error/reconnecting states."
layer = "e2e"
gate = 3
```

- **Done:** `615a6b4` — evidence `specs/001-core/evidence/task-14.txt`
  - Added `DataState`/`ErrorState` and `DegradedBanner` (`features/shared`),
    `RouteErrorBoundary`, a skip-to-content link + degraded banner in
    `PersistentShell`, and the `breadcrumb`/`navigation-menu` Shadcn primitives.
  - Scope expanded (user-approved) to fix app-wide **modal focus return**: no
    dialog used `DialogTrigger`, so Radix restored focus to a null trigger and
    it fell to `body`. Added `useRestoreFocusOnClose` and wired it into all five
    dialogs (`PlaylistEditorDialog`, `TrackEditorDialog`, `DeleteTrackDialog`,
    `AddLinkDialog`, `YouTubeReviewDialog`) — the generated `dialog.tsx`
    primitive cannot be hand-edited per CONVENTIONS.
  - `[unit]` `tests/component/screen-states.test.tsx` (10 cases) covers every
    `DataState` branch, `DegradedBanner`, `RouteErrorBoundary` recovery, and
    modal focus return. `[e2e@gate-3]` `tests/e2e/accessibility.spec.ts` adds
    keyboard traversal, skip link, reduced motion, and axe scans — walked at
    Gate 3 (Task 15).
  - `./scripts/verify.sh --fast` green (build/audit + gate-3 e2e deferred to the
    Docker composition at Gate 3).

## Task 14a — Scenario-aware gate seed for the browse journey

Raised by the Task 15 preflight: the Gate 3 journey walks *Browse seeded Tracks, Artists, Albums, and Years including Unknown Year… and compare Queue order*, but the gate seed only wrote two tracks by the same artist, album, and year (Daft Punk / Discovery / 2001) with no way to express an Unknown Year — so step 1 of the journey was not walkable. The domain, library API, and browse screens already model `release_year: int | None` (Unknown Year last); the gap was fixture data only. This task makes seeding scenario-aware so the browse gate seeds variety while the earlier gates keep their exact two base tracks.

```toml
id = "14a"
type = "fix"
chunk = 12
deps = [14]
files = ["backend/src/chillify/gate_seed.py", "scripts/gate/seed.sh", "frontend/tests/e2e/global-setup.ts", "backend/tests/unit/test_gate_seed.py"]
[[criteria]]
text = "The `listening` scenario seeds several artists, albums, and distinct release years plus exactly one Unknown Year (release_year None) track, keeping the two base tracks."
layer = "unit"
[[criteria]]
text = "The default (and any unrecognized) scenario seeds exactly the two base tracks, so the Gate 1 and Gate 2 seeds are byte-identical."
layer = "unit"
[[criteria]]
text = "seed.sh forwards an optional scenario label and the e2e global setup forwards GATE_SCENARIO (default \"default\"), so a gate can request the listening library without changing the others."
layer = "integration"
```

- **Done:** `f8cee5f` — evidence `specs/001-core/evidence/task-14a.txt`
  - `SeedTrack.release_year` is now `int | None`. `BASE_TRACKS` is the two
    Daft Punk tracks the earlier gates seed; `LISTENING_TRACKS` adds Bonobo
    (Black Sands, 2010), Miles Davis (Kind of Blue, 1959), and a None-year
    Field Recordings track — three artists/albums/known-years plus one
    first-class Unknown Year.
  - `tracks_for_scenario` maps a label to a set, unknown → base, so a
    decorative chunk label seeds exactly the base tracks. `seed(...)` and the
    `--scenario` CLI flag thread it through; `seed.sh <name> [scenario]`
    forwards it; `global-setup.ts` forwards `GATE_SCENARIO` (default
    `"default"`), leaving Gate 1/2 seeds byte-identical.
  - `[unit]` `tests/unit/test_gate_seed.py` (5 cases): default is the two base
    tracks, unknown label falls back, listening keeps the base tracks and
    offers ≥3 artists/albums/years with exactly one Unknown Year.
  - `./scripts/verify.sh` green (EXIT=0).

## Task 14b — Wire the sidebar "Choose profile" button

Raised by the Task 15 (Gate 3) crystallization: the sidebar's "Choose profile" button rendered with no handler, and `clearProfile` — the only action that clears the browser-session queue before the shell is left (`AppProviders.tsx`) — was invoked from nowhere. Switching profiles was unreachable from the shell, so journey step 3 (*switch profile without leaking session state*) could not be walked or encoded. This task wires the button to `clearProfile`.

```toml
id = "14b"
type = "fix"
chunk = 12
deps = [14]
files = ["frontend/src/app/AppSidebar.tsx", "frontend/tests/component/choose-profile.test.tsx"]
[[criteria]]
text = "The sidebar 'Choose profile' button invokes clearProfile, which clears the session queue and drops the stored profile so RequireProfile returns to the chooser."
layer = "unit"
```

- **Done:** `2d24cf2` — evidence `specs/001-core/evidence/task-14b.txt`
  - `AppSidebar.tsx` now reads `clearProfile` from `useActiveProfile` and calls
    it from the button's `onClick`. `clearProfile` already clears the session
    queue, removes the stored profile, and invalidates playlist queries; with
    the profile null, `RequireProfile` redirects to `/profiles`.
  - `[unit]` `tests/component/choose-profile.test.tsx` renders the sidebar with
    a spy session and asserts the button invokes `clearProfile` exactly once, so
    the wiring cannot silently regress.
  - `./scripts/verify.sh` green (EXIT=0).

## Task 15 — DEMO GATE 3: browse, organize, and listen

```toml
id = 15
type = "gate"
chunk = 12
deps = [11, 12, 13, 14]
files = ["frontend/tests/e2e/gate-3.spec.ts", "specs/001-core/evidence/task-15.txt"]
[[criteria]]
text = "The Gate 3 browse/listen journey, including invalid-input validation and keyboard accessibility, is encoded and green in frontend/tests/e2e/gate-3.spec.ts."
layer = "e2e"
gate = 3
[gate]
n = 3
release = false
launch = "docker compose --env-file .gate/gate-3/.env up --build -d"
seed = "./scripts/gate/seed.sh gate-3 listening"
unglamorous = "Invalid input: submit invalid profile/playlist metadata and observe preserved input, inline validation, and no durable mutation."
[[gate.journey]]
step = "Browse seeded Tracks, Artists, Albums, and Years including Unknown Year; play each and compare Queue order."
task = 11
[[gate.journey]]
step = "Create profile-specific playlists, add/reorder/remove shared tracks, and play them in exact order."
task = 12
[[gate.journey]]
step = "Reorder/remove upcoming session items, navigate primary routes, refresh, and switch profile without leaking session state."
task = 13
[[gate.journey]]
step = "Walk keyboard focus, reduced motion, and representative empty/loading/error/reconnecting states."
task = 14
[[gate.journey]]
step = "Invalid input: submit invalid profile/playlist metadata and observe preserved input, inline validation, and no durable mutation."
task = 14
```

Preflight: `./scripts/gate/prepare.sh gate-3 listening` must create only `.gate/gate-3/` roots and the isolated prefix. Record the human walkthrough result in the evidence file.

- **Done:** `01153c1` — evidence `specs/001-core/evidence/task-15.txt`
  - **GATE 3 WALKED — PASS** (2026-07-23, user: "everything observed, check
    as pass"). Preflight recreated the gate composition, seeded the
    `listening` library (6 tracks / 4 artists / 4 albums / years 1959, 2001,
    2010, Unknown), and confirmed every journey entry point reachable before
    the walkthrough.
  - Two preflight findings became head-of-queue fix tasks, both landed before
    the gate: [[task-14a]] scenario-aware seed (browse needed variety and an
    Unknown Year) and [[task-14b]] wiring the dead "Choose profile" button (the
    profile-switch no-leak guarantee was unreachable). See Task 14a/14b.
  - Crystallization: `frontend/tests/e2e/gate-3.spec.ts` encodes the full
    journey (browse + per-context queue order incl. Unknown Year, profile
    playlists add/remove/play-in-order, session prune, refresh + profile-switch
    no-leak, invalid profile/playlist input) and is **green**:
    `GATE_NAME=gate-3 GATE_SCENARIO=listening npx playwright test gate-3` →
    `1 passed`. `./scripts/verify.sh` green (EXIT=0).

## Task 16 — Production provider implementations

```toml
id = 16
type = "feature"
chunk = 13
deps = [15]
fake_of = "all external provider/network systems"
files = ["backend/src/chillify/infrastructure/providers/{deezer,lastfm,ytdlp,spotdl,artwork_http,registry}.py", "backend/tests/contract/{test_deezer_contract,test_lastfm_contract,test_ytdlp_contract,test_spotdl_contract,test_artwork_contract}.py"]
[[criteria]]
text = "Sanitized success/error fixtures pass one shared protocol suite against every fixture and production adapter."
layer = "contract"
[[criteria]]
text = "All real adapters use the one proxy policy without direct fallback, and metadata precedence/Last.fm gap merge are deterministic."
layer = "integration"
```

- **Done:** `d182276` — evidence `specs/001-core/evidence/task-16.txt`
  Scoped to the adapter layer per a user decision recorded this turn: the
  worker never calls the Last.fm enricher nor applies the
  review→provider→Last.fm→Unknown pipeline (the `ENRICHING` phase is dead
  code), and Task 16's file list is provider adapters + contract tests only.
  Rather than silently expand into `downloads.py`/`composition.py` or silently
  drop the behaviour, the enricher/precedence *wiring* is left as a flagged
  follow-up; this task delivers the production adapters and holds them to the
  same contracts as the fixtures. See the `[integration]` criterion below —
  interpreted at the adapter layer (deterministic gap merge + within-provider
  field precedence + one proxy policy), which is what the file set can carry.
  - Delivered: production `DeezerDiscoveryProvider` and `LastfmEnricher`
    already existed and route through `OutboundHttp`; added production
    `YouTubeInspector`/`YtDlpAcquisitionProvider` (injected yt-dlp Python API,
    `bestaudio`→FFmpeg mp3, real progress hooks, cancellation, and the
    `ytsearch1:` weak-match guard on title + duration tolerance), production
    `SpotdlInspector`/`SpotdlAcquisitionProvider` (isolated argument-vector CLI
    in its own process group, injected runner, saved proxy passed only to the
    child, exit-zero-is-insufficient MP3 validation), and the new
    `HttpArtworkFetcher` (one proxy policy, ≤3 redirects, 10 MiB cap,
    `normalize_cover`). `registry.build_registry` now binds the production
    adapters in production mode and the fixtures in gate mode as two
    import-isolated branches; production binds `artwork['url']`.
  - `[contract]`: the production adapters join the existing shared suites —
    `test_ytdlp_contract`/`test_spotdl_contract` gained a `production` inspector
    factory (injected doubles over the same recorded fixtures) plus production
    acquisition + SpotDL CLI-flag suites; new `test_deezer_contract`,
    `test_lastfm_contract`, `test_artwork_contract` drive the HTTP adapters
    under respx with sanitized success/error payloads.
  - `[integration]`: each real HTTP adapter's dedicated contract file asserts
    the saved proxy reaches every client with no direct-fallback (joining the
    Task 8 `test_outbound_policy` proof), and `test_lastfm_contract` pins the
    deterministic gap merge (only requested-missing fields returned, identical
    output for identical input, non-fatal on every failure).
  - Additive files beyond the predicted list, both noted: `providers/mp3.py`
    (one shared `single_valid_mp3` validator so the two audio adapters cannot
    disagree, mirroring the shared `deezer_wire` rationale). The Last.fm
    enricher and a Last.fm cover fetcher are deliberately **not** bound in the
    registry: both need the DB-stored API key, which the Settings-only
    `build_registry` cannot read — the same reason the enricher wiring is the
    flagged follow-up above.
  - `./scripts/verify.sh` → all checks passed (EXIT=0); full backend suite 466
    passed.

## Task 17 — Security, recovery, and storage hardening

```toml
id = 17
type = "feature"
chunk = 14
deps = [16]
files = ["backend/src/chillify/infrastructure/security/outbound.py", "backend/src/chillify/infrastructure/media/recovery.py", "backend/src/chillify/api/middleware.py", "deploy/nginx.conf", "scripts/verify/{security,storage,persistence}.sh", "backend/tests/integration/{test_ssrf,test_idempotency,test_concurrency}.py"]
[[criteria]]
text = "Private redirects, oversized art, symlink escapes, stale revisions, and reused idempotency keys fail with documented codes."
layer = "integration"
[[criteria]]
text = "All mutation crash points recover with zero mismatches."
layer = "integration"
[[criteria]]
text = "Security/storage scripts reject non-disposable and container-layer targets with nonzero exit status."
layer = "contract"
```

- **Done:** `190aa3d` — evidence `specs/001-core/evidence/task-17.txt`

## Task 18 — NFR and cross-browser verification

```toml
id = 18
type = "feature"
chunk = 15
deps = [17]
files = ["scripts/{verify,verify/nfr}.sh", "frontend/playwright.config.ts", "frontend/tests/e2e/{nfr,firefox-smoke,degraded,fixtures}.ts", "backend/tests/integration/test_secret_redaction.py"]
produces = ["./scripts/verify.sh"]
[[criteria]]
text = "The canonical verification command fails for any lint/type/test/build/contract/canary failure and passes from a clean checkout with gate prerequisites."
layer = "integration"
[[criteria]]
text = "The verify contract test calls ./scripts/verify.sh with a disposable environment and asserts its fail-closed aggregate result."
layer = "contract"
[[criteria]]
text = "Run named NFR evidence, Chromium/Firefox smoke, and zero-critical/serious axe verification."
layer = "e2e"
gate = 4
```

- **Done:** `4aa3210` — evidence `specs/001-core/evidence/task-18.txt`
  - Resolved the pre-existing frontend audit red: `react-router` 8.2.0 →
    8.3.0 (in-range minor, the only advisory reaching the shipped tree) plus
    narrow `overrides` for `brace-expansion`/`@hono/node-server`, lockfile
    regenerated with the web image's own npm. `npm audit --audit-level=high`
    now 0 vulnerabilities. Recorded in ARCHITECTURE's decision log.
  - `scripts/verify/nfr.sh` + `frontend/tests/e2e/{nfr,firefox-smoke,
    degraded,fixtures}.spec.ts` (`.spec.ts`, not bare `.ts`, so Playwright's
    default `testMatch` actually discovers them; `fixtures.ts` is the one
    shared, non-spec helper module) provide named NFR-1/2/3/5/9/10 evidence
    against a disposable "gate-4" stack — 7/7 green, Chromium and Firefox
    both exercised live.
  - `[contract]` `backend/tests/contract/test_verify_aggregate.py` pins
    `./scripts/verify.sh`'s fail-closed aggregate behavior via a disposable
    git worktree (clean passes; one injected failure fails closed and keeps
    running every later step; clean again once removed) — 4/4 passing.
  - Running the suite against the *real* gate composition surfaced two
    regressions invisible to unit/integration tests: nginx forwarded `Host`
    via `$host` (drops a non-default port), breaking Task 17's
    `MutationGuardMiddleware` same-origin check on every gate; and
    `RedactingFilter` never redacted `record.exc_info`, so a secret folded
    into a raw exception message could reach real stdout through a Rich
    traceback. Both fixed (`deploy/nginx.conf`, `infrastructure/logging/
    redaction.py`); the latter covered by `backend/tests/integration/
    test_secret_redaction.py` (4/4 passing).
  - **Not fixed, recorded as a finding:** the seek/volume `Slider`'s
    accessible name never reaches the Radix thumb carrying `role="slider"`
    (axe: `aria-input-field-name`, serious, on every screen — reproduces on
    a clean checkout with zero Task 18 changes). A correct fix touches
    either a generated primitive CONVENTIONS reserves for the Shadcn CLI or
    an earlier chunk's component, neither in this task's file list. `nfr.sh`
    does not bundle `accessibility.spec.ts` so this task's own result does
    not depend on it; see ARCHITECTURE's decision log for the full writeup.
  - `./scripts/verify.sh` (full, not `--fast`) green end to end.
  - **Follow-up (2026-07-26, scoped fix, not part of the Done mark above):**
    the recorded Slider `aria-input-field-name` (serious) finding is
    resolved in `1ddb6af` — `frontend/src/components/ui/slider.tsx` gained
    an optional `thumbLabels` prop forwarded per-thumb, and
    `frontend/src/features/player/PersistentPlayer.tsx` passes
    `thumbLabels={["Seek"]}`/`["Volume"]` at its two Slider call sites. Live
    axe reruns against a disposable gate stack confirm the finding
    reproduces on the unmodified checkout and is absent once the fix is
    applied. See ARCHITECTURE's 2026-07-26 decision-log entry and evidence
    `specs/001-core/evidence/task-18a-slider-a11y.txt`.
  - **Follow-up (2026-07-26, scoped fix, not part of the Done mark above):**
    the two remaining recorded findings — the destructive `Badge`'s
    `color-contrast` (serious, `#ffffff` on `#ff6b73`, 2.76:1) and the
    Playwright strict-mode "Create Playlist" locator collision on the S9
    empty-playlist state — are both resolved in `43900c3`.
    `frontend/src/components/ui/badge.tsx`'s `destructive` variant now uses
    the `text-destructive-foreground` token (7.23:1) instead of raw
    `text-white`; `frontend/tests/e2e/accessibility.spec.ts` narrows its
    `create` locator with `.first()`, matching the intentional header +
    empty-state duplicate UX.md's S9 section specifies and the identical
    disambiguation already used by `gate-3.spec.ts`/`firefox-smoke.spec.ts`.
    Live axe reruns (including a forced-redis-down run to actually render the
    destructive Badge) confirm both findings reproduce on the unmodified
    checkout and are absent, 6/6 passing with zero critical/serious
    violations, once the fix is applied. See ARCHITECTURE's 2026-07-26
    "Both remaining Task 18 findings resolved" decision-log entry and
    evidence `specs/001-core/evidence/task-18b-badge-locator.txt`.

## Task 19 — Production-composition proof

```toml
id = 19
type = "proof"
chunk = 16
deps = [18]
files = ["scripts/production_canary.sh", "scripts/gate/prepare.sh", "backend/src/chillify/composition.py", "backend/tests/integration/test_production_composition.py", "frontend/tests/e2e/production-composition.spec.ts", "README.md"]
produces = ["./scripts/production_canary.sh --env-file .gate/release/.env --no-live-success"]
[[criteria]]
text = "Release API/worker composition resolves real provider/tool/Redis/SQLite/media implementations and reaches ready/degraded states on disposable roots."
layer = "integration"
[[criteria]]
text = "The production canary refuses household roots, reports each real adapter/tool, and treats network failure as a clear canary failure without fallback."
layer = "contract"
[[criteria]]
text = "Prove the unchanged production composition resolves real adapter classes before deterministic fixtures are used."
layer = "e2e"
gate = 4
```

- **Done:** `b4111db` — evidence `specs/001-core/evidence/task-19.txt`

## Task 20 — RELEASE GATE 4: v1 exit bar

```toml
id = 20
type = "gate"
chunk = 16
deps = [1, 2, 3, 4, 6, 7, 8, 9, 11, 12, 13, 14, 16, 17, 18, 19]
files = ["frontend/tests/e2e/gate-4-release.spec.ts", "specs/001-core/evidence/task-20.txt"]
[[criteria]]
text = "The release kernel journey and its restart/offline/error-state coverage are encoded and green in frontend/tests/e2e/gate-4-release.spec.ts."
layer = "e2e"
gate = 4
[gate]
n = 4
release = true
launch = "docker compose --env-file .gate/release/.env up --build -d"
seed = "./scripts/gate/seed.sh release kernel-500"
unglamorous = "Restart: recreate release containers on .gate/release mounts and verify durable data survives while the browser playback session is empty."
[[gate.journey]]
step = "Select Household, search locally without a provider request, search Deezer explicitly, and download one distinct result through truthful phases."
task = 3
[[gate.journey]]
step = "Close/reopen the browser and verify durable job state and playable mounted MP3."
task = 3
[[gate.journey]]
step = "Correct metadata/art atomically and verify database, ID3, artwork, and path agreement."
task = 4
[[gate.journey]]
step = "Create a profile playlist, add/play the track, and navigate without interruption."
task = 13
[[gate.journey]]
step = "Validate direct links, cancellation/retry/restart, duplicates, proxy fail-closed, Redis recovery, contexts, deletion, and documented error states."
task = 17
[[gate.journey]]
step = "Run named NFR evidence, Chromium/Firefox smoke, and zero-critical/serious axe verification."
task = 18
[[gate.journey]]
step = "Prove the unchanged production composition resolves real adapter classes before deterministic fixtures are used."
task = 19
[[gate.journey]]
step = "Restart: recreate release containers on .gate/release mounts and verify durable data survives while the browser playback session is empty."
task = 19
```

Preflight: run `./scripts/gate/prepare.sh release kernel-500`, then `./scripts/production_canary.sh --env-file .gate/release/.env --no-live-success`; both must fail closed unless paths are under `.gate/release/` and the Redis prefix is `chillify:gate:release:`. The human walkthrough result and named NFR evidence are the completion artifact.

- **Preflight correction:** `kernel-500` is a seed *scenario*, not a prepare
  mode. The runnable form is `./scripts/gate/prepare.sh release release`
  followed by `./scripts/gate/seed.sh release kernel-500`. Recorded in
  `specs/001-core/evidence/task-20-preflight.txt`.
- **GATE BLOCKED → cleared for walkthrough.** The first preflight passed but
  the walkthrough failed journey step 1: no download was possible. Three
  defects found and fixed, each with live evidence:
  - `580838e` — production-mode `REDIS_URL` pointed at `127.0.0.1`, which is
    the container itself; `compose.yaml` has no redis service. Every
    containerized launch came up with acquisition degraded.
  - `2e87f54` — Task 20 required the production composition *and* seeded data,
    which two containment layers made mutually exclusive. Added a disposable
    `release` environment; `is_gate` semantics unchanged, so real adapters
    still bind.
  - `6552efd` — the configured proxy was never applied to any provider call;
    `proxy_url` was never assigned anywhere. Only the Settings proxy *test*
    used a real proxy, so it reported success while all traffic went direct.
  - `8dcda66` — SpotDL passed the proxy on argv (leaking it to `ps`, and not
    covering its internal `requests` traffic) instead of exporting it to the
    child as ARCHITECTURE specifies.
- **Deferred, agreed with the operator, not silently dropped:**
  - `production_canary.sh` probes live reachability from the *host*, which
    inherits the host's `http_proxy`. It reported `live reachability ok` while
    the containers had no working provider path, so Task 19's "treats network
    failure as a clear canary failure" criterion is not really satisfied. The
    probe must run inside the api container.
  - SpotDL inspection takes 122–140s through a real proxy; `8dcda66` raised the
    inspect timeout to 180s and nginx `proxy_read_timeout` to 200s to make it
    work. The latency itself is unexplained and deserves its own investigation.

### GATE BLOCKED — walkthrough result, 2026-07-27

The operator walked the journey. Everything was observed and correct **except
step 1's Spotify path**: Add Music failed repeatedly with "That link could not be
inspected." YouTube and Deezer worked.

Root cause established live, not inferred: `spotdl save` takes **145–183s**
through the operator's proxy — per-request latency, not any single spotdl feature
(disabling its lyrics providers did not reliably help) — which straddles the 180s
inspect timeout `8dcda66` had raised. The measured breakdown and the failing/passing
runs are in `specs/001-core/evidence/task-20-proxy-wiring.txt` and
`task-20-spotdl-proxy.txt`.

Per the spawn route this is not wedged into this queue: it needs a fast inspection
path, an operator-configurable mode and timeouts, honest inspection feedback, and
the Last.fm enrichment call site that ARCHITECTURE specifies but which was never
wired up. That is a new contract and a second subsystem, so it is a scoped child
cycle: **`specs/002-spotify-inspection/`** (Phases 1–4 complete, TASKS.md stamped
`ready`, tasks 21–30, gates 5 and 6).

**This gate stays BLOCKED and is not Done.** Its preflight re-runs only after cycle
002 completes. Both deferred items above are carried into that cycle's Task 29 —
the canary fix because 002's own release gate cannot depend on a check that
returned a false PASS, and the stopgap revert so the 180s/200s values do not
quietly become permanent.
