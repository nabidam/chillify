# Chillify Architecture

## 1. Architectural contract

Chillify is a downloader-first, local music library for one trusted household. It runs on one Arch Linux host, serves desktop browsers over the LAN, stores all durable application and media data on mounted local disk, and uses the operator's existing Redis instance only for background-job transport.

The v1 system has three application processes:

```text
Chromium / Firefox
        │ LAN HTTP
        ▼
┌──────────────────┐
│ web: nginx       │  SPA assets; same-origin /api and /media proxy
└────────┬─────────┘
         │
         ▼
┌──────────────────┐       Celery messages       ┌────────────────────┐
│ api: FastAPI     │ ───────────────────────────► │ external Redis     │
│ SQLite owner*    │ ◄──── health/reconnect ───── │ (not in Compose)   │
└───────┬──────────┘                              └──────────┬─────────┘
        │                                                    │
        │ shared SQLite + mounted media                      ▼
        │                                         ┌────────────────────┐
        └────────────────────────────────────────►│ worker: Celery     │
                                                  │ concurrency = 1    │
                                                  └────────────────────┘
```

`*` The API and worker both use the SQLite database through the same repository layer. SQLite WAL, short transactions, a busy timeout, application locks, and optimistic revisions serialize mutations. Redis is never the source of truth for jobs.

### Boundaries

- **Browser owns:** current profile selection, audio element, volume, current playback context, and editable playback queue. These disappear on refresh or profile switch.
- **API owns:** validation, local search/browse, profiles, playlists, settings, job records/events, media authorization by track ID, and all user-visible state.
- **Worker owns:** provider calls required by queued acquisition, download/conversion/tagging, durable job transitions, and recovery of interrupted jobs.
- **Disk owns:** MP3s, per-track artwork, SQLite, mutation recovery files, and temporary acquisition files.
- **Redis owns:** transient Celery delivery only. A missing Redis degrades acquisition but cannot make the library unreadable.
- **Providers own:** discovery/source data, not application state. No provider response is exposed directly to the UI.

Object storage is intentionally excluded. At 500 tracks on one host, a bind-mounted normal filesystem gives atomic same-filesystem operations, direct byte-range streaming, simple backup, and no network/storage service to operate.

## 2. Stack and pinned dependencies

Every dependency is pinned exactly in lockfiles and container images. Renovation is an explicit change, not a floating install.

### Runtime and platform

| Capability | Package/version | Replaces |
|---|---|---|
| Python runtime | CPython `3.14.6` | system Python |
| Python environment/lock | `uv 0.11.29` | pip/Poetry |
| Browser build runtime | Node.js `24.18.0` LTS, npm `12.0.1` | system Node |
| SPA/static reverse proxy | nginx `1.30.4` | dev server in production |
| conversion/probing | FFmpeg `8.1.2` | ad-hoc media conversion |
| SpotDL JavaScript runtime | Deno `2.9.3` | implicit/unpinned JS runtime |
| queue broker | operator Redis Server `8.6.1` through `REDIS_URL` | Compose-owned Redis |

### Frontend

| Capability | Package/version | Replaces |
|---|---|---|
| UI runtime | `react@19.2.7`, `react-dom@19.2.7` | server-rendered templates |
| routing | `react-router@8.2.0` | hand-written route state |
| server state | `@tanstack/react-query@5.101.3` | hand-written request cache |
| session player state | `zustand@5.0.14` | global React context |
| styling/build integration | `tailwindcss@4.3.3`, `@tailwindcss/vite@4.3.3` | free-form CSS system |
| component source/CLI | `shadcn@4.13.1` | hand-written primitives |
| accessible primitives | `radix-ui@1.6.4` | individual Radix packages/custom dialogs |
| component variants/utilities | `class-variance-authority@0.7.1`, `clsx@2.1.1`, `tailwind-merge@3.6.0` | manual class branching |
| feedback/theme utilities | `sonner@2.0.7`, `next-themes@0.4.6`, `tw-animate-css@1.4.0` | custom toast/animation primitives |
| icons | `lucide-react@1.25.0` | bespoke SVG icons |
| forms/validation | `react-hook-form@7.82.0`, `zod@4.4.3`, `@hookform/resolvers@5.4.0` | per-form state/validators |
| playlist/queue sorting | `@dnd-kit/react@0.5.0` | custom pointer drag logic |
| typed API client | `openapi-fetch@0.17.0`, `openapi-typescript@7.13.0` | duplicated request types |
| build/typecheck | `vite@8.1.5`, `@vitejs/plugin-react@6.0.3`, `typescript@5.9.3`, `@types/react@19.2.17`, `@types/react-dom@19.2.3` | untyped browser build |
| lint/format | `@biomejs/biome@2.5.4` | separate ESLint/Prettier stack |

Shadcn's `new-york-v4` registry with the Radix base is the component source of record. Before creating any UI primitive, implementation must search and inspect the Shadcn registry. Existing registry components are installed and composed; their source may be themed through semantic tokens. A custom primitive is allowed only when the registry has no suitable component, and that exception is recorded in the Decision log. Domain assemblies such as `TrackRow` and `PersistentPlayer` may compose Shadcn components; they do not reimplement Button, Dialog, Slider, Menu, Field, Table, Sheet, Sonner, Tooltip, Skeleton, Empty, Alert, or Sidebar behavior.

### Backend and worker

| Capability | Package/version | Replaces |
|---|---|---|
| HTTP/OpenAPI/SSE | `fastapi@0.139.2`, `uvicorn@0.51.0` | bespoke HTTP server |
| schemas/config | `pydantic@2.13.4`, `pydantic-settings@2.14.2` | manual coercion |
| persistence/migrations | `SQLAlchemy@2.0.51`, `alembic@1.18.5` | raw application SQL |
| background jobs | `celery@5.6.3`, `redis@8.0.1` | in-process tasks |
| outbound HTTP/proxy | `httpx[socks]@0.28.1` | mixed HTTP clients |
| audio acquisition | `yt-dlp@2026.7.4` (library), `spotdl@4.5.2` (isolated CLI) | home-grown extractors |
| media tags/images | `mutagen@1.48.1`, `pillow@12.3.0` | FFmpeg-only metadata writes |
| multipart forms | `python-multipart@0.0.32` | manual upload parsing |
| retry policy | `tenacity@9.1.4` | nested retry loops |
| secret encryption | `cryptography@49.0.0` | plaintext stored credentials |
| safe paths/locks | `pathvalidate@3.3.1`, `filelock@3.31.1` | ad-hoc filename and lock handling |
| stdout observability | `rich@15.0.0` | plain `print` and file logs |

SpotDL is not importable alongside this stack: every `spotdl@4.x` release caps `fastapi<0.104` and `uvicorn<0.24`, which the pinned API versions exceed. SpotDL is therefore installed into its own isolated environment inside the backend image and invoked as a pinned argument-vector subprocess behind the same `LinkInspector`/`AcquisitionProvider` protocols. No SpotDL module is imported into the API or worker process, no shell is involved, and the subprocess argument/output shape is a contract-tested boundary. The isolated environment's version is pinned exactly like every other dependency.

