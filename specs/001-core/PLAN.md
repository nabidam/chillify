---
status: gate-passed
---

# Chillify Core Implementation Plan

## Planning rules

- There are no `SPIKE:` markers in `ARCHITECTURE.md`; implementation begins with the walking skeleton.
- Each chunk is a vertical, reviewable increment with no more than roughly 300 lines of hand-authored production code. Generated Shadcn source, OpenAPI types, migration output, fixtures, and tests remain reviewable but are not used to hide hand-authored behavior.
- The only gate fakes replace external provider/network systems. Browser, nginx, FastAPI, SQLite, mounted files, Celery, the operator Redis connection, SSE, media streaming, and the production composition root are real at every gate.
- Fixture adapters are injected through the same production composition root. Startup refuses fixture mode unless `CHILLIFY_ENV=gate`, both storage roots resolve beneath the repository `.gate/` directory, and the Redis prefix begins with `chillify:gate:`. This fails closed against household state.
- A changed architecture interface blocks dependent chunks until `ARCHITECTURE.md`, this plan, and affected acceptance criteria are synchronized.

## Milestone 1 — Walking skeleton

The milestone proves the complete kernel journey with deliberately plain UI and verified external-system fixtures. No internal repository, queue, filesystem, or browser behavior is faked.

## Chunk 1 — Bootable production composition and household shell

**Files touched**

- `compose.yaml`
- `.env.example`
- `.gitignore`
- `biome.json`
- `deploy/docker/backend.Dockerfile`
- `deploy/docker/web.Dockerfile`
- `deploy/nginx.conf`
- `backend/pyproject.toml`
- `backend/uv.lock`
- `backend/alembic.ini`
- `backend/src/chillify/config.py`
- `backend/src/chillify/composition.py`
- `backend/src/chillify/logging/setup.py`
- `backend/src/chillify/logging/redaction.py`
- `backend/src/chillify/api/main.py`
- `backend/src/chillify/api/routes/system.py`
- `backend/src/chillify/worker/main.py`
- `backend/src/chillify/infrastructure/db/engine.py`
- `backend/migrations/env.py`
- `backend/migrations/script.py.mako`
- `backend/migrations/versions/0001_core.py`
- `frontend/package.json`
- `frontend/package-lock.json`
- `frontend/components.json`
- `frontend/index.html`
- `frontend/tsconfig.app.json`
- `frontend/tsconfig.json`
- `frontend/tsconfig.node.json`
- `frontend/vite.config.ts`
- `frontend/vitest.config.ts`
- `frontend/src/main.tsx`
- `frontend/src/app/AppSidebar.tsx`
- `frontend/src/app/AppProviders.tsx`
- `frontend/src/app/PersistentShell.tsx`
- `frontend/src/app/Router.tsx`
- `frontend/src/app/TopBar.tsx`
- `frontend/src/components/ui/badge.tsx`
- `frontend/src/components/ui/button.tsx`
- `frontend/src/components/ui/sidebar.tsx`
- `frontend/src/components/ui/sonner.tsx`
- `frontend/src/components/ui/tooltip.tsx`
- `frontend/src/lib/cn.ts`
- `frontend/public/chillify-mark.svg`
- `frontend/src/styles/tokens.css`
- `frontend/src/styles/globals.css`

**Requirements**

- Pin the approved runtime/dependency versions and create the production `web`, `api`, and serial `worker` composition without a Redis service.
- Validate all environment, UID/GID, secret-key, Redis-prefix, and mounted-path rules before migration.
- Apply the complete architecture DDL, configure SQLite WAL/full sync, and expose `/api/v1/system/status`.
- Configure standard Python logging through Rich stdout with request/service context and secret redaction.
- Initialize Shadcn `new-york-v4` with Radix and emit the DESIGN token source; mount a minimal persistent shell with route outlet and bottom-player slot.
- Add health checks that distinguish readiness from provider/Redis degradation.

**Acceptance**

- `[integration]` The production Compose command starts nginx/API/worker against disposable mounted roots, applies the migration, and `/api/v1/system/status` reports path/tool/Redis state.
- `[unit]` Invalid roots, UID/GID, secret key, or fixture-mode safety conditions fail startup with named errors before migration.
- `[unit]` Rich log records include service/request context and redact sentinel proxy/Last.fm secrets.
- `[contract]` Generated OpenAPI exposes the documented system-status error/success envelope.

**Do not**

- Do not add auth, a Compose Redis service, provider calls, custom UI primitives, or business feature shortcuts.

## Chunk 2 — Profile, local library, stream, and persistent playback slice

**Files touched**

