#!/usr/bin/env bash
#
# The production-composition canary.
#
#   ./scripts/production_canary.sh --env-file <path> [--no-live-success]
#
# Proves that the unchanged production Compose entry point (`docker compose
# up`, no gate overlay, no fixture adapters) resolves real provider/tool/
# Redis/SQLite/media implementations and reaches ready or degraded state on a
# disposable root — before any deterministic fixture is ever mounted. This is
# not a gate: it never applies `deploy/compose.gate.yaml`, never accepts
# `CHILLIFY_ENV=gate`, and refuses an env file that declares one.
#
# Accepts `CHILLIFY_ENV=production` (a real household, or a disposable stand-in
# for one — either way, no declared containment root) and `CHILLIFY_ENV=release`
# (Task 20's release gate: the identical unchanged composition, but a provably
# disposable tree the release gate is also allowed to seed — a declared
# `CHILLIFY_GATE_ROOT` is required in that mode). Both modes resolve the real
# adapters; only `CHILLIFY_ENV=gate` binds fixtures, and this script refuses it.
#
# Containment-first, like every other canary/gate script in this repository: a
# household `.env`, or a gate-shaped one that was hand-edited to point at real
# household storage, is refused before a single container starts.
#
# `--no-live-success` proves only the offline part of the release contract:
# real-adapter binding and a healthy production composition. Without it, the
# canary also drives Chillify's real Radio Javan Featured API path. A provider
# failure remains explicit and exits non-zero; it is never replaced by a
# fixture response or a direct request to the provider.

set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

ENV_FILE=""
NO_LIVE_SUCCESS=0

usage() {
    printf 'usage: %s --env-file <path> [--no-live-success]\n' "$0" >&2
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --env-file)
            if [[ $# -lt 2 ]]; then
                usage
                exit 2
            fi
            ENV_FILE="$2"
            shift 2
            ;;
        --no-live-success)
            NO_LIVE_SUCCESS=1
            shift
            ;;
        *)
            usage
            exit 2
            ;;
    esac
done

if [[ -z "$ENV_FILE" ]]; then
    usage
    exit 2
fi

