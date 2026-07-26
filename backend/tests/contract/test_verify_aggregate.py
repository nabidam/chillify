"""`./scripts/verify.sh`'s own fail-closed aggregate interface.

Every `scripts/verify/*.sh` script is already contract-tested in
`test_verify_scripts.py` for the one thing they own: refusing a
non-disposable or container-layer target. The top-level `./scripts/verify.sh`
owns a different contract — running every lint/format/type/test/build/audit/
convention step, continuing past a failing one rather than aborting on the
first, and exiting non-zero exactly when the aggregate has any failure at
all — and nothing pins that down yet.

Pinning it means actually running the script, so this suite gives it a
disposable environment of its own: a `git worktree` checked out from the same
commit, entirely separate from the developer's working tree, removed after
the test regardless of outcome. A raw-color-literal file dropped into that
worktree's own `frontend/src` is a fault `./scripts/verify.sh` is already
supposed to catch (the "raw color literals" convention check), giving a
real, reproducible red without touching anything a person is editing.

`./scripts/verify.sh`'s own `backend tests` step runs this very module, which
would otherwise recreate a worktree recursively without bound. The recursion
is broken with an ordinary environment-variable guard: the process this suite
spawns is marked nested, and a nested run skips this module instead of
spawning a fourth (or infinitude) generation of worktrees.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.contract,
    pytest.mark.skipif(
        os.environ.get("CHILLIFY_VERIFY_CONTRACT_NESTED") == "1",
        reason="already running inside a nested ./scripts/verify.sh invocation",
    ),
]

REPO_ROOT = Path(__file__).resolve().parents[3]
VERIFY = REPO_ROOT / "scripts" / "verify.sh"

# Steps declared after "raw color literals" in scripts/verify.sh's own run
# order. If the injected fault below is genuinely aggregated rather than
# fatal, every one of these still reports "ok" in the same run.
STEPS_AFTER_THE_INJECTED_FAULT = (
    "primitive boundary",
    "domain boundary",
    "secret scan",
)


def _run_verify(worktree: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    """Run the worktree's own `./scripts/verify.sh`, marked as a nested call."""
    return subprocess.run(
        [str(worktree / "scripts" / "verify.sh"), *arguments],
        cwd=worktree,
        capture_output=True,
        text=True,
        check=False,
        timeout=480,
        env={**os.environ, "CHILLIFY_VERIFY_CONTRACT_NESTED": "1"},
    )


@pytest.fixture(scope="module")
def disposable_worktree() -> Iterator[Path]:
    """A real, separate checkout of `HEAD`, sharing installed toolchains.

    A fresh `npm ci`/`uv sync` per run would make this suite either
    network-dependent or minutes slower for no reason: the worktree checks out
    the identical lockfiles the developer's own `node_modules`/`.venv` were
    installed from, so those directories are symlinked in rather than
    reinstalled.
    """
    worktree = REPO_ROOT / ".gate" / f"contract-verify-aggregate-{uuid.uuid4().hex[:8]}"
    (REPO_ROOT / ".gate").mkdir(exist_ok=True)
    subprocess.run(
        ["git", "worktree", "add", "--detach", "--force", str(worktree), "HEAD"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    try:
        frontend_modules = REPO_ROOT / "frontend" / "node_modules"
        if frontend_modules.is_dir():
            (worktree / "frontend" / "node_modules").symlink_to(frontend_modules)
        backend_venv = REPO_ROOT / "backend" / ".venv"
        if backend_venv.is_dir():
            (worktree / "backend" / ".venv").symlink_to(backend_venv)
        yield worktree
    finally:
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(worktree)],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
        )
        shutil.rmtree(worktree, ignore_errors=True)


class TestACleanCheckoutPasses:
    def test_verify_fast_passes_from_a_clean_checkout(self, disposable_worktree: Path) -> None:
        result = _run_verify(disposable_worktree, "--fast")

        assert result.returncode == 0, result.stdout + result.stderr
        assert "verify: all checks passed" in result.stdout


class TestFailClosedAggregation:
    def test_an_injected_convention_failure_fails_the_run_but_keeps_going(
        self, disposable_worktree: Path
    ) -> None:
        offender = disposable_worktree / "frontend" / "src" / "__contract_injected_fault.ts"
        # Double-quoted: this repository's biome config requires double quotes,
        # and the point of this fault is to trip exactly one check ("raw color
        # literals"), not also "frontend lint" on an unrelated formatting nit.
        offender.write_text('export const injected = "#abc123";\n', encoding="utf-8")
        try:
            result = _run_verify(disposable_worktree, "--fast")

            assert result.returncode == 1, result.stdout + result.stderr
            assert "!!! raw color literals: FAILED" in result.stderr
            assert "verify: FAILED (1)" in result.stderr
            assert "  - raw color literals" in result.stderr

            # The aggregate kept running every step after the failing one,
            # rather than aborting the whole script at the first red result.
            for step in STEPS_AFTER_THE_INJECTED_FAULT:
                assert f"--- {step}: ok" in result.stdout, (
                    f"{step!r} did not run after the injected failure:\n{result.stdout}"
                )
        finally:
            offender.unlink(missing_ok=True)

    def test_the_fault_cleared_the_run_is_clean_again(self, disposable_worktree: Path) -> None:
        # The previous test removes its own fault in a `finally`, so this is a
        # direct assertion that the worktree really is back to a clean state
        # rather than an accident of test ordering.
        result = _run_verify(disposable_worktree, "--fast")

        assert result.returncode == 0, result.stdout + result.stderr
        assert "verify: all checks passed" in result.stdout


def test_an_unknown_argument_is_a_usage_error_not_a_silent_pass() -> None:
    """A malformed invocation must never report success by falling through."""
    result = subprocess.run(
        [str(VERIFY), "--not-a-real-flag"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )

    assert result.returncode == 2
    assert "unknown argument" in result.stderr
