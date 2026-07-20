"""Shared fixtures.

Every test that touches disk uses a disposable temporary root. No test reads or
writes a household path, and none requires a live provider or Redis.
"""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

BACKEND_ROOT = Path(__file__).resolve().parents[1]

# Mounted roots must be normal durable filesystems, and pytest's tmp_path is
# tmpfs on common developer machines. Disposable roots therefore live beside
# the backend on real disk and are removed after each test.
_DISPOSABLE_ROOT_BASE = BACKEND_ROOT / ".pytest-roots"

# Sentinel secrets. If any of these strings appears in an API response, a UI
# error, or stdout, redaction failed.
SENTINEL_PROXY_PASSWORD = "sentinel-proxy-password-3f9c1a"
SENTINEL_PROXY_URL = f"socks5://proxyuser:{SENTINEL_PROXY_PASSWORD}@proxy.invalid:1080"
SENTINEL_LASTFM_KEY = "sentinel-lastfm-key-b72e40d5c1"


@pytest.fixture
def secret_key() -> str:
    return Fernet.generate_key().decode("ascii")


@pytest.fixture
def disposable_root() -> Iterator[Path]:
    """A disposable directory on a normal filesystem."""
    _DISPOSABLE_ROOT_BASE.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(dir=_DISPOSABLE_ROOT_BASE))
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


@pytest.fixture
def storage_roots(disposable_root: Path) -> tuple[Path, Path]:
    data_root = disposable_root / "data"
    music_root = disposable_root / "music"
    data_root.mkdir()
    music_root.mkdir()
    return data_root, music_root


@pytest.fixture
def valid_environment(storage_roots: tuple[Path, Path], secret_key: str) -> dict[str, str]:
    data_root, music_root = storage_roots
    return {
        "CHILLIFY_DATA_ROOT": str(data_root),
        "CHILLIFY_MUSIC_ROOT": str(music_root),
        "REDIS_URL": "redis://127.0.0.1:6379/9",
        "CHILLIFY_SECRET_KEY": secret_key,
        "CHILLIFY_ENV": "production",
    }


@pytest.fixture
def repo_root(disposable_root: Path) -> Path:
    """A disposable stand-in repository root for gate-safety assertions."""
    root = disposable_root / "repo"
    (root / ".gate").mkdir(parents=True)
    return root