Rich configures Python's standard `logging` pipeline with `RichHandler` and structured `extra` fields. Libraries log through `logging.getLogger(__name__)`; they never print. API and worker logs go only to stdout/stderr for `docker compose logs`, with timestamps, level, service, request/job ID, phase, provider, and redacted error context. Tracebacks are enabled for unexpected failures; secrets and proxy credentials are filtered before formatting.

### Test harnesses

| Layer | Harness |
|---|---|
| frontend unit/component | `vitest@4.1.10`, `@testing-library/react@16.3.2`, `@testing-library/user-event@14.6.1`, `jsdom@29.1.1`, `msw@2.15.0` |
| browser/e2e/accessibility | `@playwright/test@1.61.1`, `@axe-core/playwright@4.12.1` |
| backend/unit/integration | `pytest@9.1.1`, `respx@0.23.1` |
| Python static checks | `ruff@0.15.22`, `mypy@2.3.0` |
| Dependency audit | `pip-audit@2.10.1`, `npm audit` |
| provider contract | checked-in sanitized JSON fixtures plus `respx`/injected extractor doubles |
| container canary | Docker Compose health, persistence, Redis-offline, and mounted-path scripts |

Provider, downloader, filesystem, clock, process runner, and Redis interfaces are injected. Tests never require live provider calls.

Demo/release gates use the production Compose file and the same `composition.py` entry point. Fixture provider implementations may bind only when `CHILLIFY_ENV=gate`, `CHILLIFY_FIXTURE_ROOT` resolves beneath the repository's `.gate/` tree, both configured storage roots resolve beneath the same gate directory, and `CHILLIFY_REDIS_PREFIX` begins with `chillify:gate:`. Any mismatch fails startup before migration or Redis mutation. The guarded gate-seed entry calls the production repositories/media services after API readiness; it is a data-fixture tool, not an alternate application composition. Production mode never imports or registers fixture adapters.

## 3. Repository and module design

```text
/
├── frontend/
│   ├── src/
│   │   ├── app/                 # router, providers, shell
│   │   ├── components/ui/       # Shadcn-owned source only
│   │   ├── features/
│   │   │   ├── profiles/
│   │   │   ├── library/
│   │   │   ├── search/
│   │   │   ├── acquisition/
│   │   │   ├── downloads/
│   │   │   ├── metadata/
│   │   │   ├── playlists/
│   │   │   ├── player/
│   │   │   └── settings/
│   │   ├── api/                 # generated OpenAPI types + thin client
│   │   └── styles/              # semantic tokens and global Tailwind theme
│   └── tests/
├── backend/
│   ├── src/chillify/
│   │   ├── api/                 # FastAPI routes, schemas, error mapping
│   │   ├── application/         # use cases and transaction boundaries
│   │   ├── domain/              # entities, value objects, protocols, state machines
│   │   ├── infrastructure/
│   │   │   ├── db/
│   │   │   ├── media/
│   │   │   ├── providers/
│   │   │   ├── queue/
│   │   │   ├── security/
│   │   │   └── logging/
│   │   ├── worker/              # Celery app/tasks/reconciliation
│   │   └── config.py
│   ├── migrations/
│   └── tests/
├── deploy/
│   ├── nginx.conf
│   └── docker/
├── scripts/                     # verification/canary entry points
├── compose.yaml
├── .env.example
└── specs/
```

Dependency direction is one-way:

```text
api routes ───────► application use cases ───────► domain protocols/entities
worker tasks ─────► application use cases ───────► domain protocols/entities
infrastructure ───► domain protocols (implements them)
frontend routes ──► feature assemblies ──────────► generated API client + UI registry
player store ─────► browser Audio element only; never imports route components
```

The domain layer imports no FastAPI, SQLAlchemy, Celery, HTTPX, filesystem, or provider package. Provider implementations are registered explicitly at composition-root startup; importing a new adapter cannot change core acquisition behavior.

### Provider interfaces

```text
DiscoveryProvider.search(query, limit, proxy) -> list[TrackCandidate]
LinkInspector.supports(url) -> bool
LinkInspector.inspect(url, proxy) -> TrackCandidate
AcquisitionProvider.acquire(candidate, workspace, proxy, progress, cancelled) -> AudioArtifact
MetadataEnricher.enrich(candidate, missing_fields, proxy) -> MetadataPatch
ArtworkFetcher.fetch(source, workspace, proxy) -> ImageArtifact
```

`TrackCandidate` is the normalized boundary type: provider, source ID/URL, title, artist, album, year, disc/track number, duration, ISRC, artwork URL, acquisition locator, and raw-response fingerprint. Precedence is submitted review values → source provider metadata → Last.fm gap fill → deterministic Unknown fallback. Last.fm never overwrites a populated field.

The initial registry is:

| Adapter | Interfaces | Responsibility |
|---|---|---|
| Deezer | `DiscoveryProvider` | keyless matching-track search and metadata; never audio |
| SpotDL | `LinkInspector`, `AcquisitionProvider` | one Spotify track link; metadata and best-quality MP3, through the isolated CLI boundary |
| yt-dlp | `LinkInspector`, `AcquisitionProvider` | one YouTube video, or one audio match for a Deezer candidate |
| Last.fm | `MetadataEnricher` | optional missing metadata/artwork only |
| HTTP artwork | `ArtworkFetcher` | provider/user URL retrieval through validated outbound policy |

## 4. Data model

SQLite is configured per connection with `foreign_keys=ON`, `journal_mode=WAL`, `synchronous=FULL`, and `busy_timeout=5000`. Timestamps are UTC RFC 3339 text. UUIDv7 values are generated in the application. Case-folded and search-normalized fields are computed in application code with one versioned normalizer. The application validates release year against `1000..(current UTC year + 1)` using an injected clock; the broader SQLite check is only a corruption guard.

The initial Alembic migration owns this complete DDL:

```sql
CREATE TABLE profiles (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL CHECK (length(name) BETWEEN 1 AND 40),
    name_folded TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE tracks (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL CHECK (length(title) BETWEEN 1 AND 200),
    artist TEXT NOT NULL CHECK (length(artist) BETWEEN 1 AND 200),
    album TEXT CHECK (album IS NULL OR length(album) BETWEEN 1 AND 200),
    release_year INTEGER CHECK (release_year IS NULL OR release_year BETWEEN 1000 AND 9999),
    disc_number INTEGER CHECK (disc_number IS NULL OR disc_number BETWEEN 1 AND 999),
    track_number INTEGER CHECK (track_number IS NULL OR track_number BETWEEN 1 AND 999),
    duration_ms INTEGER CHECK (duration_ms IS NULL OR duration_ms >= 0),
    normalized_artist TEXT NOT NULL,
    normalized_title TEXT NOT NULL,
    normalized_album TEXT NOT NULL,
    isrc TEXT,
    file_relpath TEXT NOT NULL UNIQUE,
    artwork_relpath TEXT,
    mime_type TEXT NOT NULL DEFAULT 'audio/mpeg' CHECK (mime_type = 'audio/mpeg'),
    file_size_bytes INTEGER NOT NULL CHECK (file_size_bytes >= 0),
    content_sha256 TEXT NOT NULL CHECK (length(content_sha256) = 64),
    availability TEXT NOT NULL DEFAULT 'available'
        CHECK (availability IN ('available', 'missing', 'mutating', 'recovery')),
    revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (normalized_artist, normalized_title)
);

CREATE UNIQUE INDEX uq_tracks_isrc
    ON tracks(lower(isrc)) WHERE isrc IS NOT NULL AND isrc <> '';
CREATE INDEX ix_tracks_artist ON tracks(normalized_artist);
CREATE INDEX ix_tracks_title ON tracks(normalized_title);
CREATE INDEX ix_tracks_album ON tracks(normalized_artist, normalized_album);
CREATE INDEX ix_tracks_year ON tracks(release_year);
CREATE INDEX ix_tracks_created ON tracks(created_at DESC);

CREATE TABLE track_sources (
    id TEXT PRIMARY KEY,
    track_id TEXT NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
    provider TEXT NOT NULL CHECK (provider IN ('deezer', 'spotify', 'youtube')),
    source_id TEXT,
    source_url TEXT NOT NULL,
    raw_fingerprint TEXT,
    created_at TEXT NOT NULL
);

CREATE UNIQUE INDEX uq_track_sources_identity
    ON track_sources(provider, source_id)
    WHERE source_id IS NOT NULL AND source_id <> '';
CREATE INDEX ix_track_sources_track ON track_sources(track_id);

CREATE TABLE playlists (
    id TEXT PRIMARY KEY,
    profile_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    name TEXT NOT NULL CHECK (length(name) BETWEEN 1 AND 100),
    name_folded TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
    UNIQUE (profile_id, name_folded)
);

CREATE INDEX ix_playlists_profile ON playlists(profile_id, updated_at DESC);

CREATE TABLE playlist_tracks (
    playlist_id TEXT NOT NULL REFERENCES playlists(id) ON DELETE CASCADE,
    track_id TEXT NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
    position INTEGER NOT NULL CHECK (position >= 0),
    added_at TEXT NOT NULL,
    PRIMARY KEY (playlist_id, track_id),
    UNIQUE (playlist_id, position)
);

CREATE INDEX ix_playlist_tracks_track ON playlist_tracks(track_id);

CREATE TABLE download_jobs (
    id TEXT PRIMARY KEY,
    provider TEXT NOT NULL CHECK (provider IN ('deezer', 'spotdl', 'yt_dlp')),
    source_type TEXT NOT NULL CHECK (source_type IN ('deezer_result', 'spotify_track', 'youtube_video')),
    source_ref TEXT NOT NULL,
    dedupe_key TEXT NOT NULL,
    request_json TEXT NOT NULL,
    candidate_json TEXT,
    state TEXT NOT NULL
        CHECK (state IN ('queued', 'running', 'completed', 'failed', 'cancelled')),
    phase TEXT NOT NULL
        CHECK (phase IN (
            'accepted', 'inspecting', 'queued', 'restarted', 'downloading',
            'converting', 'enriching', 'tagging', 'organizing', 'completed',
            'failed', 'cancelled'
        )),
    progress_percent REAL CHECK (
        progress_percent IS NULL OR
        (progress_percent >= 0.0 AND progress_percent <= 100.0)
    ),
    celery_task_id TEXT,
    lease_owner TEXT,
    lease_expires_at TEXT,
    heartbeat_at TEXT,
    parent_job_id TEXT REFERENCES download_jobs(id) ON DELETE SET NULL,
    restart_count INTEGER NOT NULL DEFAULT 0 CHECK (restart_count >= 0),
    cancel_requested_at TEXT,
    error_code TEXT,
    error_message TEXT,
    error_detail TEXT,
    result_track_id TEXT REFERENCES tracks(id) ON DELETE SET NULL,
    version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    updated_at TEXT NOT NULL
);

CREATE UNIQUE INDEX uq_download_jobs_active_dedupe
    ON download_jobs(dedupe_key)
    WHERE state IN ('queued', 'running');
CREATE INDEX ix_download_jobs_queue ON download_jobs(state, created_at);
CREATE INDEX ix_download_jobs_updated ON download_jobs(updated_at DESC);
CREATE INDEX ix_download_jobs_parent ON download_jobs(parent_job_id);

CREATE TABLE job_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL REFERENCES download_jobs(id) ON DELETE CASCADE,
    sequence INTEGER NOT NULL CHECK (sequence >= 1),
    state TEXT NOT NULL,
    phase TEXT NOT NULL,
    progress_percent REAL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    occurred_at TEXT NOT NULL,
    UNIQUE (job_id, sequence)
);

CREATE INDEX ix_job_events_cursor ON job_events(id);
CREATE INDEX ix_job_events_job ON job_events(job_id, sequence);

CREATE TABLE settings (
    key TEXT PRIMARY KEY CHECK (
        key IN (
            'proxy', 'provider.deezer', 'provider.spotdl',
            'provider.yt_dlp', 'provider.lastfm'
        )
    ),
    public_json TEXT NOT NULL DEFAULT '{}',
    secret_ciphertext BLOB,
    revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
    updated_at TEXT NOT NULL
);

INSERT INTO settings (key, public_json, secret_ciphertext, revision, updated_at) VALUES
    ('proxy', '{"configured":false}', NULL, 1, strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    ('provider.deezer', '{"enabled":true}', NULL, 1, strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    ('provider.spotdl', '{"enabled":true}', NULL, 1, strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    ('provider.yt_dlp', '{"enabled":true}', NULL, 1, strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    ('provider.lastfm', '{"enabled":false,"configured":false}', NULL, 1, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));

CREATE TABLE artwork_stages (
    id TEXT PRIMARY KEY,
    file_relpath TEXT NOT NULL UNIQUE,
    mime_type TEXT NOT NULL CHECK (mime_type = 'image/jpeg'),
    content_sha256 TEXT NOT NULL CHECK (length(content_sha256) = 64),
    size_bytes INTEGER NOT NULL CHECK (size_bytes BETWEEN 1 AND 10485760),
    origin TEXT NOT NULL CHECK (origin IN ('upload', 'url', 'lastfm')),
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    consumed_at TEXT
);

CREATE INDEX ix_artwork_stages_expiry ON artwork_stages(expires_at, consumed_at);

CREATE TABLE api_idempotency (
    scope TEXT NOT NULL,
    key TEXT NOT NULL,
    request_sha256 TEXT NOT NULL CHECK (length(request_sha256) = 64),
    status_code INTEGER NOT NULL,
    response_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    PRIMARY KEY (scope, key)
);

CREATE INDEX ix_api_idempotency_expiry ON api_idempotency(expires_at);

CREATE TABLE media_mutations (
    id TEXT PRIMARY KEY,
    track_id TEXT,
    operation TEXT NOT NULL CHECK (operation IN ('publish', 'edit', 'delete')),
    state TEXT NOT NULL CHECK (
        state IN (
            'prepared', 'files_staged', 'active_files_removed',
            'db_committed', 'finalized', 'rolled_back', 'recovery_required'
        )
    ),
    old_record_json TEXT NOT NULL,
    new_record_json TEXT,
    recovery_json TEXT NOT NULL,
    error_detail TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX ix_media_mutations_recovery
    ON media_mutations(state, updated_at)
    WHERE state NOT IN ('finalized', 'rolled_back');
```