- `backend/src/chillify/domain/models.py`
- `backend/src/chillify/domain/normalization.py`
- `backend/src/chillify/domain/ordering.py`
- `backend/src/chillify/infrastructure/db/models.py`
- `backend/src/chillify/infrastructure/db/repositories.py`
- `backend/src/chillify/api/schemas/profiles.py`
- `backend/src/chillify/api/schemas/tracks.py`
- `backend/src/chillify/api/routes/profiles.py`
- `backend/src/chillify/api/routes/library.py`
- `backend/src/chillify/api/routes/tracks.py`
- `frontend/src/api/client.ts`
- `frontend/src/api/generated.ts`
- `frontend/src/features/profiles/ProfileChooser.tsx`
- `frontend/src/features/library/LibraryPage.tsx`
- `frontend/src/features/library/TrackTable.tsx`
- `frontend/src/features/player/playerStore.ts`
- `frontend/src/features/player/PersistentPlayer.tsx`
- `frontend/src/features/player/useAudioController.ts`
- `frontend/src/components/ui/aspect-ratio.tsx`
- `frontend/src/components/ui/dropdown-menu.tsx`
- `frontend/src/components/ui/empty.tsx`
- `frontend/src/components/ui/skeleton.tsx`
- `frontend/src/components/ui/slider.tsx`
- `frontend/src/components/ui/table.tsx`

**Requirements**

- Implement name-only profile list/create and the shared local track query over the architecture repositories.
- Seed one valid mounted MP3 only through the gate fixture command; stream it by track ID with byte ranges, ETag, and path-containment checks.
- Mount one browser audio element above the route outlet and implement play/pause, seek, volume, previous/next, and current identity using Shadcn controls.
- Keep profile selection/session player state browser-owned and stop/clear playback on profile switch.

**Acceptance**

- `[integration]` A created profile and seeded track survive API restart and the MP3 endpoint returns correct full and byte-range responses.
- `[unit]` Normalization, year validation, context ordering, and path containment match the architecture invariants.
- `[e2e@gate-1]` Create/select “Household”, play the seeded local track, navigate away from Library, and observe uninterrupted playback.
- `[contract]` Profile, library, track, and stream endpoints match generated frontend types.

**Do not**

- Do not import arbitrary host folders, persist the browser queue, or add shuffle/repeat.

## Chunk 3 — Local-first discovery through a real durable queue

**Files touched**

- `backend/src/chillify/domain/jobs.py`
- `backend/src/chillify/domain/protocols.py`
- `backend/src/chillify/application/search.py`
- `backend/src/chillify/application/downloads.py`
- `backend/src/chillify/infrastructure/providers/registry.py`
- `backend/src/chillify/infrastructure/providers/fixtures.py`
- `backend/src/chillify/infrastructure/queue/celery_app.py`
- `backend/src/chillify/infrastructure/queue/tasks.py`
- `backend/src/chillify/infrastructure/media/storage.py`
- `backend/src/chillify/api/schemas/downloads.py`
- `backend/src/chillify/api/routes/search.py`
- `backend/src/chillify/api/routes/downloads.py`
- `backend/src/chillify/api/routes/events.py`
- `frontend/src/features/search/SearchPage.tsx`
- `frontend/src/features/search/ResultCards.tsx`
- `frontend/src/features/downloads/DownloadsPage.tsx`
- `frontend/src/features/downloads/GlobalJobIndicator.tsx`
- `frontend/src/app/EventBridge.tsx`
- `frontend/src/components/ui/alert.tsx`
- `frontend/src/components/ui/field.tsx`
- `frontend/src/components/ui/input.tsx`
- `frontend/src/components/ui/progress.tsx`
- `frontend/src/components/ui/separator.tsx`
- `backend/tests/fixtures/providers/deezer_search.json`
- `backend/tests/fixtures/media/gate-tone.mp3`

**Requirements**

- Return local results without network access; call the fixture Deezer adapter only after the explicit online action and label normalized results non-playable.
- Persist a job/event before Celery publication, pass only job ID through Redis, execute one worker task at a time, and publish SSE job transitions.
- Run the real workspace, MP3 validation, mounted-file publish, track/source insert, and library invalidation path; only the external acquisition call uses a contract-verified fixture.
- Reconnect SSE by durable job-event ID and poll when disconnected.

**Acceptance**

- `[integration]` Closing the browser does not stop the job; reopening shows durable state and the completed mounted track.
- `[integration]` Three queued fixture jobs never run more than one acquisition phase concurrently.
- `[contract]` Fixture Deezer/acquisition adapters pass the same protocol suite used by production adapters.
- `[e2e@gate-1]` A local query emits no provider call; explicit Deezer search shows separate non-playable results and Download produces visible queued-to-completed phases.

**Do not**

- Do not call live providers, invent progress, pass secrets through Redis, or treat Celery state as authoritative.

## Chunk 4 — Kernel correction, playlist, and restart persistence

**Files touched**

