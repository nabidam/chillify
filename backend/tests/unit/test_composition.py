"""Tool resolution in the composition root.

SpotDL lives in an isolated environment that is deliberately absent from PATH,
so it is reachable only through its configured absolute path.
"""

from __future__ import annotations

import stat
from pathlib import Path

import pytest

from chillify.composition import _resolve_executable

pytestmark = pytest.mark.unit


@pytest.fixture
def executable(disposable_root: Path) -> Path:
    binary = disposable_root / "spotdl"
    binary.write_text("#!/bin/sh\necho 4.5.2\n", encoding="utf-8")
    binary.chmod(binary.stat().st_mode | stat.S_IXUSR)
    return binary


def test_configured_path_is_preferred(executable: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHILLIFY_SPOTDL_BIN", str(executable))

    assert _resolve_executable("spotdl", "CHILLIFY_SPOTDL_BIN") == str(executable)


def test_configured_path_that_is_not_executable_resolves_to_nothing(
    disposable_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A configured but unusable path is unavailable, never a silent PATH fallback.

    Falling back would let the isolated SpotDL environment be replaced by
    whatever happens to be installed on the host.
    """
    missing = disposable_root / "absent-spotdl"
    monkeypatch.setenv("CHILLIFY_SPOTDL_BIN", str(missing))

    assert _resolve_executable("spotdl", "CHILLIFY_SPOTDL_BIN") is None


def test_blank_variable_falls_back_to_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHILLIFY_FFMPEG_BIN", "")

    assert _resolve_executable("sh", "CHILLIFY_FFMPEG_BIN") is not None


def test_unset_variable_falls_back_to_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CHILLIFY_FFMPEG_BIN", raising=False)

    assert _resolve_executable("sh", "CHILLIFY_FFMPEG_BIN") is not None


def test_absent_tool_resolves_to_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CHILLIFY_DENO_BIN", raising=False)

    assert _resolve_executable("chillify-tool-that-does-not-exist", "CHILLIFY_DENO_BIN") is None
