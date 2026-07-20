# Chillify Core Predicted File Structure

This is the complete cycle-001 prediction. Generated `.gate/`, media, SQLite, caches, coverage, build output, and evidence files are runtime artifacts and are not committed.

```text
/
├── .env.example
├── .gitignore
├── ARCHITECTURE.md
├── CONVENTIONS.md
├── DESIGN.md
├── README.md
├── UX.md
├── biome.json
├── compose.yaml
├── backend/
│   ├── alembic.ini
│   ├── pyproject.toml
│   ├── uv.lock
│   ├── migrations/
│   │   ├── env.py
│   │   ├── script.py.mako
│   │   └── versions/
│   │       └── 0001_core.py
│   ├── src/
│   │   └── chillify/
│   │       ├── __init__.py
│   │       ├── composition.py
│   │       ├── config.py
│   │       ├── gate_seed.py
│   │       ├── api/
│   │       │   ├── __init__.py
│   │       │   ├── dependencies.py
│   │       │   ├── errors.py
│   │       │   ├── main.py
│   │       │   ├── middleware.py
│   │       │   ├── routes/
│   │       │   │   ├── __init__.py
│   │       │   │   ├── artwork.py
│   │       │   │   ├── downloads.py
│   │       │   │   ├── events.py
│   │       │   │   ├── library.py
│   │       │   │   ├── links.py
│   │       │   │   ├── playlists.py
│   │       │   │   ├── profiles.py
│   │       │   │   ├── search.py
│   │       │   │   ├── settings.py
│   │       │   │   ├── system.py
│   │       │   │   └── tracks.py
│   │       │   └── schemas/
│   │       │       ├── __init__.py
│   │       │       ├── artwork.py
│   │       │       ├── common.py
│   │       │       ├── deletion.py
│   │       │       ├── downloads.py
│   │       │       ├── library.py
│   │       │       ├── links.py
│   │       │       ├── playlists.py
│   │       │       ├── profiles.py
│   │       │       ├── settings.py
│   │       │       └── tracks.py
│   │       ├── application/
│   │       │   ├── __init__.py
│   │       │   ├── artwork.py
│   │       │   ├── deletion.py
│   │       │   ├── downloads.py
│   │       │   ├── library.py
│   │       │   ├── links.py
│   │       │   ├── metadata.py
│   │       │   ├── playlists.py
│   │       │   ├── reconciliation.py
│   │       │   ├── search.py
│   │       │   └── settings.py
│   │       ├── domain/
│   │       │   ├── __init__.py
│   │       │   ├── errors.py
│   │       │   ├── jobs.py
│   │       │   ├── models.py
│   │       │   ├── normalization.py
│   │       │   ├── ordering.py
│   │       │   └── protocols.py
│   │       ├── infrastructure/
│   │       │   ├── __init__.py
│   │       │   ├── db/
│   │       │   │   ├── __init__.py
│   │       │   │   ├── engine.py
│   │       │   │   ├── models.py
│   │       │   │   ├── repositories.py
│   │       │   │   └── transactions.py
│   │       │   ├── logging/
│   │       │   │   ├── __init__.py
│   │       │   │   ├── redaction.py
│   │       │   │   └── setup.py
│   │       │   ├── media/
│   │       │   │   ├── __init__.py
│   │       │   │   ├── artwork.py
│   │       │   │   ├── mutations.py
│   │       │   │   ├── recovery.py
│   │       │   │   ├── storage.py
│   │       │   │   ├── tags.py
│   │       │   │   └── workspaces.py
│   │       │   ├── providers/
│   │       │   │   ├── __init__.py
│   │       │   │   ├── artwork_http.py
│   │       │   │   ├── deezer.py
│   │       │   │   ├── fixtures.py
│   │       │   │   ├── lastfm.py
│   │       │   │   ├── registry.py
│   │       │   │   ├── spotdl.py
│   │       │   │   └── ytdlp.py
│   │       │   ├── queue/
│   │       │   │   ├── __init__.py
│   │       │   │   ├── cancellation.py
│   │       │   │   ├── celery_app.py
│   │       │   │   ├── reconciliation.py
│   │       │   │   └── tasks.py
│   │       │   └── security/
│   │       │       ├── __init__.py
│   │       │       ├── outbound.py
│   │       │       └── secrets.py
│   │       └── worker/
│   │           ├── __init__.py
│   │           └── main.py
│   └── tests/
│       ├── __init__.py
│       ├── conftest.py
│       ├── contract/
│       │   ├── __init__.py
│       │   ├── provider_suite.py
│       │   ├── test_artwork_contract.py
│       │   ├── test_deezer_contract.py
│       │   ├── test_lastfm_contract.py
│       │   ├── test_openapi_contract.py
│       │   ├── test_spotdl_contract.py
│       │   └── test_ytdlp_contract.py
│       ├── fixtures/
│       │   ├── media/
│       │   │   ├── cover.jpg
│       │   │   └── gate-tone.mp3
│       │   └── providers/
│       │       ├── deezer_error.json
│       │       ├── deezer_search.json
│       │       ├── lastfm_miss.json
│       │       ├── lastfm_track.json
│       │       ├── spotdl_track.json
│       │       └── ytdlp_video.json
│       ├── integration/
│       │   ├── __init__.py
│       │   ├── test_concurrency.py
│       │   ├── test_context_ordering.py
│       │   ├── test_duplicates.py
│       │   ├── test_idempotency.py
│       │   ├── test_media_delete_recovery.py
│       │   ├── test_media_edit_recovery.py
│       │   ├── test_playlists.py
│       │   ├── test_production_composition.py
│       │   ├── test_proxy_fail_closed.py
│       │   ├── test_queue_recovery.py
│       │   ├── test_secret_redaction.py
│       │   └── test_ssrf.py
│       └── unit/
│           ├── __init__.py
│           ├── test_config.py
│           ├── test_errors.py
│           ├── test_jobs.py
│           ├── test_normalization.py
│           └── test_ordering.py
├── deploy/
│   ├── docker/
│   │   ├── backend.Dockerfile
│   │   └── web.Dockerfile
│   └── nginx.conf
├── frontend/
│   ├── components.json
│   ├── index.html
│   ├── package-lock.json
│   ├── package.json
│   ├── playwright.config.ts
│   ├── tsconfig.app.json
│   ├── tsconfig.json
│   ├── tsconfig.node.json
│   ├── vite.config.ts
│   ├── vitest.config.ts
│   ├── public/
│   │   └── chillify-mark.svg
│   ├── src/
│   │   ├── main.tsx
│   │   ├── api/
│   │   │   ├── client.ts
│   │   │   ├── generated.ts
│   │   │   └── queryKeys.ts
│   │   ├── app/
│   │   │   ├── AppSidebar.tsx
│   │   │   ├── AppProviders.tsx
│   │   │   ├── EventBridge.tsx
│   │   │   ├── PersistentShell.tsx
│   │   │   ├── RouteErrorBoundary.tsx
│   │   │   ├── Router.tsx
│   │   │   └── TopBar.tsx
│   │   ├── components/
│   │   │   └── ui/
│   │   │       ├── accordion.tsx
│   │   │       ├── alert-dialog.tsx
│   │   │       ├── alert.tsx
│   │   │       ├── aspect-ratio.tsx
│   │   │       ├── badge.tsx
│   │   │       ├── breadcrumb.tsx
│   │   │       ├── button.tsx
│   │   │       ├── card.tsx
│   │   │       ├── dialog.tsx
│   │   │       ├── dropdown-menu.tsx
│   │   │       ├── empty.tsx
│   │   │       ├── field.tsx
│   │   │       ├── input.tsx
│   │   │       ├── label.tsx
│   │   │       ├── navigation-menu.tsx
│   │   │       ├── progress.tsx
│   │   │       ├── scroll-area.tsx
│   │   │       ├── select.tsx
│   │   │       ├── separator.tsx
│   │   │       ├── sheet.tsx
│   │   │       ├── sidebar.tsx
│   │   │       ├── skeleton.tsx
│   │   │       ├── slider.tsx
│   │   │       ├── sonner.tsx
│   │   │       ├── switch.tsx
│   │   │       ├── table.tsx
│   │   │       ├── tabs.tsx
│   │   │       └── tooltip.tsx
│   │   ├── features/
│   │   │   ├── acquisition/
│   │   │   │   ├── AddLinkDialog.tsx
│   │   │   │   └── YouTubeReviewDialog.tsx
│   │   │   ├── downloads/
│   │   │   │   ├── DownloadRow.tsx
│   │   │   │   ├── DownloadsPage.tsx
│   │   │   │   └── GlobalJobIndicator.tsx
│   │   │   ├── library/
│   │   │   │   ├── AddToPlaylistMenu.tsx
│   │   │   │   ├── ContextGrid.tsx
│   │   │   │   ├── ContextPage.tsx
│   │   │   │   ├── LibraryPage.tsx
│   │   │   │   ├── TrackRow.tsx
│   │   │   │   ├── TrackTable.tsx
│   │   │   │   └── contextQueue.ts
│   │   │   ├── metadata/
│   │   │   │   ├── ArtworkPicker.tsx
│   │   │   │   ├── DeleteTrackDialog.tsx
│   │   │   │   └── TrackEditorDialog.tsx
│   │   │   ├── player/
│   │   │   │   ├── PersistentPlayer.tsx
│   │   │   │   ├── QueueDrawer.tsx
│   │   │   │   ├── SortableQueueRow.tsx
│   │   │   │   ├── playerStore.ts
│   │   │   │   └── useAudioController.ts
│   │   │   ├── playlists/
│   │   │   │   ├── PlaylistEditorDialog.tsx
│   │   │   │   ├── PlaylistPage.tsx
│   │   │   │   ├── PlaylistsPage.tsx
│   │   │   │   └── SortablePlaylistRow.tsx
│   │   │   ├── profiles/
│   │   │   │   └── ProfileChooser.tsx
│   │   │   ├── search/
│   │   │   │   ├── ResultCards.tsx
│   │   │   │   └── SearchPage.tsx
│   │   │   ├── settings/
│   │   │   │   ├── ProviderCard.tsx
│   │   │   │   ├── SettingsPage.tsx
│   │   │   │   └── StorageDiagnostics.tsx
│   │   │   └── shared/
│   │   │       ├── DataState.tsx
│   │   │       └── DegradedBanner.tsx
│   │   ├── lib/
│   │   │   ├── cn.ts
│   │   │   ├── format.ts
│   │   │   └── validation.ts
│   │   └── styles/
│   │       ├── globals.css
│   │       └── tokens.css
│   └── tests/
│       ├── component/
│       │   ├── player-continuity.test.tsx
│       │   └── screen-states.test.tsx
│       ├── e2e/
│       │   ├── accessibility.spec.ts
│       │   ├── degraded.spec.ts
│       │   ├── firefox-smoke.spec.ts
│       │   ├── fixtures.ts
│       │   ├── gate-1.spec.ts
│       │   ├── gate-2.spec.ts
│       │   ├── gate-3.spec.ts
│       │   ├── gate-4-release.spec.ts
│       │   ├── nfr.spec.ts
│       │   └── production-composition.spec.ts
│       └── setup.ts
├── scripts/
│   ├── production_canary.sh
│   ├── verify.sh
│   ├── gate/
│   │   ├── cleanup.sh
│   │   ├── prepare.sh
│   │   └── seed.sh
│   └── verify/
│       ├── nfr.sh
│       ├── persistence.sh
│       ├── security.sh
│       └── storage.sh
└── specs/
    ├── ROADMAP.md
    └── 001-core/
        ├── FILE_STRUCTURE.md
        ├── PLAN.md
        ├── PRD.md
        └── SPEC.md
```

