"""Shared fixtures.

Every test that touches disk uses a disposable temporary root. No test reads or
writes a household path, and none requires a live provider or Redis.
"""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

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
def migrated_environment(
    valid_environment: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> dict[str, str]:
    """A valid environment whose disposable database is already migrated.

    The real Alembic migration runs, so tests exercise the schema the household
    deployment actually gets rather than a metadata-created approximation.
    """
    for key, value in valid_environment.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("CHILLIFY_FIXTURE_ROOT", raising=False)

    database_path = Path(valid_environment["CHILLIFY_DATA_ROOT"]) / "db" / "chillify.sqlite3"
    database_path.parent.mkdir(parents=True, exist_ok=True)
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database_path}")
    command.upgrade(config, "head")
    return valid_environment


@pytest.fixture
def start_api(migrated_environment: dict[str, str]) -> Iterator[Callable[[], TestClient]]:
    """Start the real application, as many times as one test needs.

    Restarting is a first-class operation here: the household restarts Compose,
    and every durable claim in this suite must survive that.
    """
    from chillify.api.main import create_app

    running: list[TestClient] = []

    def start() -> TestClient:
        client = TestClient(create_app())
        client.__enter__()
        running.append(client)
        return client

    try:
        yield start
    finally:
        for client in reversed(running):
            client.__exit__(None, None, None)


@pytest.fixture
def repo_root(disposable_root: Path) -> Path:
    """A disposable stand-in repository root for gate-safety assertions."""
    root = disposable_root / "repo"
    (root / ".gate").mkdir(parents=True)
    return root
