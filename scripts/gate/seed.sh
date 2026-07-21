#!/usr/bin/env bash
#
# Seed a prepared gate environment with fixture data.
#
#   ./scripts/gate/seed.sh <name>
#
# Reads .gate/<name>/.env and writes only inside that tree. It refuses to run
# against anything but a gate environment, so household data is unreachable
# even if the wrong name is typed.

set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
NAME="${1:-}"

if [[ -z "$NAME" ]]; then
    printf 'usage: %s <name>\n' "$0" >&2
    exit 2
fi

if [[ ! "$NAME" =~ ^[a-z0-9][a-z0-9-]*$ ]]; then
    printf 'seed: gate name must be lowercase alphanumeric with dashes\n' >&2
    exit 2
fi

GATE_ROOT="$REPO_ROOT/.gate/$NAME"
ENV_FILE="$GATE_ROOT/.env"

if [[ ! -f "$ENV_FILE" ]]; then
    printf 'seed: %s does not exist; run prepare.sh first\n' "$ENV_FILE" >&2
    exit 1
fi

# Fail closed on a production-mode environment rather than seeding invented
# rows into something that could be a household deployment.
if ! grep -qx 'CHILLIFY_ENV=gate' "$ENV_FILE"; then
    printf 'seed: %s is not a gate environment; refusing to seed\n' "$ENV_FILE" >&2
    exit 1
fi

FIXTURE_AUDIO="$REPO_ROOT/backend/tests/fixtures/media/gate-tone.mp3"
if [[ ! -f "$FIXTURE_AUDIO" ]]; then
    printf 'seed: fixture audio %s is missing\n' "$FIXTURE_AUDIO" >&2
    exit 1
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

# Compose applies the migration as a one-shot service before the API starts.
# A standalone seed has no such service, so it brings its own schema up first;
# `upgrade head` is idempotent, so seeding a running environment is still safe.
# The migration resolves its target from the same validated configuration the
# application uses, so it cannot reach a location the config would reject.
mkdir -p "$CHILLIFY_DATA_ROOT/db"
(cd "$REPO_ROOT/backend" && uv run alembic upgrade head)

(cd "$REPO_ROOT/backend" && uv run python -m chillify.gate_seed --fixture-audio "$FIXTURE_AUDIO")

printf 'seeded %s\n' "$GATE_ROOT"