## Code map

| Area | Entry point | Owns |
|---|---|---|
| Web | `frontend/src/main.tsx` | SPA composition and route mount |
| Browser shell | `frontend/src/app/PersistentShell.tsx` | stable navigation, viewport, global status, player slot |
| Browser audio | `frontend/src/features/player/useAudioController.ts` | one audio element and session queue effects |
| API | `backend/src/chillify/api/main.py` | HTTP/SSE middleware and route composition |
| Worker | `backend/src/chillify/worker/main.py` | Celery process bootstrap |
| Composition | `backend/src/chillify/composition.py` | real/fixture protocol binding and safety guard |
| Domain | `backend/src/chillify/domain/` | dependency-free contracts and invariants |
| Use cases | `backend/src/chillify/application/` | transaction boundaries and orchestration |
| Persistence | `backend/src/chillify/infrastructure/db/` | SQLite models/repositories/transactions |
| Media | `backend/src/chillify/infrastructure/media/` | files, tags, artwork, locking, recovery |
| Providers | `backend/src/chillify/infrastructure/providers/` | external wire adapters only |
| Queue | `backend/src/chillify/infrastructure/queue/` | Celery transport, task boundary, reconciliation |
| Deployment | `compose.yaml` | production entry point for normal use and gates |
| Verification | `scripts/verify.sh` | canonical static/test/build/e2e/canary command |