SQLite has no server users and is not exposed outside the containers. The database lives at `${CHILLIFY_DATA_ROOT}/db/chillify.sqlite3`; MP3s and art live below `${CHILLIFY_MUSIC_ROOT}`. API responses never expose relative paths.

### Ordering and duplicate invariants

- Album order: unknown disc/track last, then disc, track, normalized title, ID.
- Artist order: unknown year last, year, normalized album, disc, track, ID.
- Year order: normalized artist, normalized album, disc, track, ID.
- `artist_key` is unpadded base64url of UTF-8 `normalized_artist`. `album_key` is unpadded base64url of UTF-8 `normalized_artist + NUL + normalized_album`. The API decodes and verifies canonical form before querying. Same-named albums by different normalized artists are separate contexts; tracks with an absent album share that artist's deterministic Unknown Album context. A metadata edit may move a track to a different context and make the old derived URL empty.
- Playlist order: `position`, ID. Reorder writes a complete contiguous `0..n-1` list in one transaction.
- Duplicate resolution is exact and ordered: provider/source ID → normalized ISRC → normalized artist/title. Database unique constraints are the final race-safe guard.
- One track may appear at most once in a playlist. One source identity may map to exactly one track.

## 5. API contract

All browser traffic is same-origin under `/api/v1`. JSON uses `snake_case`, UTF-8, RFC 3339 timestamps, and string IDs. Mutations accept `Idempotency-Key`; reusing a key with a different body returns `409`. Mutable records include `revision`, supplied as `If-Match`; stale writes return `409 record_changed`.

### Common envelopes

Success bodies are the resource itself or:

```json
{"items": [], "next_cursor": null}
```

Errors have one stable shape:

```json
{
  "error": {
    "code": "proxy_connection_failed",
    "message": "Could not reach Deezer through the configured proxy.",
    "field": null,
    "retryable": true,
    "request_id": "01...",
    "detail": {"provider": "deezer"}
  }
}
```

`detail` is allowlisted and redacted. Status mapping: `400` malformed/unsupported input, `404` missing resource, `409` duplicate/stale/conflict, `413` art too large, `422` field validation, `423` mutation locked, `502` provider/extractor response, `503` Redis/provider/tool unavailable, `504` outbound timeout.

Idempotency responses are retained for 24 hours in `api_idempotency` and pruned opportunistically. The scope includes method and route family. The request hash prevents one key from authorizing a different body.

### Resource endpoints

| Method and path | Request → response | Screens |
|---|---|---|
| `GET /system/status` | — → local/Redis/tools/providers/storage/degraded status | shell, S11, S12 |
| `GET /events` | `Last-Event-ID` → SSE `job.changed`, `library.changed`, `system.changed` | shell, S11 |
| `GET /profiles` | — → profiles | S1 |
| `POST /profiles` | `{name}` → profile | S1 |
| `GET /library/tracks` | `q, sort, cursor, limit<=100` → local track summaries | S2, S3 |
| `GET /library/artists` | `q, cursor` → artist summaries | S2 |
| `GET /library/artists/{artist_key}` | — → identity + ordered tracks | S6 |
| `GET /library/albums` | `q, cursor` → album summaries | S2 |
| `GET /library/albums/{album_key}` | — → identity + ordered tracks | S7 |
| `GET /library/years` | — → year summaries including `unknown` | S2 |
| `GET /library/years/{year_key}` | — → ordered tracks | S8 |
| `GET /tracks/{id}` | — → complete editable track + sources | S13 |
| `GET /tracks/{id}/stream` | `Range` optional → `audio/mpeg`, ranges, ETag | player |
| `POST /artwork/stages/upload` | multipart image → one-hour artwork stage | S5, S13 |
| `POST /artwork/stages/url` | `{url}` → one-hour artwork stage | S5, S13 |
| `POST /artwork/stages/lastfm` | `{artist,title,album?}` → best-match artwork stage or miss | S5, S13 |
| `PATCH /tracks/{id}` | complete metadata + optional `artwork_stage_id` + `If-Match` → atomically updated track | S13 |
| `GET /tracks/{id}/delete-impact` | — → server-owned playlist count | S15 |
| `DELETE /tracks/{id}` | `If-Match` → `204` | S15 |
| `GET /search/deezer` | `q, limit<=50` → normalized remote candidates + duplicate link | S3 |
| `POST /links/inspect` | `{url}` → detected candidate/review requirement | S4, S5 |
| `POST /downloads` | source/candidate/review + optional `artwork_stage_id` + idempotency → job | S3, S4, S5 |
| `GET /downloads` | `state, cursor` → jobs newest/queue order | S11 |
| `GET /downloads/{id}` | — → job + events | S11 |
| `POST /downloads/{id}/cancel` | version → job | S11 |
| `POST /downloads/{id}/retry` | idempotency → new linked job | S11 |
| `GET /profiles/{profile_id}/playlists` | — → playlist summaries | shell, S9 |
| `POST /profiles/{profile_id}/playlists` | `{name}` → playlist | S16 |
| `GET /playlists/{id}` | — → playlist + ordered tracks | S10 |
| `PATCH /playlists/{id}` | `{name, revision}` → playlist | S16 |
| `POST /playlists/{id}/tracks` | `{track_id, revision}` → playlist | row action |
| `DELETE /playlists/{id}/tracks/{track_id}` | `If-Match` → playlist | S10 |
| `PUT /playlists/{id}/order` | `{track_ids, revision}` → playlist | S10 |
| `GET /settings` | — → masked settings and editable public state | S12 |
| `PATCH /settings/proxy` | proxy URL/null + revision → masked setting | S12 |
| `POST /settings/proxy/test` | saved or supplied proxy → diagnostic result | S12 |
| `PATCH /settings/providers/{provider}` | enabled/credential + revision → masked state | S12 |
| `POST /settings/providers/{provider}/test` | — → diagnostic result | S12 |

Artwork-stage endpoints validate, normalize, and store a JPEG beneath `.chillify/staging/artwork/{stage-id}.jpg`; they do not mutate a track. A stage expires after one hour, is single-use, and is consumed only inside the final track-edit or download-publication transaction. S13 therefore has one Save mutation covering metadata, ID3 artwork, external artwork, path, and database revision. S5 can use the same stage token in its immutable reviewed download request. Expired, missing, or consumed tokens return `409 artwork_stage_unavailable`; periodic/startup cleanup removes unconsumed expired files and rows.

Profiles deliberately have no rename/delete endpoint. Playlists deliberately have no delete endpoint in v1. Favorites have no endpoint. The session queue has no endpoint.

### SSE behavior

FastAPI's native SSE response sends durable job events using `job_events.id` as the event ID. Transient `system.changed` and `library.changed` invalidations have no SSE `id`; therefore the browser's single `Last-Event-ID` cursor belongs exclusively to the durable job-event sequence. On reconnect the server replays retained job events after that ID, emits fresh transient invalidations, and sends current system status. A 15-second comment heartbeat detects dead connections. TanStack Query invalidates affected resources; it never treats an SSE payload as the sole durable copy. If SSE fails, the client uses 5-second job/status polling with a visible reconnecting state.

### Media streaming

