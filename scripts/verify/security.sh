#!/usr/bin/env bash
#
# Scan one disposable target for leaked secret-shaped content and unsafe
# `.env` permissions.
#
#   ./scripts/verify/security.sh <path>
#
# Fail-closed and containment-first, like the gate scripts: a target that is
# not beneath the repository's disposable .gate tree, or that names a
# container-layer path, is refused before a single byte of it is read. This
# is the one command NFR-11's release check and the household operator both
# run against a real gate environment, never against household data.

set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TARGET="${1:-}"

if [[ -z "$TARGET" ]]; then
    printf 'usage: %s <path>\n' "$0" >&2
    exit 2
fi

# Reserved and pseudo filesystems are refused by name before any resolution
# is attempted, so a mistyped target can never even be `stat`ed.
case "$TARGET" in
    / | /proc | /proc/* | /sys | /sys/* | /dev | /dev/* | /run | /run/* | /var/lib/docker | /var/lib/docker/*)
        printf 'security: refusing a container-layer target (%s)\n' "$TARGET" >&2
        exit 1
        ;;
esac

if [[ ! -e "$TARGET" ]]; then
    printf 'security: %s does not exist\n' "$TARGET" >&2
    exit 1
fi

if [[ -d "$TARGET" ]]; then
    RESOLVED="$(cd "$TARGET" && pwd -P)"
else
    RESOLVED="$(cd "$(dirname "$TARGET")" && pwd -P)/$(basename "$TARGET")"
fi

# Disposable-only: the resolved target must sit beneath this repository's own
# .gate tree, exactly what scripts/gate/prepare.sh ever creates.
DISPOSABLE_ROOT="$(cd "$REPO_ROOT" && mkdir -p .gate && cd .gate && pwd -P)"
case "$RESOLVED" in
    "$DISPOSABLE_ROOT"/*) ;;
    *)
        printf 'security: refusing a non-disposable target (%s is not beneath %s)\n' \
            "$RESOLVED" "$DISPOSABLE_ROOT" >&2
        exit 1
        ;;
esac

# A resolved symlink or bind mount can still land on a container writable
# layer even when the unresolved path looked disposable; the filesystem type
# is the one thing that cannot be spoofed by a path string.
if command -v stat >/dev/null 2>&1; then
    FSTYPE="$(stat -f -c %T "$RESOLVED" 2>/dev/null || printf 'unknown')"
    case "$FSTYPE" in
        overlay | overlayfs | tmpfs | ramfs | proc | sysfs | devtmpfs | cgroup2)
            printf 'security: refusing a container-layer filesystem (%s is on %s)\n' \
                "$RESOLVED" "$FSTYPE" >&2
            exit 1
            ;;
    esac
fi

FINDINGS=""

HITS="$(grep -rIlnE \
    -e 'BEGIN (RSA|OPENSSH|DSA|EC|PGP) PRIVATE KEY' \
    -e 'CHILLIFY_SECRET_KEY=[A-Za-z0-9_-]{20,}' \
    -e 'api_key=[A-Za-z0-9]{16,}' \
    "$RESOLVED" 2>/dev/null || true)"
if [[ -n "$HITS" ]]; then
    FINDINGS+="secret-shaped content in:"$'\n'"$HITS"$'\n'
fi

while IFS= read -r -d '' env_file; do
    MODE="$(stat -c '%a' "$env_file" 2>/dev/null || printf '???')"
    if [[ "$MODE" != "600" ]]; then
        FINDINGS+="$env_file is mode $MODE, expected 600"$'\n'
    fi
done < <(find "$RESOLVED" -name '.env' -print0 2>/dev/null)

if [[ -n "$FINDINGS" ]]; then
    printf 'security: findings:\n%s' "$FINDINGS" >&2
    exit 1
fi

printf 'security: %s ok\n' "$RESOLVED"
