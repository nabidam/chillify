#!/usr/bin/env bash
#
# Verify one disposable managed-media target has no symlink escaping it.
#
#   ./scripts/verify/storage.sh <path>
#
# This is the host-side half of the containment `resolve_managed_path`
# enforces in-process: every symlink beneath the target must resolve back
# inside it. Containment is checked first, exactly as in every gate script, so
# a target outside the disposable tree or on a container-layer filesystem is
# never even walked.

set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TARGET="${1:-}"

if [[ -z "$TARGET" ]]; then
    printf 'usage: %s <path>\n' "$0" >&2
    exit 2
fi

case "$TARGET" in
    / | /proc | /proc/* | /sys | /sys/* | /dev | /dev/* | /run | /run/* | /var/lib/docker | /var/lib/docker/*)
        printf 'storage: refusing a container-layer target (%s)\n' "$TARGET" >&2
        exit 1
        ;;
esac

if [[ ! -e "$TARGET" ]]; then
    printf 'storage: %s does not exist\n' "$TARGET" >&2
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
        printf 'storage: refusing a non-disposable target (%s is not beneath %s)\n' \
            "$RESOLVED" "$DISPOSABLE_ROOT" >&2
        exit 1
        ;;
esac

if command -v stat >/dev/null 2>&1; then
    FSTYPE="$(stat -f -c %T "$RESOLVED" 2>/dev/null || printf 'unknown')"
    case "$FSTYPE" in
        overlay | overlayfs | tmpfs | ramfs | proc | sysfs | devtmpfs | cgroup2)
            printf 'storage: refusing a container-layer filesystem (%s is on %s)\n' \
                "$RESOLVED" "$FSTYPE" >&2
            exit 1
            ;;
    esac
fi

ESCAPED=""
while IFS= read -r -d '' link; do
    DEST="$(readlink -f "$link" 2>/dev/null || true)"
    case "$DEST" in
        "$RESOLVED" | "$RESOLVED"/*) ;;
        *) ESCAPED+="$link -> ${DEST:-<unresolvable>}"$'\n' ;;
    esac
done < <(find "$RESOLVED" -type l -print0 2>/dev/null)

if [[ -n "$ESCAPED" ]]; then
    printf 'storage: symlinks escaping the managed root:\n%s' "$ESCAPED" >&2
    exit 1
fi

printf 'storage: %s ok\n' "$RESOLVED"