`GET /tracks/{id}/stream` resolves a database track to a canonical path beneath the configured music root, refuses symlink/path escape, verifies availability, and delegates one-range responses to Starlette `FileResponse`. It returns `Accept-Ranges: bytes`, correct `206/416`, `Content-Length`, `Last-Modified`, and an ETag derived from revision/size/mtime. nginx buffers neither this response nor SSE. Missing files atomically mark the track `missing` and return `410 track_file_missing`.

## 6. External wire contracts

All outbound HTTP uses one `httpx.Client` factory. If a proxy is saved, it is supplied for every HTTP/HTTPS/SOCKS request and there is no direct fallback client. Timeouts are 5 seconds connect, 15 seconds read, 20 seconds pool/write; at most two retries use bounded exponential jitter for connection resets, `408`, `429`, and `5xx`. Validation, authentication, and `4xx` input errors are not retried.

### Deezer

- Request: `GET https://api.deezer.com/search?q={query}&limit={1..50}`.
- Accepted fields per `data[]`: `id`, `title`, `duration`, optional `isrc`, `artist.id/name`, `album.id/title/cover_xl|cover_big|cover_medium`.
- Pagination beyond the requested first page is ignored in v1.
- `error` objects, invalid JSON, absent `data`, and HTTP failures map to typed provider errors.
- Audio acquisition uses yt-dlp search target `ytsearch1:{artist} {title}`. Deezer never supplies audio.

### Last.fm

- Request: `GET https://ws.audioscrobbler.com/2.0/?method=track.getInfo&api_key=…&artist=…&track=…&autocorrect=1&format=json`.
- Accepted fields: corrected `track.name`, `track.artist.name`, optional `track.album.title`, `track.album.image[]`, `track.mbid`, and duration.
- Only requested missing fields are merged. An API `error`, no track, empty image, timeout, or missing key becomes a non-fatal enrichment warning.

### yt-dlp

- The adapter uses the injected Python API, never `shell=True`.
- Inspect options: `quiet`, `skip_download`, `noplaylist`, validated proxy; only a single `youtube`/`youtu_be` video extractor result is accepted.
- Acquire options: `format="bestaudio/best"`, `noplaylist=True`, same proxy, a task-local output template, FFmpeg `ExtractAudio` with preferred codec `mp3`, and progress/postprocessor hooks.
- For direct YouTube, the inspected canonical video URL is acquired. For Deezer, `ytsearch1:` is used and the first candidate must pass title/artist normalization plus duration tolerance of `max(10 seconds, 15%)` when both durations exist. A mismatch fails clearly; it never silently downloads a weak match.
- Hooks emit real downloaded-byte percentages when totals exist, phase-only events otherwise, and consult the cancellation flag. The worker terminates the current process group/call, removes the task workspace, and marks cancelled.

### SpotDL

- SpotDL runs as an argument-vector subprocess in its own process group, with one canonical open.spotify.com track URL, task-local output, MP3 format, sync disabled, and the saved proxy exported only to the child.
- JSON/metadata inspection output is normalized to `TrackCandidate`; album/playlist/episode entities are rejected before invocation.
- stdout/stderr are captured by the adapter, parsed into phase/progress where stable, bounded to 64 KiB in job detail, redacted, and never streamed raw to the browser.
- Exit zero is insufficient: exactly one valid MP3 must exist in the task workspace and pass FFprobe/Mutagen validation.

Exact CLI flags are contained in one adapter contract test against `spotdl@4.5.2`; the domain and worker do not know them. This isolates expected SpotDL CLI churn.

### Artwork

Artwork URLs are fetched through the same proxy policy with redirects limited to three. Each hop must be HTTP(S), pass host/IP policy, declare or stream no more than 10 MiB, and decode as JPEG/PNG/WebP in Pillow. Images are orientation-corrected, stripped of active metadata, converted to sRGB JPEG, and bounded to 1600×1600 before ID3 embedding and per-track disk storage.

## 7. Durable job state machine

```text
accepted → queued → running/downloading → converting → enriching
         → tagging → organizing → completed
                     └──────────────► failed
queued/running ─────────────────────► cancelled
interrupted running → queued/restarted → running
failed/cancelled --retry(new linked job)--> queued
```

The stored state remains one of the five durable values in the DDL. API job representations add a derived `display_state`: `retrying` when a queued job has `parent_job_id`, and `restarted` when a queued job has `restart_count > 0`. This exposes every approved UI state without introducing ambiguous persistence transitions.

1. The API validates provider state, Redis health, supported entity, and duplicate signals.
2. In one SQLite `BEGIN IMMEDIATE` transaction it inserts the job and its first event. The partial unique index prevents duplicate active requests.
3. After commit it sends the job ID to Celery. Publish failure leaves the durable job queued and returns `503 queue_unavailable`; reconciliation publishes it later.
4. The worker accepts only a job ID, acquires a per-job DB lease by version/state transition, and refreshes `heartbeat_at`/`lease_expires_at` during work. It reconstructs all input from SQLite. Celery messages contain no credentials or candidate payload.
5. Worker concurrency and prefetch are both one. Late acknowledgement is used; the database lease/state remains authoritative.
6. Every phase update and event insertion occurs in one transaction. Progress is monotonic within a phase; unknown progress remains `null`.
7. A successful job publishes the final track and source rows in the same transaction that marks the job complete.
8. On API/worker startup and Redis reconnection, reconciliation finds queued jobs without live dispatch and running jobs whose worker heartbeat/lease is stale. Stale workspaces are removed, running jobs become queued with phase `restarted`, `restart_count` increments, and they are republished oldest-first.
9. Cancel sets `cancel_requested_at`. The worker checks between phases and in downloader hooks, stops the active process group, cleans the workspace, and commits `cancelled`. A queued cancel never dispatches.
10. Retry creates a new job linked by `parent_job_id`; state chronology is immutable except for the approved metadata anonymization when a completed track is permanently deleted.

Celery retry is reserved for broker delivery failures. Application/provider retry is controlled in the adapter and recorded in the same job; Celery must not create parallel hidden attempts.

## 8. Media organization and crash consistency

### Layout

```text
${CHILLIFY_MUSIC_ROOT}/
├── Music/{Artist}/{Album}/{NN - Title}.mp3
├── Artwork/{track-id}.jpg
└── .chillify/
    ├── work/{job-id}/
    ├── staging/{mutation-id-or-artwork-stage-id}/
    ├── recovery/{mutation-id}/
    └── locks/
        ├── library.lock
        └── tracks/{track-id}.lock

${CHILLIFY_DATA_ROOT}/
└── db/chillify.sqlite3
```

Artist/album/title components are Unicode-normalized, stripped of control/traversal/reserved characters with Pathvalidate, trimmed, capped by UTF-8 byte length, and replaced by deterministic Unknown values if empty. Track prefixes use two digits through 99 and the full number above that. Path collision never overwrites: exact duplicates are rejected; nonduplicate sanitized collisions append a short track-ID suffix.

Every publish, edit, or deletion that calculates or changes a managed path acquires the cross-process `library.lock`. Edit/delete then acquire the target track lock; the fixed order is always library then track, and no code may invert it. The locks cover final duplicate/path rechecks through filesystem and database commit/recovery-state update. They are advisory `filelock` locks on the shared mounted filesystem with bounded wait; timeout maps to `423 mutation_locked`.

### Download commit

