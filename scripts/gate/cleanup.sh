#!/usr/bin/env bash
#
# Remove a disposable gate environment.
#
#   ./scripts/gate/cleanup.sh <name>
#
# It stops the Compose project for that environment and then deletes
# .gate/<name>/ and nothing else. The resolved target is verified to sit
# beneath the repository .gate tree before a single file is removed: this is
# the one script that deletes, so it is the one that must be certain where.

set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
NAME="${1:-}"

if [[ -z "$NAME" ]]; then
    printf 'usage: %s <name>\n' "$0" >&2
    exit 2
fi

if [[ ! "$NAME" =~ ^[a-z0-9][a-z0-9-]*$ ]]; then
    printf 'cleanup: gate name must be lowercase alphanumeric with dashes\n' >&2
    exit 2
fi

GATE_PARENT="$REPO_ROOT/.gate"
GATE_ROOT="$GATE_PARENT/$NAME"

if [[ ! -d "$GATE_ROOT" ]]; then
    printf 'cleanup: %s does not exist; nothing to remove\n' "$GATE_ROOT"
    exit 0
fi

# Fail closed: the resolved directory must be a direct child of the repository
# .gate tree. A symlinked or traversed name is refused rather than followed.
RESOLVED_PARENT="$(cd "$GATE_PARENT" && pwd -P)"
RESOLVED_TARGET="$(cd "$GATE_ROOT" && pwd -P)"
case "$RESOLVED_TARGET" in
    "$RESOLVED_PARENT"/*) ;;
    *)
        printf 'cleanup: refusing to remove %s outside %s\n' "$RESOLVED_TARGET" \
            "$RESOLVED_PARENT" >&2
        exit 1
        ;;
esac
if [[ "$(dirname "$RESOLVED_TARGET")" != "$RESOLVED_PARENT" ]]; then
    printf 'cleanup: refusing to remove a nested path\n' >&2
    exit 1
fi

ENV_FILE="$GATE_ROOT/.env"
if [[ -f "$ENV_FILE" ]] && command -v docker >/dev/null 2>&1; then
    # Best effort: an environment that was never launched has nothing to stop,
    # and a stopped stack must not block removal of its own directory.
    docker compose --env-file "$ENV_FILE" down --volumes --remove-orphans >/dev/null 2>&1 || true
fi

rm -rf "$RESOLVED_TARGET"

printf 'removed %s\n' "$RESOLVED_TARGET"