# Reserved and pseudo filesystems are refused by name before any resolution is
# attempted, exactly as in scripts/verify/security.sh.
case "$ENV_FILE" in
    / | /proc | /proc/* | /sys | /sys/* | /dev | /dev/* | /run | /run/* | /var/lib/docker | /var/lib/docker/*)
        printf 'production_canary: refusing a container-layer target (%s)\n' "$ENV_FILE" >&2
        exit 1
        ;;
esac

if [[ ! -f "$ENV_FILE" ]]; then
    printf 'production_canary: %s does not exist\n' "$ENV_FILE" >&2
    exit 1
fi

ENV_FILE="$(cd "$(dirname "$ENV_FILE")" && pwd -P)/$(basename "$ENV_FILE")"

DISPOSABLE_ROOT="$(cd "$REPO_ROOT" && mkdir -p .gate && cd .gate && pwd -P)"
case "$ENV_FILE" in
    "$DISPOSABLE_ROOT"/*) ;;
    *)
        printf 'production_canary: refusing a non-disposable env file (%s is not beneath %s)\n' \
            "$ENV_FILE" "$DISPOSABLE_ROOT" >&2
        exit 1
        ;;
esac

# The disposable-root containment check (resolve_no_create/assert_roots_under)
# is shared with scripts/gate/seed.sh, which needs the identical property:
# refuse a production-mode environment whose roots are not provably
# disposable, before anything is written.
# shellcheck disable=SC1091
source "$REPO_ROOT/scripts/lib/containment.sh"

# Read specific values out of the file rather than sourcing it, so a canary run
# never executes arbitrary content from an `.env`.
read_var() {
    read_env_var "$1" "$ENV_FILE"
}

ENV_MODE="$(read_var CHILLIFY_ENV)"
GATE_ROOT_VALUE="$(read_var CHILLIFY_GATE_ROOT)"
FIXTURE_ROOT_VALUE="$(read_var CHILLIFY_FIXTURE_ROOT)"
BIND_PORT="$(read_var CHILLIFY_BIND_PORT)"
BIND_PORT="${BIND_PORT:-8787}"

case "$ENV_MODE" in
    production | release) ;;
    *)
        printf 'production_canary: refuses CHILLIFY_ENV=%s; this canary proves the unchanged production composition, not a gate\n' \
            "${ENV_MODE:-<unset>}" >&2
        exit 1
        ;;
esac

# Fixture adapters must never bind in either accepted mode: refused
# regardless of which one this env file declares.
if [[ -n "$FIXTURE_ROOT_VALUE" ]]; then
    printf 'production_canary: refuses a gate-declaring env file (CHILLIFY_FIXTURE_ROOT must be unset — fixture adapters never bind here)\n' >&2
    exit 1
fi

if [[ "$ENV_MODE" == "production" && -n "$GATE_ROOT_VALUE" ]]; then
    printf 'production_canary: refuses a gate-declaring env file (CHILLIFY_GATE_ROOT must be unset in production mode)\n' >&2
    exit 1
fi

if [[ "$ENV_MODE" == "release" && -z "$GATE_ROOT_VALUE" ]]; then
    printf 'production_canary: release mode requires CHILLIFY_GATE_ROOT declaring the disposable tree its roots must resolve beneath\n' >&2
    exit 1
fi

CONTAINMENT_LABEL="production_canary" assert_roots_under \
    "$DISPOSABLE_ROOT" "$ENV_FILE" CHILLIFY_DATA_ROOT CHILLIFY_MUSIC_ROOT

CANARY_BASE_URL="http://localhost:${BIND_PORT}"
BASE_URL="${CHILLIFY_CANARY_BASE_URL:-$CANARY_BASE_URL}"
FEATURED_URL="${BASE_URL}/api/v1/radio-javan/tracks?section=featured"

CLEANED_UP=0
cleanup() {
    if [[ "$CLEANED_UP" -eq 1 ]]; then
        return
    fi
    CLEANED_UP=1
    printf 'production_canary: tearing down %s\n' "$ENV_FILE"
    (cd "$REPO_ROOT" && docker compose --env-file "$ENV_FILE" down --remove-orphans) || true
}
trap cleanup EXIT

printf 'production_canary: bringing up the unchanged production composition from %s\n' "$ENV_FILE"
(cd "$REPO_ROOT" && docker compose --env-file "$ENV_FILE" up --build -d)

printf 'production_canary: waiting for %s/api/v1/system/status\n' "$BASE_URL"
DEADLINE=$((SECONDS + 180))
STATUS_JSON=""
while (( SECONDS < DEADLINE )); do
    if STATUS_JSON="$(curl -fsS -m 5 "$BASE_URL/api/v1/system/status" 2>/dev/null)"; then
        break
    fi
    STATUS_JSON=""
    sleep 2
done

if [[ -z "$STATUS_JSON" ]]; then
    printf 'production_canary: %s/api/v1/system/status never answered within 180s\n' "$BASE_URL" >&2
    exit 1
fi

if ! python3 - "$STATUS_JSON" <<'PYEOF'
import json
import sys

# Passed as an argument, not piped: a heredoc already occupies this process's
# stdin with the script above, so a pipe feeding the same stdin would race it
# and lose — this is what silently produced an empty read here before.
data = json.loads(sys.argv[1])
ready = bool(data.get("ready"))
degraded = bool(data.get("degraded"))

print(
    f"production_canary: ready={json.dumps(ready)} degraded={json.dumps(degraded)} "
    f"environment={data.get('environment')}"
)
print(f"production_canary: database: {json.dumps(data.get('database'))}")
for item in data.get("storage", []):
    print(f"production_canary: storage: {json.dumps(item)}")
print(f"production_canary: redis: {json.dumps(data.get('redis'))}")
for item in data.get("tools", []):
    print(f"production_canary: tool: {json.dumps(item)}")
for item in data.get("providers", []):
    print(f"production_canary: provider: {json.dumps(item)}")

if not (ready or degraded):
    print(
        "production_canary: neither ready nor degraded — the composition did "
        "not reach a legitimate state",
        file=sys.stderr,
    )
    sys.exit(1)
PYEOF
then
    printf 'production_canary: FAILED — the real composition did not reach ready or degraded\n' >&2
    exit 1
fi

# Test-only failure seam: persist an unreachable *valid* proxy in this
# disposable composition, then call the normal Featured URL below. The request
# therefore reaches SearchService and the real Radio Javan adapter before its
# outbound boundary fails; it cannot turn into a direct provider request.
if [[ -n "${CHILLIFY_CANARY_FAILURE_PROXY:-}" ]]; then
    if [[ "$BASE_URL" != "$CANARY_BASE_URL" ]]; then
        printf 'production_canary: the disposable failure probe requires the canary localhost URL\n' >&2
        exit 1
    fi
    SETTINGS_JSON="$(curl -fsS -m 5 "$BASE_URL/api/v1/settings" 2>/dev/null)" || {
        printf 'production_canary: could not read settings for the disposable failure probe\n' >&2
        exit 1
    }
    PROXY_BODY="$(python3 - "$SETTINGS_JSON" "$CHILLIFY_CANARY_FAILURE_PROXY" <<'PYEOF'
import json
import sys

settings = json.loads(sys.argv[1])
revision = settings.get("proxy", {}).get("revision")
if not isinstance(revision, int) or revision < 1:
    sys.exit(1)
print(json.dumps({"url": sys.argv[2], "revision": revision, "clear": False}))
PYEOF
)" || {
        printf 'production_canary: could not prepare the disposable failure probe\n' >&2
        exit 1
    }
    if ! curl -fsS -m 5 -X PATCH "$BASE_URL/api/v1/settings/proxy" \
        -H 'Content-Type: application/json' --data "$PROXY_BODY" >/dev/null 2>&1; then
        printf 'production_canary: could not configure the disposable failure probe\n' >&2
        exit 1
    fi
fi

printf 'production_canary: calling the real Radio Javan Featured API at %s\n' "$FEATURED_URL"
FEATURED_OK=1
if FEATURED_JSON="$(curl -fsS -m 15 "$FEATURED_URL" 2>/dev/null)" && python3 - "$FEATURED_JSON" <<'PYEOF'
import json
import sys

try:
    payload = json.loads(sys.argv[1])
except json.JSONDecodeError:
    sys.exit(1)

if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
    sys.exit(1)
if payload.get("next_cursor") is not None:
    sys.exit(1)
PYEOF
then
    printf 'production_canary: Radio Javan Featured API succeeded through the real adapter\n'
    FEATURED_OK=0
else
    # Do not print a provider body: it could contain URLs or other upstream
    # material that the Radio Javan boundary intentionally keeps out of logs.
    printf 'production_canary: Radio Javan Featured API failed through the real adapter\n' >&2
fi

if [[ "$FEATURED_OK" -ne 0 ]]; then
    if [[ "$NO_LIVE_SUCCESS" -eq 1 ]]; then
        printf 'production_canary: Radio Javan Featured success not required (--no-live-success); continuing\n'
    else
        printf 'production_canary: FAILED — Radio Javan Featured success is required and was not satisfied; pass --no-live-success to prove offline binding only\n' >&2
        exit 1
    fi
fi

printf 'production_canary: PASS\n'