The worker writes only inside `.chillify/work/{job-id}`, validates the decoded MP3, composes final tags/art, fsyncs files and directories, and then takes `library.lock`. It rechecks duplicates and inserts a `media_mutations(operation='publish', state='prepared')` recovery record before atomically moving media to unused final paths on the same mount. One DB transaction then inserts track/source rows, marks the job complete, consumes any artwork stage, and sets the mutation `db_committed`; final cleanup removes the journal row. A normal DB failure removes the newly moved files before releasing the lock. Startup recovery removes an orphan publish whose track row is absent or finalizes one whose track/job transaction committed, then removes abandoned non-active workspaces.

### Metadata edit

Edits are serialized by `library.lock`, then the track file lock, plus optimistic `revision`.

1. Validate the complete intended record and optional unconsumed artwork stage, then calculate unused final paths.
2. Insert `media_mutations(prepared)` containing old/new records and recovery paths.
3. Copy the original MP3 into same-filesystem staging, rewrite all ID3 text/art tags, validate, fsync, and mark `files_staged`.
4. Preserve recovery hard links, atomically place staged MP3/art at intended paths, and mark the track `mutating`.
5. In one DB transaction update every track field/path/revision, consume the artwork stage if supplied, and set mutation state `db_committed`.
6. Remove obsolete active paths/recovery links, fsync directories, and mark `finalized`.

If any pre-commit step fails, staged files are removed and the old record/path remains authoritative. If DB commit fails after placement, recovery links restore the old paths and the new files are removed. Startup recovery finishes `db_committed` cleanup and rolls earlier states back conservatively. No old path is removed until the new record can play.

### Two-stage permanent deletion

Deletion honors the required order—active disk media first, then all metadata—without giving up rollback:

1. Under `library.lock` and then the track lock, create and fsync hard-link recovery snapshots of MP3 and art on the same filesystem; record `prepared`.
2. Unlink the active MP3/art paths and fsync their directories; record `active_files_removed`. The file is now deleted from its managed location.
3. In one DB transaction anonymize every completed download job linked to this track by replacing `source_ref`, `dedupe_key`, `request_json`, `candidate_json`, error detail, and event payload metadata with nonidentifying deleted-track values. Then delete the `tracks` row; `result_track_id` becomes null, foreign keys remove sources and all playlist entries, durable job phase/timestamps/events remain, and the independent mutation journal becomes `db_committed`.
4. Remove recovery links and the deletion journal row. The API emits `library.changed`; browser queues remove the track and the player advances or stops.

If step 3 fails, the recovery links are linked back to the original active paths and the old database record remains authoritative. After a crash, `active_files_removed` with a live track rolls back; `db_committed` finalizes recovery deletion and removes its journal. The impact endpoint counts server-owned playlist references; S15 combines that with current-track and queue occurrences derived from the browser's Zustand store. A missing active file skips its snapshot but still permits confirmed metadata cleanup. A completed deletion retains only an anonymous job-history shell (provider, phases, status, timestamps); it retains no track identity, source locator, candidate/request metadata, source record, playlist entry, artwork, tag, path, or recovery metadata.

## 9. Frontend architecture and UX mapping

`AppProviders` mounts the router, TanStack Query, active-profile session, SSE bridge, theme, and Sonner once. `PersistentShell` and `PersistentPlayer` sit above route outlets; route transitions cannot remount the `<audio>` element. Zustand's player store contains track IDs and ordered queue entries, not server records; current metadata is selected from Query cache by ID.

### Component hierarchy

```text
AppProviders
├── S1 ProfileChooser
│   └── Card + Field/FieldGroup + Input + Button + Alert + Skeleton
└── PersistentShell (S2–S12)
    ├── AppSidebar
    │   └── Sidebar + DropdownMenu + NavigationMenu + Button + Badge
    ├── TopBar
    │   └── Button + Tooltip + Breadcrumb + Alert
    ├── RouteOutlet
    │   ├── S2 LibraryPage
    │   │   └── Tabs + Select + TrackTable/ContextGrid + Empty + Skeleton
    │   ├── S3 SearchPage
    │   │   └── Field + Input + Button + Separator + TrackTable + ResultCards
    │   ├── S4 AddLinkDialog
    │   │   └── Dialog + Field + Input + Alert + Button
    │   ├── S5 YouTubeReviewDialog
    │   │   └── Dialog + FieldGroup + Input + ArtworkPicker + Button
    │   ├── S6/S7/S8 ContextPage
    │   │   └── AspectRatio + Button + TrackTable + Empty + Skeleton
    │   ├── S9 PlaylistsPage
    │   │   └── Button + Card + Empty + Skeleton
    │   ├── S10 PlaylistPage
    │   │   └── Button + Sortable TrackTable + DropdownMenu + Alert
    │   ├── S11 DownloadsPage
    │   │   └── Alert + Progress + Badge + Accordion + Button + Empty
    │   └── S12 SettingsPage
    │       └── Field/FieldGroup + Input + Switch + Card + Alert + Button
    ├── S13 TrackEditorDialog
    │   └── Dialog + Field/FieldGroup + ArtworkPicker + Alert + Button
    ├── S14 QueueDrawer
    │   └── Sheet + sortable rows + Button + ScrollArea + Empty
    ├── S15 DeleteTrackAlertDialog
    │   └── AlertDialog + Alert + Button
    ├── S16 PlaylistEditorDialog
    │   └── Dialog + Field + Input + Button
    ├── GlobalJobIndicator
    │   └── Button + Badge + Progress + Tooltip
    └── PersistentPlayer
        └── Button + Slider + Tooltip + AspectRatio
```

`TrackTable`, `TrackRow`, `ContextGrid`, `ArtworkPicker`, `ResultCards`, `GlobalJobIndicator`, and `PersistentPlayer` are domain compositions, not replacement primitives. They must be built exclusively from inspected Shadcn components unless a documented registry gap exists. The only non-Shadcn interaction dependency is dnd-kit for accessible sortable behavior; its visual controls are Shadcn Buttons/rows.

### State ownership

- Query keys include active `profile_id` only for playlists; library/jobs/settings are global.
- Profile switch pauses and clears the audio source/queue before invalidating profile queries.
- Local and Deezer search are separate queries. Local search reacts to input; Deezer query is disabled until the explicit button supplies a submission token.
- Remote candidates carry `playable=false`; no component renders a Play action for them.
- S13 artwork selection creates a temporary stage only; its single Save sends complete metadata and the optional stage ID in one atomic `PATCH`. S15 merges API playlist impact with current-track/queue impact selected from the browser player store.
- Completed download rows whose tracks were permanently deleted render the anonymous identity “Deleted track”; their provider, phase, state, and timestamps remain inspectable.
- Route errors are bounded per viewport. Provider/Redis degradation uses persistent Alert; form errors use FieldError; brief success uses Sonner.
- Player errors mark missing/unplayable entries, skip to the next candidate, and invalidate the affected track.
- Motion is limited to opacity/transform/progress transitions, disabled with reduced motion, and never delays input.
- Desktop breakpoints are release scope. Narrow screens remain functional but are not mobile-optimized.

## 10. End-to-end flow traces

### F1 — Kernel

