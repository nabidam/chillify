#!/usr/bin/env bash
#
# Shared disposable-root containment guard.
#
# Sourced (never executed) by scripts/production_canary.sh and
# scripts/gate/seed.sh. Both scripts must refuse a production-mode
# environment whose declared storage roots are not provably disposable
# *before* anything is created, mounted, or written — a household
# deployment's roots resolve outside the disposable tree and must still be
# refused. This file holds that one containment check so the two scripts
# stay identical in the property that matters instead of drifting via
# copy-paste.

# Resolve a path for containment comparison without ever creating it: the
# whole point of the household-root check below is to refuse before
# anything is touched, including `mkdir`. `realpath -m` also collapses any
# symlink in the path, so a symlink planted to escape the disposable tree
# resolves to its real, outside-the-tree target rather than being taken at
# face value.
resolve_no_create() {
    if command -v realpath >/dev/null 2>&1; then
        realpath -m "$1"
    else
        printf '%s\n' "$1"
    fi
}

# Read a KEY=value out of an env file without sourcing it, so this check
# never executes arbitrary content from an `.env`.
read_env_var() {
    local key="$1" env_file="$2"
    grep -E "^${key}=" "$env_file" | tail -1 | cut -d= -f2- || true
}

# assert_roots_under <disposable_root> <env_file> <VAR_NAME>...
#
# For each named variable declared in <env_file>, resolves its value
# (without creating it) and refuses (prints to stderr, exit 1) unless the
# resolved path sits beneath <disposable_root>. An unset/empty value is
# also a refusal: a root that does not resolve to anything cannot be
# proven disposable. Set CONTAINMENT_LABEL in the caller's environment to
# prefix messages with the caller's own script name (defaults to
# "containment").
assert_roots_under() {
    local disposable_root="$1"
    local env_file="$2"
    shift 2
    local label="${CONTAINMENT_LABEL:-containment}"
    local name value resolved
    for name in "$@"; do
        value="$(read_env_var "$name" "$env_file")"
        if [[ -z "$value" ]]; then
            printf '%s: %s is not set in %s\n' "$label" "$name" "$env_file" >&2
            exit 1
        fi
        resolved="$(resolve_no_create "$value")"
        case "$resolved" in
            "$disposable_root"/*) ;;
            *)
                printf '%s: refusing a household %s (%s is not beneath %s)\n' \
                    "$label" "$name" "$resolved" "$disposable_root" >&2
                exit 1
                ;;
        esac
    done
}
