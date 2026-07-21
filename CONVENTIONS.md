# Chillify Conventions

## Machine-enforced baseline

Task 0 configures these checks; prose does not duplicate them:

- TypeScript strict mode, no unchecked indexed access, no implicit override, and generated API types excluded from manual edits.
- Biome owns frontend formatting, import ordering, unused code, accessibility lint, and banned raw console calls.
- Ruff owns Python formatting/imports/lint; mypy is strict for `src/chillify`; pytest rejects unregistered markers and warnings not explicitly filtered.
- Dependency lock drift, raw color literals outside `frontend/src/styles/tokens.css`, and direct primitive creation outside `frontend/src/components/ui/` fail `./scripts/verify.sh`.
- Backend domain imports of FastAPI, SQLAlchemy, Celery, HTTPX, provider packages, or filesystem modules fail an architecture-boundary check.
- Every migration, generated Shadcn file, and OpenAPI generation result is committed; generated files are never hand-edited.

## Names and types

- Python modules/functions/variables use `snake_case`; classes/protocols/errors use `PascalCase`; constants use `UPPER_SNAKE_CASE`.
- TypeScript files exporting React components use `PascalCase.tsx`; hooks use `useCamelCase.ts`; stores/services/helpers use `camelCase.ts`; tests mirror the subject name.
- API JSON, database columns, event fields, and error codes use `snake_case`. Routes use plural nouns; actions are subresources only where CRUD is insufficient.
- Domain IDs are distinct typed values at boundaries, not interchangeable bare strings. UTC timestamps and normalized keys are constructed by domain helpers.
- Boolean names state the positive condition (`is_playable`, `is_configured`). Avoid generic `data`, `utils`, `manager`, `handler`, and `service` when a domain verb/noun is available.

## Folder and dependency rules

- `domain` defines entities/value objects/protocols and imports no infrastructure. `application` owns use cases/transactions and depends on domain protocols. `infrastructure` implements protocols. `api` and `worker` translate transport into application calls.
- Frontend feature folders own route assemblies, queries, and domain compositions. Shared Shadcn source lives only in `components/ui`; shared nonprimitive state presenters live in `features/shared`.
- Cross-feature imports go through a feature's explicit public module; never reach into another feature's internal file. Player code may depend on API track summaries but never route components.
- A new provider implements existing capability protocols and registers only in the composition root. Provider response types do not escape its adapter.
- Package-before-custom is mandatory. If ARCHITECTURE assigns a capability to Shadcn, TanStack Query, Zustand, dnd-kit, Mutagen, Pillow, HTTPX, Tenacity, Pathvalidate, Filelock, Celery, or another approved package, reimplementing it is a review finding.
- Before any frontend primitive is written, run `npx shadcn@latest search @shadcn -q "<need>"` and inspect the result. Custom primitive source requires an approved ARCHITECTURE Decision log entry.

## Errors, logging, and state

- Domain code raises a closed typed Chillify error with stable code, safe message, retryability, and allowlisted context. Infrastructure translates third-party exceptions once; API/worker boundaries map/log once.
- Never catch `Exception` below a process/request boundary. Cleanup uses `finally`; an expected partial failure is represented explicitly, not logged and ignored.
- Public errors contain no absolute path, provider body, command line, proxy credential, API key, ciphertext, or traceback. Unexpected details remain in redacted Rich stdout under request/job ID.
- Use `logging.getLogger(__name__)` with structured `extra`; never `print`, add file sinks, or log the same failure at multiple layers.
- SQLite/job/filesystem state is authoritative only after its documented transaction/recovery transition. UI never invents progress or treats toast/SSE/cache state as durable.
- Frontend server state belongs to TanStack Query; browser playback/session state belongs to Zustand; transient form state belongs to React Hook Form. Do not mirror one state across stores.

## Test strategy

| Tag | Owns | Harness |
|---|---|---|
| `[unit]` | pure normalization, ordering, validation, reducers, error mapping, component state | pytest; Vitest + Testing Library |
| `[integration]` | SQLite migrations/repositories, real mounted temp files, mutation recovery, Celery/Redis seam, FastAPI routes, React+MSW feature integration | pytest; Vitest + MSW |
| `[contract]` | OpenAPI shape, provider protocol shared suite, sanitized wire fixtures, subprocess argument/output contract, scripts' fail-closed interface | pytest + respx/injected doubles; OpenAPI TypeScript generation |
| `[e2e@gate-N]` | behavior observable only in the running production composition, browser audio/navigation, degradation, accessibility, numeric NFRs | Playwright Chromium/Firefox + axe; Docker Compose |

- Tests use Arrange–Act–Assert, one behavioral reason to fail, deterministic clocks/UUIDs, and disposable paths. Assert public behavior and durable state; do not mock the subject or inspect private calls unless the call itself is the contract.
- Provider tests never need live network. Each production and fixture adapter runs the same protocol suite; sanitized fixtures cover success, malformed, timeout, proxy, cancellation, and no-progress cases.
- Every bug fix starts with a failing test at the lowest layer that reproduces it. Every persistence mutation tests success plus each documented injected failure/recovery stage.
- Gate tests use the unchanged production Compose entry point and `.gate/` safety checks. A gate-only application composition is forbidden.
- Canonical verification is `./scripts/verify.sh`; focused commands may run during development, but a chunk is complete only when its relevant tags and the full static checks pass.

## Running the app

- Production entry point, for household use and every gate: `docker compose --env-file <env> up --build -d`. With a repository `.env` the `--env-file` flag is omitted. Compose applies the Alembic migration as a one-shot service; the API and worker do not start until it succeeds.
- Disposable environments come from `./scripts/gate/prepare.sh <name> [production|gate]`, which writes `.gate/<name>/` and nothing outside it. Launch with `docker compose --env-file .gate/<name>/.env up --build -d`.
- Boot smoke test: `GET /api/v1/system/health` returns `{"status":"ready"}` and `GET /api/v1/system/status` reports database, storage, Redis, tool, and provider state. Readiness and degradation are separate: Redis or tool loss degrades acquisition and never fails readiness.
- Local development without containers: `cd backend && uv run uvicorn chillify.api.main:app` and `cd frontend && npm run dev`. The dev server proxies `/api` and `/media` so browser code has no environment-specific base URL.
- Canonical verification is `./scripts/verify.sh` (`--fast` skips the build and dependency audits). It is fail-closed: a missing tool is a failure, never a skip.
- The frontend lock is validated with the npm inside the web image's build stage, not the developer's npm, and `docker` is therefore required for that step. Different npm versions disagree about which transitive wasm dependencies a lock must record, so validating with the local one let a lock that could not build the production image report green. Regenerate the lock the same way — in that image — rather than with a host `npm install`.
- Implementation batches run 2 tasks per session, flushed at each demo gate.

## Commits and reviews

- Commit one coherent chunk/task outcome using Conventional Commits: `type(scope): imperative summary`; allowed types are `build`, `chore`, `docs`, `feat`, `fix`, `refactor`, and `test`.
- Do not mix generated dependency/component churn with unrelated behavior. Schema changes include migration and rollback/recovery tests in the same commit.
- Reviews check contract traceability, package reuse, lock/transaction boundaries, secret/path redaction, degraded local behavior, Shadcn state/accessibility, and evidence for every acceptance tag.