| UX step | Contract and state transition |
|---|---|
| S1 select/create | `GET/POST /profiles`; client sets session profile and loads profile playlists |
| S3 local search | `GET /library/tracks?q=` only; no outbound adapter |
| S3 explicit Deezer | `GET /search/deezer`; Deezer adapter returns normalized non-playable candidates |
| Download result | `POST /downloads`; duplicate chain runs, durable `queued` job/event is committed and dispatched |
| S11 progress | `/events` replays queued → downloading → converting → enriching → tagging → organizing → completed |
| S2 new track | `library.changed` invalidates local queries; stream endpoint is now available |
| S13 correct | artwork is staged if changed; one `PATCH /tracks/{id}` atomically consumes it with metadata under the recoverable edit/revision contract |
| S16/S2/S10 playlist | create playlist, add track, fetch ordered detail |
| S10 play | player store replaces its session queue; `<audio>` loads `/tracks/{id}/stream` |
| S2–S12 navigate | route outlet changes; shell/audio/store stay mounted |
| service restart | mounted SQLite/media restore track/profile/playlist; browser session queue intentionally starts empty |

### F2 — Reviewed YouTube

`POST /links/inspect` validates the host/entity and uses yt-dlp metadata-only inspection through the proxy. S5 edits stay client-side; an optional replacement image first becomes a short-lived artwork stage. `POST /downloads` stores reviewed metadata and the optional stage ID in immutable `request_json`. The worker acquires only that canonical video, applies reviewed values before optional Last.fm gaps, atomically consumes the staged art during publish, cleans its workspace on cancel/failure, and commits one organized track. S2 updates through `library.changed`.

### F3 — Browse/play context

S2 calls artist/album/year collections; S6–S8 receive server-ordered track arrays. Play copies that exact ID order into the player store. S14 reorders/removes the browser-only queue with dnd-kit. Route changes never touch the store or audio element. A refresh/profile switch clears both.

### F4 — Failure/recovery

Provider/proxy errors use the common envelope while local Query data/player remain active. S12 updates/tests the global proxy; the HTTP factory either uses it or fails closed. Redis health in `/system/status` disables download/retry actions. Reconnection reconciliation resets stale running jobs to queued/restarted and publishes durable events. Cancel mutates the current job; retry creates a new linked job.

## 11. Error strategy

Domain exceptions are closed, typed values: validation, unsupported entity, duplicate, record changed, mutation locked, missing media, provider disabled, proxy configuration/auth/connection/timeout, provider response, extractor mismatch, queue unavailable, tool unavailable, disk full/unwritable, and internal.

- Infrastructure translates library/process exceptions into domain exceptions at its boundary.
- API middleware assigns `request_id`, maps known exceptions to the common envelope, and logs unexpected failures once.
- Worker catches at the task boundary, redacts/bounds diagnostic detail, cleans temporary state, commits a failed/cancelled event, and logs with `job_id`.
- No handler exposes a stack trace, command line with credentials, raw provider body, local absolute path, encryption key, proxy password, or Last.fm key.
- Warnings are first-class job event payloads. Optional Last.fm failure can coexist with `completed`.
- UI copy states the failed action and next step. It never claims rollback/completion before the durable transition arrives.
- Logging failures must not fail application work. Rich output has no file sink or remote dependency.

## 12. Configuration and secret handling

Deployment configuration is validated at process startup:

| Environment variable | Required/default | Rule |
|---|---|---|
| `CHILLIFY_BIND_PORT` | `8787` | host port 1–65535 |
| `CHILLIFY_DATA_ROOT` | required | absolute mounted writable normal filesystem path |
| `CHILLIFY_MUSIC_ROOT` | required | absolute mounted writable normal filesystem path |
| `REDIS_URL` | required for acquisition | `redis://`/`rediss://`; dedicated DB/key prefix recommended |
| `CHILLIFY_REDIS_PREFIX` | `chillify:` | nonempty, no whitespace |
| `CHILLIFY_SECRET_KEY` | required | URL-safe 32-byte Fernet key supplied by operator |
| `CHILLIFY_UID` | `1000` | positive host UID that owns/writes both mounted roots |
| `CHILLIFY_GID` | `1000` | positive host GID that owns/writes both mounted roots |
| `CHILLIFY_LOG_LEVEL` | `INFO` | standard logging level |
| `CHILLIFY_ALLOWED_ORIGINS` | same-origin only | explicit LAN origins only if direct API access is enabled |

Compose contains `web`, `api`, and `worker`; it contains no Redis service. API and worker receive identical, explicit bind mounts for data and music. The worker runs Celery with concurrency/prefetch one. Containers run as `CHILLIFY_UID:CHILLIFY_GID`, use read-only root filesystems where tool behavior permits, and have only their required writable mounts/tmpfs. A one-shot preflight reports the exact path and expected UID/GID, then fails before migration if either mounted root is absent, not a normal filesystem, or not writable by that identity.

Application Settings store provider enabled flags and the optional proxy/Last.fm key. The initial migration enables Deezer, SpotDL, and yt-dlp, and disables Last.fm until a key is configured. A missing required provider settings row after migration is configuration corruption: that provider is disabled, Settings shows a repairable error, and no implementation-specific fallback is guessed. Secrets are encrypted with Fernet before SQLite; GET returns only `configured: true/false` and masked proxy username/host. A blank credential on PATCH means “unchanged”; explicit `clear_secret: true` removes it. The key is never stored in SQLite, image, Compose file, or logs. `.env.example` names the required key and includes a safe generation command; startup fails with a named error if it is missing, malformed, or cannot decrypt existing settings.

## 13. Threat model

The accepted trust boundary is explicit: there is no authentication, authorization, or TLS. Anyone who can reach the LAN endpoint can download, edit, permanently delete shared tracks, inspect named playlists, and change proxy/provider settings. The UI states this on S1 and Settings; operators must bind/firewall Chillify to a trusted LAN only.

| Threat | Control |
|---|---|
| command injection through URLs/tags | no shell invocation; argument vectors/Python APIs; strict supported-host/entity parsing; metadata never becomes an option |
| path traversal/symlink escape | normalized path components, canonical-root containment checks, `O_NOFOLLOW`/lstat checks where available, no absolute paths from requests |
| SSRF through artwork/provider URL | provider host allowlist; artwork HTTP(S) only; resolve every redirect; reject loopback, link-local, multicast, and private targets; size/time limits |
| decompression/image bomb | 10 MiB transfer cap, Pillow pixel limit, decode in worker, normalized output |
| malicious/invalid media | task-local workspace, FFprobe/Mutagen validation, bounded filenames, no direct serving until commit |
| secret leakage | encryption at rest, response masking, Rich logging filter, bounded allowlisted diagnostics, sentinel test |
| Redis message tampering | dedicated prefix/DB, job-ID-only messages, worker reloads authoritative DB and validates state; Redis should not be exposed beyond host |
| CSRF/cross-origin mutation | same-origin nginx routing, no permissive CORS, reject non-JSON mutation content except artwork multipart, Origin validation |
| LAN denial of service | request body/query limits, one worker, bounded search/page sizes, outbound timeouts, nginx connection/body limits |
| race/corruption | SQLite WAL/full sync, revision checks, unique constraints, file locks, recovery journal, same-filesystem atomic operations |
| unsupported copyrighted acquisition | personal household scope and provider/tool terms remain operator responsibility; UI does not imply rights |

