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

## Task 9 — Mutation recovery and permanent deletion

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
