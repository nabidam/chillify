#!/usr/bin/env bash
#
# The canonical Chillify verification command.
#
#   ./scripts/verify.sh            run every check
#   ./scripts/verify.sh --fast     skip the production build and audits
#
# Fail-closed: any lint, format, type, test, build, audit, secret, or
# boundary failure exits non-zero. A missing tool is a failure, never a skip.

set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

BACKEND="$REPO_ROOT/backend"
FRONTEND="$REPO_ROOT/frontend"
FAST=0
FAILURES=()

for argument in "$@"; do
    case "$argument" in
        --fast) FAST=1 ;;
        *)
            printf 'verify: unknown argument %s\n' "$argument" >&2
            exit 2
            ;;
    esac
done

step() {
    local name="$1"
    shift
    printf '\n=== %s\n' "$name"
    if "$@"; then
        printf -- '--- %s: ok\n' "$name"
    else
        printf -- '!!! %s: FAILED\n' "$name" >&2
        FAILURES+=("$name")
    fi
}

require() {
    local tool="$1"
    if ! command -v "$tool" >/dev/null 2>&1; then
        printf 'verify: required tool %s is not installed\n' "$tool" >&2
        exit 2
    fi
}

require uv
require npm

# --------------------------------------------------------------------------
# Lockfile drift — the committed lock is the only source of installed versions
# --------------------------------------------------------------------------
check_backend_lock() { (cd "$BACKEND" && uv lock --check); }

# The frontend lock is validated with the npm that builds the production web
# image, not with whatever npm the developer happens to have installed. Those
# disagree: a lock missing transitive wasm dependencies passed under one npm
# and failed the image build under another, so this step reported green on a
# lock that could not ship. The base image is read out of the Dockerfile rather
# than repeated here, because a second copy of the version is a second thing to
# forget.
web_build_image() {
    sed -n 's/^FROM \(node:[^ ]*\) AS build$/\1/p' "$REPO_ROOT/deploy/docker/web.Dockerfile" | head -1
}

check_frontend_lock() {
    local image
    image="$(web_build_image)"
    if [[ -z "$image" ]]; then
        printf 'verify: no "FROM node:... AS build" stage in web.Dockerfile\n' >&2
        return 1
    fi
    if ! command -v docker >/dev/null 2>&1; then
        printf 'verify: docker is required to validate the frontend lock against %s\n' \
            "$image" >&2
        return 1
    fi
    # package.json and the lock are copied into the container rather than
    # bind-mounted read-write, so a validation run can never rewrite them.
    docker run --rm --network none -v "$FRONTEND:/frontend:ro" "$image" sh -c '
        set -e
        mkdir -p /tmp/lockcheck
        cp /frontend/package.json /frontend/package-lock.json /tmp/lockcheck/
        cd /tmp/lockcheck
        npm ci --dry-run --no-audit --no-fund >/dev/null
    '
}

# --------------------------------------------------------------------------
# Backend
# --------------------------------------------------------------------------
backend_lint() { (cd "$BACKEND" && uv run ruff check .); }
backend_format() { (cd "$BACKEND" && uv run ruff format --check .); }
backend_types() { (cd "$BACKEND" && uv run mypy); }
backend_tests() { (cd "$BACKEND" && uv run pytest -q); }
# --skip-editable excludes the local chillify package itself, which has no PyPI
# release to audit against. Every third-party dependency is still audited, and
# pip-audit still exits non-zero when it finds a vulnerability. --strict is
# deliberately absent: it would fail on that unavoidable local-package skip.
backend_audit() {
    (cd "$BACKEND" && uv run pip-audit --skip-editable --progress-spinner off)
}

# --------------------------------------------------------------------------
# Frontend
# --------------------------------------------------------------------------
frontend_lint() { (cd "$FRONTEND" && npx --no-install biome check ../); }
frontend_types() { (cd "$FRONTEND" && npx --no-install tsc -b --noEmit); }
frontend_tests() { (cd "$FRONTEND" && npx --no-install vitest run); }
frontend_build() { (cd "$FRONTEND" && npx --no-install vite build); }
frontend_audit() { (cd "$FRONTEND" && npm audit --audit-level=high); }