The proxy itself may observe credentials and traffic; this is an operator-selected trust decision. Proxy failure never falls back to direct network access.

## 14. Verification and release gates

### Automated

- Backend unit tests cover normalizers, validation, duplicate precedence, queue state machine, ordering, error mapping, redaction, and provider interfaces.
- Provider contract tests replay checked-in Deezer/Last.fm/yt-dlp/SpotDL fixtures, malformed responses, proxy failures, no-progress behavior, and cancellation.
- SQLite integration tests run real migrations, constraints, concurrency/revision conflicts, restart reconciliation, and every edit/deletion recovery stage.
- Frontend tests use MSW for local-first search, remote distinction, job feedback, form preservation, Shadcn dialog focus return, profile/session clearing, and player continuity across route renders.
- Playwright runs the F1 kernel in Chromium, the playback/navigation/seek/modal smoke in Firefox, and axe checks for every state explicitly enumerated under S1–S16, including loading, empty, validation, unavailable, stale/reconnecting, degraded, recovery, failure, and success states where applicable.
- Compose canaries prove mounted persistence after container recreation, byte-range seeking, serial concurrency, Redis-offline local use, Redis reconnection, proxy fail-closed behavior, and no files in container writable layers.

### Numeric gates

The release script seeds 500 tracks and maps every PRD budget to a named check:

| PRD gate | Release check |
|---|---|
| NFR-1 | 20 local searches; rendered p95 ≤300 ms |
| NFR-2 | 20 cached S2–S12 transitions; p95 ≤500 ms |
| NFR-3 | 10 representative MP3 starts per browser; p95 ≤1 second |
| NFR-4 | 20 durable job transitions; server-to-render lag ≤2 seconds |
| NFR-5 | 20 route transitions while playing; zero pause/end/source-reset/backward-time events |
| NFR-6 | container recreation; 100% profile/playlist/track/settings/job persistence |
| NFR-7 | success plus an injected failure at every edit/delete stage; zero database/file/tag/art mismatch |
| NFR-8 | every state enumerated under S1–S16; WCAG 2.2 AA, zero critical/serious automated findings, manual keyboard/focus/contrast/reduced-motion pass |
| NFR-9 | F1 in current Chromium plus playback/navigation/seek/queue/modal/download smoke in current Firefox |
| NFR-10 | internet and Redis disconnected; 100% of specified local browse/search/play/playlist reads remain usable |
| NFR-11 | sentinel proxy/key values; zero occurrences in API responses, UI errors, or Rich stdout logs |
| NFR-12 | completed media/data inspection and container recreation; 100% outside container writable layers |

## 15. Operational behavior

- `docker compose up -d` runs Alembic upgrade as a one-shot dependency before API/worker health becomes ready.
- API readiness requires valid config, migrated SQLite, and writable mounted paths. Redis/provider failure affects degraded status, not API readiness.
- Worker readiness requires valid paths/tools and Redis; its loss disables acquisition only.
- Health endpoints are local process checks; provider tests occur only on user action or bounded periodic status refresh.
- Back up by stopping API/worker or using SQLite's online backup API, then copy both data and music roots together and separately preserve `.env`/`CHILLIFY_SECRET_KEY` with restricted permissions. Restore all three as one set; a different key fails startup rather than discarding encrypted settings.
- Rich stdout logs are the sole logging system. Docker log rotation is an operator concern and is documented in deployment instructions.
- Database/job event retention is unlimited at the v1 scale. Completed task workspaces are deleted immediately; failed diagnostics are bounded in SQLite.

## 16. Forward constraints

- **M2 discovery/bulk:** preserve `TrackCandidate`, provider capability interfaces, source identity uniqueness, and parent/child job linkage so grouped results and batch parents can be added without changing completed-track semantics.
- **M3 existing library:** reserve the `track_sources` provider vocabulary for an `import` source and keep media mutation/reconciliation behind protocols so unmanaged-file policies can be added without weakening current ownership rules.
- **M4 playback/clients:** keep playback queue state behind a frontend store boundary and media endpoints stateless so persisted queues, mobile layouts, shuffle/repeat, and advanced playback can evolve without coupling them to acquisition.

## Decision log

### 2026-07-20 — Independent review arbitration

### 2026-07-20 — Dependency audit tooling pinned

`./scripts/verify.sh` must fail on a vulnerable dependency in either stack. The frontend uses `npm audit`, which needs no new package; the backend had no equivalent in the pinned plan, so `pip-audit@2.10.1` joins the dev group. It is verification tooling in the same category as ruff and mypy: dev-only, never imported by the application, and absent from the runtime image.

### 2026-07-20 — SpotDL isolated behind a subprocess boundary

The pinned dependency plan was unsatisfiable: `spotdl@4.5.2` — the latest release, and every `4.x` — requires `fastapi<0.104` and `uvicorn<0.24`, while the API is pinned to `fastapi@0.139.2` and `uvicorn@0.51.0`, which §5's native SSE contract depends on. Downgrading the API to SpotDL's ceiling was rejected as a 2023-era pin on the whole HTTP surface; dropping SpotDL was rejected as a scope cut of spec'd Spotify-link acquisition. SpotDL is installed into its own isolated environment and invoked as a pinned argument-vector subprocess behind the unchanged provider protocols. This affects Chunk 13 / Task 16 only; that chunk requires a scoped re-gate before implementation. Chunks 1–12 are unaffected because no earlier chunk imports or invokes SpotDL.

### 2026-07-20 — Independent review arbitration

Approved: browser-owned deletion impact; reusable artwork staging with one atomic final mutation; anonymous job-history shells after deletion; derived collision-safe artist/album keys; exhaustive documented-state accessibility coverage; clock-bound year validation; seeded provider defaults; job-only SSE cursors; one ordered cross-process library/track locking protocol; and explicit secret-key/UID/GID deployment and backup contracts.

### 2026-07-21 — TypeScript pinned to the 5 line

The pinned `typescript@7.0.2` made the pinned typed-API-client plan unbuildable: `openapi-typescript@7.13.0` — the latest release — generates `src/api/generated.ts` through the TypeScript 5 compiler API (`ts.factory`), which the native TypeScript 7 port does not expose, and npm refuses to nest a peer dependency to give the generator its own copy. Downgrading the generator was not possible (no release supports 7), and hand-writing the client was rejected as reimplementing what the dependency plan assigns to a package. The root pin therefore moves to `typescript@5.9.3`. Every other pinned dev tool — shadcn, msw, vitest — already peers against a 4.x/5.x range, so nothing else changes. Application code and `./scripts/verify.sh` typecheck unchanged.

### 2026-07-21 — Transitive js-yaml override

`@redocly/openapi-core`, reached only through the build-time `openapi-typescript` generator, pins `js-yaml@4.2.0` exactly; that version carries GHSA-52cp-r559-cp3m, so `./scripts/verify.sh`'s `npm audit --audit-level=high` fails and `npm audit fix` cannot resolve it in range. A scoped `overrides` entry lifts that transitive copy to the patched `js-yaml@4.3.0` within the same major. No `js-yaml` reaches the browser bundle.
