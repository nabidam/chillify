#!/usr/bin/env bash
#
# Named NFR evidence, Chromium/Firefox smoke, and axe verification.
#
#   ./scripts/verify/nfr.sh [gate-name]
#
# Runs the browser-measured checks Task 18 adds against a fresh, disposable
# gate stack: frontend/tests/e2e/nfr.spec.ts (NFR-1/2/3/5, Chromium),
# firefox-smoke.spec.ts (NFR-3/9, Firefox), and degraded.spec.ts (NFR-10).
# Provisioning and teardown of the gate stack are owned by
# playwright.config.ts's globalSetup/globalTeardown, exactly as every other
# gate suite in this repository (gate-1/2/3, accessibility) — this script only
# names which specs run, against which gate, and surfaces the "NFR-n: ..."
# lines each spec prints as the named evidence artifact.
#
# The zero-critical/serious axe bar (NFR-8) is frontend/tests/e2e/
# accessibility.spec.ts's own, pre-existing responsibility (Task 14/15) and is
# not rerun here: bundling it into this script would make Task 18's own
# result depend on a defect this task did not introduce and is not scoped to
# fix. Task 18's evidence file records that finding directly.
#
# `gate-name` defaults to "gate-4": Task 18's own disposable stack, seeded
# with the same "listening" scenario Gate 3 uses. Task 20's release gate reruns
# these same specs against the full kernel-500 release stack for the v1 exit
# bar's own numbers; this script proves the measurement mechanism itself,
# not that scale.

set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
GATE_NAME="${1:-gate-4}"

cd "$REPO_ROOT/frontend"

export GATE_NAME
export GATE_SCENARIO="listening"
export GATE_BASE_URL="${GATE_BASE_URL:-http://localhost:8788}"

printf '=== NFR evidence: gate "%s" ===\n' "$GATE_NAME"

OUTPUT="$(mktemp)"
trap 'rm -f "$OUTPUT"' EXIT

STATUS=0
npx --no-install playwright test nfr firefox-smoke degraded 2>&1 | tee "$OUTPUT" || STATUS=1

printf '\n--- named NFR evidence ---\n'
if ! grep -E '^NFR-[0-9]+:' "$OUTPUT"; then
    printf '(no NFR evidence lines were captured)\n'
    STATUS=1
fi

exit "$STATUS"
