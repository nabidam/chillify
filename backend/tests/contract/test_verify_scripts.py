"""The security/storage/persistence verification scripts' fail-closed interface.

These scripts inspect a live filesystem tree — they are meant to be pointed at
a real gate environment's data and music roots. What they must never do is
read, walk, or report on anything that is not disposable: a household path, a
system path, or a container-layer pseudo-filesystem. This suite pins that
refusal, and confirms a disposable, empty target passes cleanly.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.contract

REPO_ROOT = Path(__file__).resolve().parents[3]
SECURITY = REPO_ROOT / "scripts" / "verify" / "security.sh"
STORAGE = REPO_ROOT / "scripts" / "verify" / "storage.sh"
PERSISTENCE = REPO_ROOT / "scripts" / "verify" / "persistence.sh"
SCRIPTS = (SECURITY, STORAGE, PERSISTENCE)


def _run(script: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(script), *arguments],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
        env={**os.environ, "PATH": os.environ.get("PATH", "")},
    )


class TestScriptInterface:
    @pytest.mark.parametrize("script", SCRIPTS)
    def test_every_verify_script_is_executable(self, script: Path) -> None:
        assert script.is_file()
        assert os.access(script, os.X_OK)

    @pytest.mark.parametrize("script", SCRIPTS)
    def test_a_missing_target_is_a_usage_error(self, script: Path) -> None:
        result = _run(script)

        assert result.returncode == 2
        assert "usage" in result.stderr.lower()


class TestNonDisposableTargetsAreRefused:
    @pytest.mark.parametrize("script", SCRIPTS)
    def test_a_household_style_path_is_refused(self, script: Path, tmp_path: Path) -> None:
        """A path that exists but sits outside the repository's .gate tree."""
        household = tmp_path / "household-music"
        household.mkdir()

        result = _run(script, str(household))

        assert result.returncode == 1
        assert "non-disposable" in result.stderr

    @pytest.mark.parametrize("script", SCRIPTS)
    def test_a_repository_path_outside_gate_is_refused(self, script: Path) -> None:
        result = _run(script, str(REPO_ROOT / "backend"))

        assert result.returncode == 1
        assert "non-disposable" in result.stderr


class TestContainerLayerTargetsAreRefused:
    @pytest.mark.parametrize("script", SCRIPTS)
    @pytest.mark.parametrize(
        "target", ["/", "/proc", "/proc/1", "/sys", "/dev", "/run", "/var/lib/docker"]
    )
    def test_a_reserved_system_path_is_refused(self, script: Path, target: str) -> None:
        result = _run(script, target)

        assert result.returncode == 1
        assert "container-layer" in result.stderr

    @pytest.mark.parametrize("script", SCRIPTS)
    def test_a_nonexistent_target_is_refused(self, script: Path) -> None:
        result = _run(script, str(REPO_ROOT / ".gate" / "contract-verify-scripts-absent"))

        assert result.returncode == 1


class TestADisposableTargetPasses:
    @pytest.fixture
    def gate_directory(self) -> Path:
        directory = REPO_ROOT / ".gate" / "contract-verify-scripts-ok"
        (directory / "data").mkdir(parents=True, exist_ok=True)
        (directory / "data" / "marker").write_text("ok", encoding="utf-8")
        try:
            yield directory
        finally:
            for path in sorted(directory.rglob("*"), reverse=True):
                path.unlink() if path.is_file() or path.is_symlink() else path.rmdir()
            directory.rmdir()

    def test_security_accepts_a_clean_disposable_target(self, gate_directory: Path) -> None:
        result = _run(SECURITY, str(gate_directory))

        assert result.returncode == 0, result.stderr
        assert "ok" in result.stdout

    def test_storage_accepts_a_disposable_target_with_no_escaping_symlink(
        self, gate_directory: Path
    ) -> None:
        result = _run(STORAGE, str(gate_directory))

        assert result.returncode == 0, result.stderr
        assert "ok" in result.stdout

    def test_storage_refuses_a_symlink_that_escapes_the_target(
        self, gate_directory: Path, tmp_path: Path
    ) -> None:
        outside = tmp_path / "outside.txt"
        outside.write_text("escaped", encoding="utf-8")
        (gate_directory / "data" / "escape").symlink_to(outside)

        result = _run(STORAGE, str(gate_directory))

        assert result.returncode == 1
        assert "escaping" in result.stderr

    def test_persistence_reports_nothing_to_verify_without_a_database(
        self, gate_directory: Path
    ) -> None:
        result = _run(PERSISTENCE, str(gate_directory / "data"))

        assert result.returncode == 0, result.stderr
        assert "nothing to verify" in result.stdout

    def test_security_finds_a_leaked_secret_shaped_value(self, gate_directory: Path) -> None:
        leaked = gate_directory / "data" / "leaked.env"
        # Built from two literals rather than one contiguous string: written to
        # this disposable fixture, the joined text is exactly the secret-shaped
        # line security.sh must catch, but this source file itself no longer
        # contains that shape, so the repository's own top-level secret scan
        # (./scripts/verify.sh's check_secrets, which greps tracked source for
        # the identical pattern) does not flag this test as a leak.
        key_line = "CHILLIFY_SECRET_KEY=" + "abcdefghijklmnopqrstuvwxyzABCDEF01"
        leaked.write_text(f"{key_line}\n", encoding="utf-8")

        result = _run(SECURITY, str(gate_directory))

        assert result.returncode == 1
        assert "secret-shaped" in result.stderr