- `backend/src/chillify/application/artwork.py`
- `backend/src/chillify/application/metadata.py`
- `backend/src/chillify/application/playlists.py`
- `backend/src/chillify/infrastructure/media/artwork.py`
- `backend/src/chillify/infrastructure/media/tags.py`
- `backend/src/chillify/infrastructure/media/mutations.py`
- `backend/src/chillify/api/schemas/artwork.py`
- `backend/src/chillify/api/schemas/playlists.py`
- `backend/src/chillify/api/routes/artwork.py`
- `backend/src/chillify/api/routes/playlists.py`
- `frontend/src/features/metadata/TrackEditorDialog.tsx`
- `frontend/src/features/metadata/ArtworkPicker.tsx`
- `frontend/src/features/playlists/PlaylistsPage.tsx`
- `frontend/src/features/playlists/PlaylistPage.tsx`
- `frontend/src/features/playlists/PlaylistEditorDialog.tsx`
- `frontend/src/features/library/TrackRow.tsx`
- `scripts/gate/prepare.sh`
- `scripts/gate/seed.sh`
- `scripts/gate/cleanup.sh`
- `backend/src/chillify/gate_seed.py`
- `frontend/src/components/ui/card.tsx`
- `frontend/src/components/ui/dialog.tsx`

**Requirements**

- Stage uploaded artwork, then make one optimistic-revision edit synchronize display metadata, ID3 tags/art, organized path, SQLite, and cleanup through the mutation journal.
- Create/rename profile-specific playlists, add a local track once, fetch manual order, and play that context in the browser queue.
- Provide gate preparation that creates disposable roots/config and isolated Redis prefix, seeds contract fixtures, and refuses non-`.gate/` roots.
- Ensure container recreation preserves profile, corrected track, job history, and playlist while playback session remains empty.

**Acceptance**

- `[integration]` A metadata/art edit changes the MP3 tags, mounted path, artwork, and database together; restart preserves only the new version.
- `[integration]` Playlist name uniqueness and track uniqueness are enforced per profile.
- `[e2e@gate-1]` Correct the downloaded track and cover, create a personal playlist, add/play the track, navigate, recreate containers, and observe durable library/playlist data with an empty playback session.
- `[contract]` Artwork-stage, atomic track edit, and playlist endpoints match the architecture contract.

**Do not**

- Do not split metadata and artwork into separate final mutations, expose filesystem paths, or persist playback state.

## DEMO GATE 1 — Walking skeleton

**Runnability preconditions**

- Prepare: `./scripts/gate/prepare.sh gate-1 kernel`.
- Launch: `docker compose --env-file .gate/gate-1/.env up --build -d`.
- Seed: `./scripts/gate/seed.sh gate-1 kernel` after API readiness; it invokes the guarded backend seed entry through the running production container.
- Composition: the production `compose.yaml` and production API/worker composition root; only provider/network protocols resolve to checked fixture adapters.
- Disposable safety: both mounts are beneath `.gate/gate-1/`; Redis uses the gate-only prefix; startup rejects any other fixture target.
- Serving chunks: boot/status/persistent shell (Chunk 1); profile/local playback (Chunk 2); search/download/job state (Chunk 3); correction/playlist/restart (Chunk 4).

**Journey to walk**

1. Create/select Household and open the shared library.
2. Search locally and confirm no provider activity.
3. Explicitly search Deezer and see separate results with Download but no Play.
4. Download one result and watch queued through completed after closing/reopening the browser.
5. Play the new local track, correct metadata/art atomically, and verify its new organized identity.
6. Create a playlist, add/play the track, and navigate S2, S3, S9, and S11 without playback reset.
7. Recreate the production containers with the same disposable mounts; verify track, correction, profile, playlist, and job history persist while the session queue does not.

**Observe**

- Real SQLite, mounted MP3/ID3/art, Redis/Celery, SSE, nginx range streaming, and browser audio are exercised.
- Local and internet results never intermix; server job state is truthful; Rich output contains no fixture sentinel secret.
- Record the walked journey as `frontend/tests/e2e/gate-1.spec.ts`.

## Milestone 2 — Acquisition safety and recovery

## Chunk 5 — Direct-link inspection and reviewed YouTube acquisition

**Files touched**

- `backend/src/chillify/application/links.py`
- `backend/src/chillify/api/schemas/links.py`
- `backend/src/chillify/api/routes/links.py`
- `backend/src/chillify/infrastructure/providers/ytdlp.py`
- `backend/src/chillify/infrastructure/providers/spotdl.py`
- `frontend/src/features/acquisition/AddLinkDialog.tsx`
- `frontend/src/features/acquisition/YouTubeReviewDialog.tsx`
- `frontend/src/components/ui/label.tsx`
- `backend/tests/contract/test_ytdlp_contract.py`
- `backend/tests/contract/test_spotdl_contract.py`

**Requirements**

