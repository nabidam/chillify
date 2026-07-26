#!/usr/bin/env bash
#
# Seed a prepared gate or release environment with fixture data.
#
#   ./scripts/gate/seed.sh <name> [scenario]
#
# Reads .gate/<name>/.env and writes only inside that tree. It refuses to run
# against anything but a gate or release environment, so household data is
# unreachable even if the wrong name is typed. `gate` mode is trusted on the
# environment declaration alone (config.py's own, stricter gate-safety rules
# already require a declared containment root, a fixture root beneath it, and
# the gate Redis namespace for that mode). `release` mode — the real
# production composition, seeded, which is what Task 20's release gate needs
# — additionally re-verifies containment itself here: every root
# .gate/<name>/.env declares must resolve beneath this gate's own
# .gate/<name>/ tree before anything is written. A household deployment's
# roots resolve outside that tree and are still refused; production mode
# itself is refused outright, unconditionally, regardless of its roots — this
# script never seeds a household deployment.
#
# `scenario` selects which fixture track set to seed (default: "default").
# The browse/organize/listen gate passes "listening" for a library with
# several artists, albums, years, and an Unknown Year grouping. An unknown
# label falls back to the base track set, so a decorative chunk label is
# harmless.

set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
NAME="${1:-}"
SCENARIO="${2:-default}"

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

CHILLIFY_ENV_VALUE="$(grep -E '^CHILLIFY_ENV=' "$ENV_FILE" | tail -1 | cut -d= -f2-)"

case "$CHILLIFY_ENV_VALUE" in
    gate)
        # Trusted on the declaration alone: config.py's own gate-safety rules
        # (stricter than this script could re-derive from the outside) already
        # require a declared containment root, a fixture root beneath it, and
        # the gate Redis namespace before CHILLIFY_ENV=gate is even accepted.
        ;;
    release)
        # The real production composition, seeded — refused unless every
        # declared root is provably disposable (resolves beneath this gate's
        # own .gate/<name>/ tree). A household-shaped root, or one that
        # symlink-escapes that tree, is refused before anything below is
        # written. This is the same containment check
        # scripts/production_canary.sh performs for the unchanged production
        # composition, shared via scripts/lib/containment.sh so both scripts
        # refuse on the identical property instead of drifting via
        # copy-paste.
        # shellcheck disable=SC1091
        source "$REPO_ROOT/scripts/lib/containment.sh"
        # GATE_ROOT itself is resolved (without creating it — it must already
        # exist, since ENV_FILE just above was confirmed to live inside it)
        # rather than trusted as a string, so a symlinked .gate/<name> cannot
        # widen the boundary a declared root is checked against.
        GATE_ROOT_RESOLVED="$(resolve_no_create "$GATE_ROOT")"
        CONTAINMENT_LABEL="seed" assert_roots_under \
            "$GATE_ROOT_RESOLVED" "$ENV_FILE" CHILLIFY_DATA_ROOT CHILLIFY_MUSIC_ROOT
        ;;
    *)
        # Fail closed on anything else (production, unset, or unrecognized)
        # rather than seeding invented rows into something that could be a
        # household deployment. Production is refused unconditionally,
        # regardless of how disposable its roots look: it is real household
        # configuration, and seeding it is exactly what must never happen.
        printf 'seed: %s is not a gate or release environment; refusing to seed\n' "$ENV_FILE" >&2
        exit 1
        ;;
esac

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

(cd "$REPO_ROOT/backend" && uv run python -m chillify.gate_seed --fixture-audio "$FIXTURE_AUDIO" --scenario "$SCENARIO")

printf 'seeded %s\n' "$GATE_ROOT"