# --------------------------------------------------------------------------
# Convention checks that a linter cannot express
# --------------------------------------------------------------------------

# Raw color literals belong only in the token source.
check_raw_colors() {
    local offenders
    offenders="$(grep -rIn --include='*.tsx' --include='*.ts' --include='*.css' \
        -E '#[0-9a-fA-F]{3,8}\b|\b(rgb|rgba|hsl|hsla|oklch)\(' \
        "$FRONTEND/src" \
        | grep -v '^.*/src/styles/tokens.css:' \
        | grep -v '^.*/src/components/ui/' || true)"
    if [[ -n "$offenders" ]]; then
        printf 'Raw color values outside the token source:\n%s\n' "$offenders" >&2
        return 1
    fi
}

# Radix and CVA are primitive-construction tools; only the Shadcn registry
# directory may use them directly.
check_primitive_boundary() {
    local offenders
    offenders="$(grep -rIn --include='*.tsx' --include='*.ts' \
        -E 'from "(radix-ui|@radix-ui/[^"]+|class-variance-authority)"' \
        "$FRONTEND/src" \
        | grep -v '^.*/src/components/ui/' || true)"
    if [[ -n "$offenders" ]]; then
        printf 'Primitive construction outside src/components/ui:\n%s\n' "$offenders" >&2
        return 1
    fi
}

# The domain layer imports no framework, no infrastructure, no provider SDK.
check_domain_boundary() {
    local domain="$BACKEND/src/chillify/domain"
    [[ -d "$domain" ]] || return 0
    local offenders
    offenders="$(grep -rIn --include='*.py' \
        -E '^\s*(import|from)\s+(fastapi|starlette|sqlalchemy|alembic|celery|redis|httpx|yt_dlp|spotdl|mutagen|PIL|pathlib|os|shutil|subprocess)\b' \
        "$domain" || true)"
    if [[ -n "$offenders" ]]; then
        printf 'Domain layer imports infrastructure:\n%s\n' "$offenders" >&2
        return 1
    fi
}

# No secret ever reaches the repository.
check_secrets() {
    local findings=""

    if git ls-files --error-unmatch .env >/dev/null 2>&1; then
        findings+=$'.env is tracked by git\n'
    fi

    local tracked
    tracked="$(git ls-files -z | tr '\0' '\n' | grep -vE '^(specs/|.*\.lock$|frontend/package-lock\.json$)' || true)"
    if [[ -n "$tracked" ]]; then
        local hits
        hits="$(printf '%s\n' "$tracked" | xargs -r grep -IlnE \
            -e 'BEGIN (RSA|OPENSSH|DSA|EC|PGP) PRIVATE KEY' \
            -e 'CHILLIFY_SECRET_KEY=[A-Za-z0-9_-]{20,}' \
            -e 'api_key=[A-Za-z0-9]{16,}' \
            2>/dev/null || true)"
        [[ -n "$hits" ]] && findings+="secret-shaped content in: $hits"$'\n'
    fi

    if [[ -n "$findings" ]]; then
        printf 'Secret scan findings:\n%s' "$findings" >&2
        return 1
    fi
}

# --------------------------------------------------------------------------
step "lockfile drift (backend)" check_backend_lock
step "lockfile drift (frontend)" check_frontend_lock

step "backend lint" backend_lint
step "backend format" backend_format
step "backend types" backend_types
step "backend tests" backend_tests

step "frontend lint" frontend_lint
step "frontend types" frontend_types
step "frontend tests" frontend_tests

step "raw color literals" check_raw_colors
step "primitive boundary" check_primitive_boundary
step "domain boundary" check_domain_boundary
step "secret scan" check_secrets

if [[ "$FAST" -eq 0 ]]; then
    step "frontend build" frontend_build
    step "backend dependency audit" backend_audit
    step "frontend dependency audit" frontend_audit
fi

printf '\n'
if [[ ${#FAILURES[@]} -gt 0 ]]; then
    printf 'verify: FAILED (%d)\n' "${#FAILURES[@]}" >&2
    printf -- '  - %s\n' "${FAILURES[@]}" >&2
    exit 1
fi

printf 'verify: all checks passed\n'