- Detect only one Spotify track or one YouTube video; reject album/playlist/channel/bulk entities before job creation.
- Inspect YouTube through the saved proxy, present editable required metadata, and reuse artwork-stage inputs.
- Queue reviewed values immutably and ensure submitted metadata wins over provider/Last.fm gaps.
- Keep subprocess calls argument-vector/process-group based with bounded redacted diagnostics.

**Acceptance**

- `[contract]` yt-dlp and SpotDL fixture adapters normalize the documented candidates/errors and share the production protocol suite.
- `[unit]` Unsupported/malformed/bulk links create no durable job.
- `[e2e@gate-2]` A YouTube video opens review, blocks blank title/artist, accepts corrected metadata/art, and completes as one playable MP3; Spotify track succeeds while bulk links fail clearly.

**Do not**

- Do not accept arbitrary extractor sites, albums/playlists, direct Deezer audio, or raw provider output.

## Chunk 6 — Queue cancellation, retry, restart, and duplicates

**Files touched**

- `backend/src/chillify/application/reconciliation.py`
- `backend/src/chillify/infrastructure/queue/reconciliation.py`
- `backend/src/chillify/infrastructure/queue/cancellation.py`
- `backend/src/chillify/infrastructure/media/workspaces.py`
- `frontend/src/features/downloads/DownloadRow.tsx`
- `backend/tests/integration/test_queue_recovery.py`
- `backend/tests/integration/test_duplicates.py`

**Requirements**

- Implement DB leases/heartbeats, startup/Redis reconnection reconciliation, oldest-first redispatch, and restarted display state.
- Cancel queued/running work cooperatively, terminate process groups, remove task workspaces, and advance the serial queue.
- Retry as a new linked job and preserve chronology.
- Reject duplicates in exact source → ISRC → normalized artist/title order both before queueing and at publication.

**Acceptance**

- `[integration]` Killing worker mid-download returns the job to queued/restarted and completes once without duplicate files.
- `[integration]` Cancel removes temporary files and advances; retry creates a linked attempt.
- `[integration]` Every duplicate identity race produces one track/file and a link to it.
- `[e2e@gate-2]` Cancel, retry, worker restart, and duplicate resubmission show truthful global outcomes.

**Do not**

- Do not resume partial downloads, hide attempts, or use fuzzy matching as an identity decision.

## Chunk 7 — Proxy-first settings and degraded local operation

**Files touched**

- `backend/src/chillify/application/settings.py`
- `backend/src/chillify/infrastructure/security/secrets.py`
- `backend/src/chillify/infrastructure/security/outbound.py`
- `backend/src/chillify/infrastructure/providers/deezer.py`
- `backend/src/chillify/infrastructure/providers/lastfm.py`
- `backend/src/chillify/api/schemas/settings.py`
- `backend/src/chillify/api/routes/settings.py`
- `frontend/src/features/settings/SettingsPage.tsx`
- `frontend/src/features/settings/ProviderCard.tsx`
- `frontend/src/features/settings/StorageDiagnostics.tsx`
- `frontend/src/components/ui/select.tsx`
- `frontend/src/components/ui/switch.tsx`
- `backend/tests/integration/test_proxy_fail_closed.py`

**Requirements**

- Put global proxy first; validate, encrypt, mask, save/test, and route Deezer, Last.fm, SpotDL, yt-dlp, and artwork through one fail-closed policy.
- Expose seeded provider enabled states and isolated health results for Redis, storage, FFmpeg, SpotDL, and yt-dlp.
- Disable acquisition/retry during Redis loss while all local read/play/playlist behavior remains usable; reconnect without web restart.
- Treat Last.fm absence/failure as an optional warning only.

**Acceptance**

- `[integration]` Invalid proxy traffic inspection observes zero direct fallback attempts.
- `[integration]` Sentinel secrets appear in neither API bodies nor Rich logs.
- `[e2e@gate-2]` Save/test a failing proxy, observe specific errors, remove it, disable a provider, stop/restore Redis, and keep local playback usable throughout.
- `[contract]` Settings/status masking and provider diagnostic envelopes match generated types.

**Do not**

- Do not read ambient proxy variables after an app proxy is saved, echo credentials, or make Last.fm mandatory.

## Chunk 8 — Mutation failure recovery and permanent deletion

**Files touched**

- `backend/src/chillify/application/deletion.py`
- `backend/src/chillify/infrastructure/media/recovery.py`
- `backend/src/chillify/api/schemas/deletion.py`
- `backend/src/chillify/api/routes/tracks.py`
- `frontend/src/features/metadata/DeleteTrackDialog.tsx`
- `frontend/src/components/ui/alert-dialog.tsx`
- `backend/tests/integration/test_media_edit_recovery.py`
- `backend/tests/integration/test_media_delete_recovery.py`

**Requirements**

