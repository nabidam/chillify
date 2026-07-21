"""The gate scripts' fail-closed command interface.

These scripts are the only things in the repository that create and then delete
whole directory trees. Every assertion here is about what they refuse: a name
they cannot verify, an environment that is not a gate, or a path outside the
disposable tree.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.contract

REPO_ROOT = Path(__file__).resolve().parents[3]
PREPARE = REPO_ROOT / "scripts" / "gate" / "prepare.sh"
SEED = REPO_ROOT / "scripts" / "gate" / "seed.sh"
CLEANUP = REPO_ROOT / "scripts" / "gate" / "cleanup.sh"


def _run(
    script: Path, *arguments: str, cwd: Path | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(script), *arguments],
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd,
        timeout=120,
        env={**os.environ, "PATH": os.environ.get("PATH", "")},
    )


class TestScriptInterface:
    @pytest.mark.parametrize("script", [PREPARE, SEED, CLEANUP])
    def test_every_gate_script_is_executable(self, script: Path) -> None:
        assert script.is_file()
        assert os.access(script, os.X_OK)

    @pytest.mark.parametrize("script", [PREPARE, SEED, CLEANUP])
    def test_a_missing_name_is_a_usage_error(self, script: Path) -> None:
        result = _run(script)

        assert result.returncode == 2
        assert "usage" in result.stderr.lower()

    @pytest.mark.parametrize("script", [PREPARE, SEED, CLEANUP])
    def test_a_traversing_name_is_refused_before_anything_is_touched(self, script: Path) -> None:
        result = _run(script, "../escape")

        assert result.returncode == 2
        assert "lowercase alphanumeric" in result.stderr

    @pytest.mark.parametrize("script", [PREPARE, SEED, CLEANUP])
    def test_an_absolute_name_is_refused(self, script: Path) -> None:
        result = _run(script, "/etc")

        assert result.returncode == 2


class TestSeedRefusals:
    def test_seeding_an_unprepared_environment_is_refused(self) -> None:
        result = _run(SEED, "definitely-not-prepared")

        assert result.returncode == 1
        assert "prepare.sh first" in result.stderr

    def test_seeding_a_production_environment_is_refused(self) -> None:
        """A production `.env` must never receive invented rows.

        The check is on the file's own `CHILLIFY_ENV`, not on the name, so a
        gate-looking name over a household configuration is still refused.
        """
        gate_root = REPO_ROOT / ".gate" / "contract-production-check"
        gate_root.mkdir(parents=True, exist_ok=True)
        environment = gate_root / ".env"
        environment.write_text("CHILLIFY_ENV=production\n", encoding="utf-8")
        try:
            result = _run(SEED, "contract-production-check")
        finally:
            environment.unlink(missing_ok=True)
            gate_root.rmdir()

        assert result.returncode == 1
        assert "not a gate environment" in result.stderr


class TestCleanupBehaviour:
    def test_removing_an_absent_environment_succeeds_quietly(self) -> None:
        result = _run(CLEANUP, "never-existed")

        assert result.returncode == 0
        assert "nothing to remove" in result.stdout

    def test_cleanup_removes_only_its_own_tree(self) -> None:
        """A sibling gate environment is untouched by another's cleanup."""
        gate_parent = REPO_ROOT / ".gate"
        removed = gate_parent / "contract-removed"
        kept = gate_parent / "contract-kept"
        (removed / "data").mkdir(parents=True, exist_ok=True)
        (kept / "data").mkdir(parents=True, exist_ok=True)
        (removed / "data" / "marker").write_text("x", encoding="utf-8")
        (kept / "data" / "marker").write_text("x", encoding="utf-8")

        try:
            result = _run(CLEANUP, "contract-removed")

            assert result.returncode == 0
            assert not removed.exists()
            assert (kept / "data" / "marker").is_file()
        finally:
            for tree in (removed, kept):
                if tree.exists():
                    for path in sorted(tree.rglob("*"), reverse=True):
                        path.unlink() if path.is_file() else path.rmdir()
                    tree.rmdir()
