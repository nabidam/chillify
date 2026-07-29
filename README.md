# Chillify

A downloader-first, local music library for one trusted household. Chillify
runs on one Arch Linux host, serves desktop browsers over the LAN, stores all
durable application and media data on mounted local disk, and uses the
operator's existing Redis instance only for background-job transport. See
`ARCHITECTURE.md` for the full architectural contract, `DESIGN.md`/`UX.md` for
product and interaction design, and `CONVENTIONS.md` for the machine-enforced
and reviewed engineering conventions this repository holds itself to.

## Running it

Copy `.env.example` to `.env` and fill in the mounted roots, Redis URL, and
secret key (`.env.example` documents every value, including how to generate
the Fernet secret key). The example Redis URL uses `host.docker.internal` so
containers reach the Redis instance on the Docker host. Then, from the
repository root:

```sh
docker compose up --build -d
```

There is deliberately no Redis service in the production composition:
Chillify reaches the operator's own Redis through `REDIS_URL`. Losing it
degrades background acquisition only; the library itself stays readable.

Compose applies the Alembic migration as a one-shot `migrate` service; `api`
and `worker` do not start until it succeeds, so no process ever serves an
unmigrated database. On Linux, all three backend services receive the
`host.docker.internal` host-gateway alias used by the example Redis URL and
operator-configured host proxies.

Boot smoke test:

```sh
curl http://localhost:8787/api/v1/system/health   # {"status":"ready"}
curl http://localhost:8787/api/v1/system/status   # database, storage, Redis, tool, provider detail
```

Readiness and degradation are reported separately: Redis or tool loss
degrades acquisition and never fails readiness.

### Local development without containers

```sh
cd backend && uv run uvicorn chillify.api.main:app
cd frontend && npm run dev
```

The dev server proxies `/api` and `/media`, so browser code never needs an
environment-specific base URL.

## Verifying a change

```sh
./scripts/verify.sh          # every check: lint, format, types, tests, boundaries, secrets, build, audits
./scripts/verify.sh --fast   # skips the production build and dependency audits
```

`verify.sh` is fail-closed: a missing required tool is a failure, never a
silently skipped step.

## Disposable environments

Every gate and every canary in this repository runs against a disposable
environment created beneath the repository's own `.gate/` tree, never against
household configuration or data:

```sh
./scripts/gate/prepare.sh <name> [production|gate]
```

`production` mode brings up the unchanged production composition with real
adapters against a disposable root — no fixture overlay, no gate Redis
namespace. `gate` mode additionally seeds deterministic fixture payloads
(`./scripts/gate/seed.sh <name> <scenario>`) and requires
`deploy/compose.gate.yaml` overlaid on top of `compose.yaml`. Either way,
`./scripts/gate/cleanup.sh <name>` removes only that environment's own tree.

### The production-composition canary

```sh
./scripts/production_canary.sh --env-file .gate/<name>/.env [--no-live-success]
```

Brings up the *unchanged* production Compose entry point against a disposable,
`production`-mode environment and proves it resolves the real provider, tool,
Redis, SQLite, and media implementations — reporting each one — before any
deterministic fixture is ever mounted. It refuses an env file that is not
beneath the repository's own `.gate/` tree, refuses one that names a
household storage root even if the file itself sits under `.gate/`, and
refuses one that declares gate mode: this canary proves production, not a
gate. A live outbound reachability check is part of the proof; without
`--no-live-success` a reachability failure is a canary failure with no silent
fallback. Pass `--no-live-success` only where guaranteed egress is not part of
what is being proven (this is what Task 20's own release-gate preflight uses).