- Enforce library-then-track lock order for publish/edit/delete and optimistic conflicts.
- Inject failures at every edit/delete stage and implement conservative startup rollback/finalization.
- Show server playlist impact plus browser queue/current-track impact before deletion.
- Delete active media first, then metadata/references; anonymize completed job identity while preserving phase/status/timestamps.

**Acceptance**

- `[integration]` Each injected edit/delete failure leaves one authoritative playable state after startup recovery.
- `[integration]` Successful deletion removes files, tags, records, playlist/session references, and identifying history metadata.
- `[e2e@gate-2]` Delete a playing playlist track, confirm disclosed impact, observe advance/stop, restart, and see only an anonymous “Deleted track” history shell.

**Do not**

- Do not soft-delete shared media, invert lock order, or retain identifying request/source metadata.

## DEMO GATE 2 — Acquisition and recovery

**Runnability preconditions**

- Prepare: `./scripts/gate/prepare.sh gate-2 recovery`.
- Launch: `docker compose --env-file .gate/gate-2/.env up --build -d`.
- Seed: `./scripts/gate/seed.sh gate-2 recovery` after API readiness.
- Composition: production Compose/composition root with fixture external protocols, real proxy policy, Redis, worker, filesystem, and failure-injection seams.
- Disposable safety: gate startup validates `.gate/gate-2/` roots and isolated Redis prefix before enabling failure injection.
- Serving chunks: link/review (Chunk 5); durable controls/recovery/duplicates (Chunk 6); settings/degradation (Chunk 7); edit/delete recovery (Chunk 8).

**Journey to walk**

1. Inspect valid Spotify/YouTube links and reject their bulk variants without jobs.
2. Review/correct a YouTube candidate, replace artwork, and download it.
3. Queue three jobs; cancel one, retry one, interrupt the active worker, and observe serial restart recovery.
4. Resubmit exact source/ISRC/artist-title duplicates and reach the existing track.
5. Inspect mounted path/free space/tool/provider health; verify masked Last.fm state and a nonfatal Last.fm miss; disable/re-enable Deezer; force proxy failure and observe no direct fallback; stop Redis and browse/search/play/read playlists locally, then restore Redis and observe unfinished work requeue without a web restart.
6. Inject edit failure and verify old state; perform successful edit and verify synchronized state.
7. Delete a playing playlist track and verify two-stage cleanup, queue handling, restart durability, and anonymized history.

**Observe**

- F2 and F4 are walkable; AC5–13 and AC18–20/23 have visible evidence.
- Failures name the affected phase and next action without secrets or fake percentages.
- Record the journey as `frontend/tests/e2e/gate-2.spec.ts`.

## Milestone 3 — Complete listening and interface

## Chunk 9 — Artist, album, and year contexts

**Files touched**

- `backend/src/chillify/application/library.py`
- `backend/src/chillify/api/schemas/library.py`
- `backend/src/chillify/api/routes/library.py`
- `frontend/src/features/library/ContextPage.tsx`
- `frontend/src/features/library/ContextGrid.tsx`
- `frontend/src/features/library/contextQueue.ts`
- `frontend/src/components/ui/tabs.tsx`
- `backend/tests/integration/test_context_ordering.py`

**Requirements**

- Implement stable derived artist/album keys, Unknown Album/Year contexts, collection summaries, and exact server orders.
- Expose Tracks/Artists/Albums/Years browsing and play each returned order unchanged.
- Preserve missing rows as unavailable and skip them during playback.

**Acceptance**

- `[integration]` Seeded contexts return exactly the architecture album/artist/year order, including unknown values.
- `[unit]` Context keys round-trip canonically and same-named albums by different artists stay separate.
- `[e2e@gate-3]` Browse and play artist, album, and year contexts; Queue shows the exact displayed order.

**Do not**

- Do not introduce separate artist/album persistence, recommendations, or grouped online search.

## Chunk 10 — Playlist ownership, reorder, and row actions

**Files touched**

- `backend/src/chillify/application/playlists.py`
- `backend/src/chillify/api/routes/playlists.py`
- `frontend/src/features/playlists/PlaylistPage.tsx`
- `frontend/src/features/playlists/SortablePlaylistRow.tsx`
- `frontend/src/features/library/AddToPlaylistMenu.tsx`
- `backend/tests/integration/test_playlists.py`

**Requirements**

- Put Add to Playlist on every local row through the same Shadcn DropdownMenu.
- Implement accessible dnd-kit reorder as one contiguous optimistic-revision transaction, plus remove-without-delete.
- Keep playlists profile-specific while media remains shared; preserve last confirmed order on failure.

**Acceptance**

- `[integration]` Profile A/B isolation, duplicate name/track rejection, contiguous reorder, and remove-without-delete hold after restart.
- `[e2e@gate-3]` Create playlists under two profiles, add/reorder/remove shared tracks, and verify ownership and exact play order.
- `[contract]` Playlist mutation conflicts return `record_changed` and restore the confirmed UI state.

