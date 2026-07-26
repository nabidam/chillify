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


def _remove_tree(name: str) -> None:
    """Remove a prepared environment's directory tree directly, without going
    through cleanup.sh.

    cleanup.sh's `docker compose --env-file ... down` targets the compose
    project literally named `chillify` in the repository's own `compose.yaml`
    — the *same* project name regardless of which `.env` is passed, since
    Compose takes a file's `name:` directive over any per-invocation env-file
    difference. A prepared-but-never-launched test environment has no
    containers of its own to stop, but calling cleanup.sh here would still
    reach for that shared project name and could tear down an unrelated,
    genuinely running `chillify` stack on the same machine (a real release
    gate, for instance). These tests only need the directory removed, so they
    remove it directly and never invoke `docker compose` at all.
    """
    tree = REPO_ROOT / ".gate" / name
    if not tree.exists():
        return
    for path in sorted(tree.rglob("*"), reverse=True):
        if path.is_file() or path.is_symlink():
            path.unlink()
        else:
            path.rmdir()
    tree.rmdir()


class TestSeedRefusals:
    def test_seeding_an_unprepared_environment_is_refused(self) -> None:
        result = _run(SEED, "definitely-not-prepared")

        assert result.returncode == 1
        assert "prepare.sh first" in result.stderr

    def test_seeding_a_production_environment_is_refused(self) -> None:
        """A production `.env` must never receive invented rows, regardless
        of how disposable its roots look.

        The check is on the file's own `CHILLIFY_ENV`, not on the name, so a
        gate-looking name over a household configuration is still refused.
        This is the regression guard on the original safety property: seeding
        gained a `release` mode, but production stayed exactly as refused as
        before.
        """
        gate_root = REPO_ROOT / ".gate" / "contract-production-check"
        gate_root.mkdir(parents=True, exist_ok=True)
        environment = gate_root / ".env"
        environment.write_text(
            "CHILLIFY_ENV=production\n"
            f"CHILLIFY_DATA_ROOT={gate_root}/data\n"
            f"CHILLIFY_MUSIC_ROOT={gate_root}/music\n",
            encoding="utf-8",
        )
        try:
            result = _run(SEED, "contract-production-check")

            assert result.returncode == 1
            assert "not a gate or release environment" in result.stderr
            assert not (gate_root / "data").exists()
        finally:
            environment.unlink(missing_ok=True)
            gate_root.rmdir()

    def test_release_environment_with_a_household_root_is_refused_before_any_write(
        self, tmp_path: Path
    ) -> None:
        """A release `.env` hand-edited (or copy-pasted) to a real household
        root must never receive invented rows either. Refusal happens before
        `CHILLIFY_DATA_ROOT`'s own directory is ever created."""
        name = "contract-release-household"
        gate_root = REPO_ROOT / ".gate" / name
        gate_root.mkdir(parents=True, exist_ok=True)
        household = tmp_path / "household-music"
        household.mkdir()
        environment = gate_root / ".env"
        environment.write_text(
            "CHILLIFY_ENV=release\n"
            f"CHILLIFY_DATA_ROOT={gate_root}/data\n"
            f"CHILLIFY_MUSIC_ROOT={household}\n"
            f"CHILLIFY_GATE_ROOT={gate_root}\n",
            encoding="utf-8",
        )
        try:
            result = _run(SEED, name, "kernel-500")

            assert result.returncode == 1
            assert "household" in result.stderr
            assert not (gate_root / "data").exists()
        finally:
            environment.unlink(missing_ok=True)
            gate_root.rmdir()

    def test_release_environment_with_a_symlink_escaping_root_is_refused_before_any_write(
        self, tmp_path: Path
    ) -> None:
        """A declared root that resolves, through a symlink, to somewhere
        outside `.gate/<name>/` is refused exactly like a plainly household
        one — `realpath -m` collapses the symlink before the containment
        comparison runs."""
        name = "contract-release-symlink"
        gate_root = REPO_ROOT / ".gate" / name
        gate_root.mkdir(parents=True, exist_ok=True)
        outside = tmp_path / "outside-music"
        outside.mkdir()
        escape = gate_root / "music-escape"
        escape.symlink_to(outside)
        environment = gate_root / ".env"
        environment.write_text(
            "CHILLIFY_ENV=release\n"
            f"CHILLIFY_DATA_ROOT={gate_root}/data\n"
            f"CHILLIFY_MUSIC_ROOT={escape}\n"
            f"CHILLIFY_GATE_ROOT={gate_root}\n",
            encoding="utf-8",
        )
        try:
            result = _run(SEED, name, "kernel-500")

            assert result.returncode == 1
            assert "household" in result.stderr
            assert not (gate_root / "data").exists()
        finally:
            environment.unlink(missing_ok=True)
            escape.unlink()
            gate_root.rmdir()

    def test_release_environment_with_contained_roots_seeds_successfully(self) -> None:
        """The shape Task 20's release gate actually runs: real adapters,
        roots beneath `.gate/<name>/`. `kernel-500` is a chunk label, not a
        registered scenario, so it falls back to the base track set — the
        same fallback `test_unknown_scenario_falls_back_to_the_base_tracks`
        already covers at the track-set level."""
        name = "contract-release-seed-ok"
        try:
            prepared = _run(PREPARE, name, "release")
            assert prepared.returncode == 0, prepared.stderr

            result = _run(SEED, name, "kernel-500")

            assert result.returncode == 0, result.stderr
            assert "seeded" in result.stdout
            database = REPO_ROOT / ".gate" / name / "data" / "db" / "chillify.sqlite3"
            assert database.is_file()
        finally:
            _remove_tree(name)

    def test_gate_environment_still_seeds_successfully(self) -> None:
        """No regression: gate mode is unaffected by release mode's addition."""
        name = "contract-gate-seed-ok"
        try:
            prepared = _run(PREPARE, name, "gate")
            assert prepared.returncode == 0, prepared.stderr

            result = _run(SEED, name)

            assert result.returncode == 0, result.stderr
            assert "seeded" in result.stdout
        finally:
            _remove_tree(name)


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
