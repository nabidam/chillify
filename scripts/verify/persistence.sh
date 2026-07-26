#!/usr/bin/env bash
#
# Verify one disposable SQLite database is intact and has no media mutation
# left unresolved.
#
#   ./scripts/verify/persistence.sh <path>
#
# `<path>` names either the database file directly or a directory containing
# `db/chillify.sqlite3`, such as a gate's `CHILLIFY_DATA_ROOT`. A target with
# no database yet is not a failure — a freshly prepared gate has none — but a
# database that fails its own integrity check, or still has a
# `media_mutations` row in `recovery_required`, is exactly the mismatch
# NFR-7's recovery guarantee promises never survives a restart.

set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TARGET="${1:-}"

if [[ -z "$TARGET" ]]; then
    printf 'usage: %s <path>\n' "$0" >&2
    exit 2
fi

case "$TARGET" in
    / | /proc | /proc/* | /sys | /sys/* | /dev | /dev/* | /run | /run/* | /var/lib/docker | /var/lib/docker/*)
        printf 'persistence: refusing a container-layer target (%s)\n' "$TARGET" >&2
        exit 1
        ;;
esac

if [[ ! -e "$TARGET" ]]; then
    printf 'persistence: %s does not exist\n' "$TARGET" >&2
    exit 1
fi

if [[ -d "$TARGET" ]]; then
    RESOLVED="$(cd "$TARGET" && pwd -P)"
else
    RESOLVED="$(cd "$(dirname "$TARGET")" && pwd -P)/$(basename "$TARGET")"
fi

DISPOSABLE_ROOT="$(cd "$REPO_ROOT" && mkdir -p .gate && cd .gate && pwd -P)"
case "$RESOLVED" in
    "$DISPOSABLE_ROOT"/*) ;;
    *)
        printf 'persistence: refusing a non-disposable target (%s is not beneath %s)\n' \
            "$RESOLVED" "$DISPOSABLE_ROOT" >&2
        exit 1
        ;;
esac

if command -v stat >/dev/null 2>&1; then
    FSTYPE="$(stat -f -c %T "$RESOLVED" 2>/dev/null || printf 'unknown')"
    case "$FSTYPE" in
        overlay | overlayfs | tmpfs | ramfs | proc | sysfs | devtmpfs | cgroup2)
            printf 'persistence: refusing a container-layer filesystem (%s is on %s)\n' \
                "$RESOLVED" "$FSTYPE" >&2
            exit 1
            ;;
    esac
fi

DB_PATH=""
if [[ -f "$RESOLVED" && "$RESOLVED" == *.sqlite3 ]]; then
    DB_PATH="$RESOLVED"
elif [[ -f "$RESOLVED/db/chillify.sqlite3" ]]; then
    DB_PATH="$RESOLVED/db/chillify.sqlite3"
fi

if [[ -z "$DB_PATH" ]]; then
    printf 'persistence: no database beneath %s; nothing to verify\n' "$RESOLVED"
    exit 0
fi

if ! command -v sqlite3 >/dev/null 2>&1; then
    printf 'persistence: sqlite3 is required to verify %s\n' "$DB_PATH" >&2
    exit 1
fi

INTEGRITY="$(sqlite3 "$DB_PATH" 'PRAGMA integrity_check;' 2>&1 || true)"
if [[ "$INTEGRITY" != "ok" ]]; then
    printf 'persistence: integrity check failed for %s:\n%s\n' "$DB_PATH" "$INTEGRITY" >&2
    exit 1
fi

STUCK="$(sqlite3 "$DB_PATH" \
    "SELECT COUNT(*) FROM media_mutations WHERE state = 'recovery_required';" 2>/dev/null || printf 0)"
if [[ "$STUCK" != "0" ]]; then
    printf 'persistence: %s media mutation(s) left in recovery_required\n' "$STUCK" >&2
    exit 1
fi

printf 'persistence: %s ok\n' "$DB_PATH"