**Do not**

- Do not add playlist deletion, cover art, collaboration, or custom drag primitives.

## Chunk 11 — Session queue and resilient persistent player

**Files touched**

- `frontend/src/features/player/QueueDrawer.tsx`
- `frontend/src/features/player/SortableQueueRow.tsx`
- `frontend/src/features/player/playerStore.ts`
- `frontend/src/features/player/useAudioController.ts`
- `frontend/src/features/player/PersistentPlayer.tsx`
- `frontend/src/components/ui/scroll-area.tsx`
- `frontend/src/components/ui/sheet.tsx`
- `frontend/tests/component/player-continuity.test.tsx`

**Requirements**

- Implement row-start/current-view continuation, context replacement, manual upcoming reorder/remove/clear, and previous/next.
- Keep player/audio mounted across S2–S12; clear on refresh/profile switch.
- Remove globally deleted occurrences and skip/label transiently missing tracks.
- Use Shadcn Sheet, Button, Slider, Tooltip, ScrollArea, and Empty for all visual controls.

**Acceptance**

- `[unit]` Queue reducers implement every context/session rule and handle deleted/missing tracks deterministically.
- `[e2e@gate-3]` Reorder/remove Queue items, navigate S2/S3/S9/S11/S12, and observe monotonic playback without source reset.
- `[e2e@gate-3]` Refresh and profile switch clear playback/queue while saved playlists remain.

**Do not**

- Do not add shuffle, repeat, restored queue, crossfade, or custom slider/drawer behavior.

## Chunk 12 — Complete Shadcn visual states and accessibility

**Files touched**

- `frontend/src/app/Router.tsx`
- `frontend/src/app/RouteErrorBoundary.tsx`
- `frontend/src/app/PersistentShell.tsx`
- `frontend/src/features/shared/DataState.tsx`
- `frontend/src/features/shared/DegradedBanner.tsx`
- `frontend/src/components/ui/accordion.tsx`
- `frontend/src/components/ui/breadcrumb.tsx`
- `frontend/src/components/ui/navigation-menu.tsx`
- `frontend/tests/e2e/accessibility.spec.ts`
- `frontend/tests/component/screen-states.test.tsx`

**Requirements**

- Finish every S1–S16 loading, empty, validation, unavailable, stale/reconnecting, degraded, recovery, error, and success state from UX.md.
- Install/compose Shadcn registry components before domain assemblies; document any registry gap before custom source.
- Enforce token-only styling, keyboard order, focus return, reduced motion, accessible names, contrast, and desktop density.
- Keep local/remote provenance, determinate/indeterminate progress, and operator feedback unmistakable.

**Acceptance**

- `[unit]` Component tests cover every enumerated screen state and modal focus return.
- `[e2e@gate-3]` Keyboard-only traversal completes F3 and settings recovery with visible focus and no trap.
- `[e2e@gate-3]` Axe reports zero critical/serious findings across every enumerated S1–S16 state.

**Do not**

- Do not copy Spotify assets/marks, add dashboard cards/gradients as decoration, or invent primitives present in Shadcn.

## DEMO GATE 3 — Browse, organize, and listen

**Runnability preconditions**

- Prepare: `./scripts/gate/prepare.sh gate-3 listening`.
- Launch: `docker compose --env-file .gate/gate-3/.env up --build -d`.
- Seed: `./scripts/gate/seed.sh gate-3 listening` after API readiness.
- Composition: unchanged production Compose/composition root with disposable provider fixtures and a seeded 500-track mounted library.
- Disposable safety: gate environment and isolated Redis prefix are validated before migration.
- Serving chunks: contexts (Chunk 9); playlists (Chunk 10); session player (Chunk 11); full states/accessibility (Chunk 12).

**Journey to walk**

1. Browse seeded Tracks, Artists, Albums, and Years including Unknown Year.
2. Play each context and compare S14 order with the displayed order.
3. Create profile-specific playlists; add, reorder, remove, and play shared tracks.
4. Reorder/remove upcoming session items, then navigate all primary routes without playback interruption.
5. Refresh and switch profile; verify session clears and durable playlists remain.
6. Walk keyboard/focus/reduced-motion and representative empty/loading/error/reconnecting states.

**Observe**

- F3, AC14–17/22, NFR-1/2/5/8, and local portions of NFR-10 are directly observable.
- Track rows remain dense, local/online provenance remains explicit, and the persistent player never remounts.
- Record the journey as `frontend/tests/e2e/gate-3.spec.ts`.

## Milestone 4 — Production hardening and release

## Chunk 13 — Production provider implementations

**Files touched**

- `backend/src/chillify/infrastructure/providers/deezer.py`
- `backend/src/chillify/infrastructure/providers/lastfm.py`
- `backend/src/chillify/infrastructure/providers/ytdlp.py`
- `backend/src/chillify/infrastructure/providers/spotdl.py`
- `backend/src/chillify/infrastructure/providers/artwork_http.py`
- `backend/src/chillify/infrastructure/providers/registry.py`
- `backend/tests/contract/test_deezer_contract.py`
- `backend/tests/contract/test_lastfm_contract.py`
- `backend/tests/contract/test_ytdlp_contract.py`
- `backend/tests/contract/test_spotdl_contract.py`
- `backend/tests/contract/test_artwork_contract.py`

**Requirements**

- Implement every external wire contract, timeout/retry/proxy rule, response normalization, match tolerance, bounded diagnostic, cancellation, and optional-enrichment behavior.
- Run production and fixture adapters through the same protocol suites.
- Verify exactly one valid MP3 output for SpotDL/yt-dlp and reject weak Deezer-to-audio matches.

**Acceptance**

- `[contract]` Sanitized success/error fixtures for every external system pass both fixture and production adapter suites.
- `[integration]` All real adapters receive the one proxy policy and no direct fallback transport.
- `[unit]` Provider metadata precedence and Last.fm gap-only merge are deterministic.

**Do not**

- Do not make live network calls in the normal test suite or couple application use cases to provider response shapes.

## Chunk 14 — Security, recovery, and storage hardening

**Files touched**

- `backend/src/chillify/infrastructure/security/outbound.py`
- `backend/src/chillify/infrastructure/media/recovery.py`
- `backend/src/chillify/api/middleware.py`
- `deploy/nginx.conf`
- `scripts/verify/security.sh`
- `scripts/verify/storage.sh`
- `scripts/verify/persistence.sh`
- `backend/tests/integration/test_ssrf.py`
- `backend/tests/integration/test_idempotency.py`
- `backend/tests/integration/test_concurrency.py`

**Requirements**

- Enforce SSRF redirect/IP rules, content limits, Origin checks, nginx body/connection limits, idempotency, path/symlink controls, and bounded errors.
- Exercise orphan publish/edit/delete recovery and concurrent mutation single-winner behavior.
- Verify durable files exist only on mounts and backup/restore requires the same key.

**Acceptance**

- `[integration]` Private/loopback redirect targets, oversized art, symlink escapes, stale revisions, and reused idempotency keys fail with the documented codes.
- `[integration]` All mutation crash points recover with zero mismatches.
- `[contract]` Security/storage scripts exit nonzero for a non-disposable or container-layer target.

**Do not**

- Do not add authentication/TLS or weaken trusted-LAN warnings.

## Chunk 15 — NFR and cross-browser verification

**Files touched**

- `scripts/verify.sh`
- `scripts/verify/nfr.sh`
- `frontend/playwright.config.ts`
- `frontend/tests/e2e/nfr.spec.ts`
- `frontend/tests/e2e/firefox-smoke.spec.ts`
- `frontend/tests/e2e/degraded.spec.ts`
- `frontend/tests/e2e/fixtures.ts`
- `backend/tests/integration/test_secret_redaction.py`

**Requirements**

- Provide one verify command covering Biome, TypeScript, Vitest, Ruff, mypy, pytest, contract tests, production build, Playwright, axe, and Compose canaries.
- Measure every PRD NFR with its exact sample size/budget and store machine-readable evidence.
- Run Chromium kernel and Firefox playback/navigation/seek/queue/modal/download smoke.
- Disconnect outbound traffic/Redis for degraded-local checks and scan API/UI/Rich output for secret sentinels.

**Acceptance**

- `[integration]` `./scripts/verify.sh` fails on any lint/type/test/build/contract/canary failure and passes from a clean checkout with gate prerequisites.
- `[e2e@gate-4]` NFR-1 through NFR-12 produce named measurements at or within every PRD budget.
- `[e2e@gate-4]` Current Chromium completes F1 and current Firefox completes the required smoke.

**Do not**

- Do not relax budgets, omit slow states, or turn live provider availability into a release dependency.

## Chunk 16 — Production-composition proof

**Files touched**

- `scripts/production_canary.sh`
- `scripts/gate/prepare.sh`
- `backend/src/chillify/composition.py`
- `backend/tests/integration/test_production_composition.py`
- `frontend/tests/e2e/production-composition.spec.ts`
- `README.md`

**Requirements**

- Build release images and start the unchanged production entry point with real provider adapter classes, real tools, disposable SQLite/media roots, and isolated Redis.
- Prove provider/tool composition and fail-closed outbound error paths without fixture adapter classes; live provider success remains an explicit canary action and never mutates household state.
- Run deterministic release journeys with fixture external protocols only after the production-composition proof passes.
- Document Arch Linux Compose setup, mounted-volume ownership, Redis URL/prefix, key backup, LAN warning, and provider legal/terms responsibility.

**Acceptance**

- `[integration]` The release API/worker composition resolves real Deezer, Last.fm, SpotDL, yt-dlp, artwork, Redis, SQLite, and media implementations and reaches ready/degraded states on disposable roots.
- `[contract]` `scripts/production_canary.sh` refuses household roots and reports each real adapter/tool independently; network failure remains a clear canary failure, never a direct-fallback success.
- `[e2e@gate-4]` The release build starts through production Compose after proof, then the deterministic kernel journey runs with only external systems replaced at their verified seams.

**Do not**

- Do not create a gate-only application composition, require live providers for deterministic release, or run a canary against household data.

## Acceptance-to-gate coverage

| PRD criteria | Observable gate journey |
|---|---|
| AC1–AC4 | Gate 1 steps 1–4; Gate 4 steps 1–3 |
| AC5–AC13 | Gate 2 steps 1–7; Gate 4 steps 2–7 |
| AC14–AC17 | Gate 3 steps 1–5; Gate 4 steps 5–7 |
| AC18–AC20, AC23 | Gate 2 steps 4–5; Gate 4 step 7 |
| AC21 | Gate 1 step 7; Gate 4 step 6 |
| AC22 | Gates 1–3 state walks; Gate 4 step 7 |

## NFR serving map

| NFR | Serving mechanism |
|---|---|
| NFR-1 | Chunk 15 `nfr.spec.ts` seeded-500 search measurement; Gates 3/4 |
| NFR-2 | Chunk 15 route timing measurement; Gates 3/4 |
| NFR-3 | Chunk 15 per-browser playback-start measurement; Gate 4 |
| NFR-4 | Chunk 15 server-event-to-render timestamp measurement; Gates 2/4 |
| NFR-5 | Chunk 11 continuity instrumentation and Chunk 15 measurement; Gates 3/4 |
| NFR-6 | Chunk 14 persistence canary; Gates 1/4 |
| NFR-7 | Chunks 8/14 stage-failure integration matrix; Gates 2/4 |
| NFR-8 | Chunk 12 enumerated-state axe/manual matrix; Gates 3/4 |
| NFR-9 | Chunk 15 Chromium journey and Firefox smoke; Gate 4 |
| NFR-10 | Chunks 7/15 disconnected-network/Redis journey; Gates 2/4 |
| NFR-11 | Chunks 1/7/15 sentinel scan of API/UI/Rich logs; Gates 2/4 |
| NFR-12 | Chunk 14 storage-layer canary; Gate 4 |

## RELEASE GATE 4 — v1 exit bar

**Runnability preconditions**

- Prepare: `./scripts/gate/prepare.sh release kernel-500`.
- Production proof: `./scripts/production_canary.sh --env-file .gate/release/.env --no-live-success`.
- Launch: `docker compose --env-file .gate/release/.env up --build -d`.
- Seed: `./scripts/gate/seed.sh release kernel-500` after API readiness.
- Verify: `./scripts/verify.sh --env-file .gate/release/.env`.
- Composition: release Dockerfiles, unchanged production `compose.yaml`, production composition root, real SQLite/media/Redis/tools, and verified fixture implementations only at external provider/network protocols.
- Disposable safety: `.gate/release/` roots and `chillify:gate:release:` Redis prefix are mandatory and checked by both startup and scripts.
- Serving chunks: production boot (Chunk 1); local profile/player (Chunk 2); durable acquisition (Chunks 3, 5–7, 13); correction/deletion (Chunks 4, 8); browse/playlists/player/UI (Chunks 9–12); hardening/NFR/proof (Chunks 14–16).

**Kernel journey**

1. Select Household; local search makes no provider request.
2. Explicitly search Deezer; download one distinct result through the serial queue and observe every truthful phase.
3. Close/reopen the browser and verify durable job state and playable mounted MP3.
4. Correct metadata/artwork atomically and verify DB, ID3, art, and path agreement.
5. Create a profile playlist, add/play the track, and navigate without interruption.
6. Restart containers and verify track, correction, playlist, settings, and anonymous/nondeleted job history persist while playback session is empty.
7. Walk direct Spotify/YouTube validation, cancellation/retry/restart, duplicate rejection, proxy fail-closed, Redis degradation/recovery, context ordering, deletion, and every documented empty/error/reconnecting state.

**Observe**

- All PRD acceptance criteria AC1–AC23 pass through the production composition.
- NFR-1–NFR-12 have named evidence and meet their numeric/zero-defect budgets.
- Chromium completes F1; Firefox completes playback/navigation/seek/queue/modal/download smoke; axe has no critical/serious finding.
- Rich stdout and API/UI errors contain no sentinel secret; all durable data is on disposable mounts; no live call or household path is required.
- Record the release journey as `frontend/tests/e2e/gate-4-release.spec.ts`.
