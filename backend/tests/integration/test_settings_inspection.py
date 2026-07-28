"""Cycle-002 inspection settings through their real migration and API boundary."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from chillify.application.settings import InspectionMode

pytestmark = pytest.mark.integration

BACKEND_ROOT = Path(__file__).resolve().parents[2]
SETTINGS = "/api/v1/settings"
SENTINEL_CLIENT_ID = "sentinel-spotify-client-id"
SENTINEL_CLIENT_SECRET = "sentinel-spotify-client-secret-9a5b3d"


@pytest.fixture
def alembic_config(tmp_path: Path) -> tuple[Config, Path]:
    database_path = tmp_path / "chillify.sqlite3"
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database_path}")
    return config, database_path


def _settings_rows(database_path: Path) -> list[tuple[str, str, bytes | None, int, str]]:
    with closing(sqlite3.connect(database_path)) as connection:
        return connection.execute(
            "SELECT key, public_json, secret_ciphertext, revision, updated_at "
            "FROM settings ORDER BY key"
        ).fetchall()


def test_settings_key_migration_round_trips_preexisting_rows(
    alembic_config: tuple[Config, Path],
) -> None:
    config, database_path = alembic_config

    command.upgrade(config, "0001_core")
    before = _settings_rows(database_path)

    command.upgrade(config, "head")
    upgraded = {row[0]: row for row in _settings_rows(database_path)}
    assert [upgraded[row[0]] for row in before] == before
    assert upgraded["inspection"][1] == (
        '{"mode":"fast","timeout_spotify_s":8,"timeout_spotdl_s":150,"timeout_ytdlp_s":60}'
    )
    assert upgraded["provider.spotify_api"][1] == '{"configured":false}'

    # The downgrade removes the new rows before rebuilding the narrower CHECK.
    command.downgrade(config, "0001_core")
    assert _settings_rows(database_path) == before

    command.upgrade(config, "head")
    restored = {row[0]: row for row in _settings_rows(database_path)}
    assert [restored[row[0]] for row in before] == before


def test_inspection_settings_persist_and_reject_stale_revisions(start_api) -> None:
    client: TestClient = start_api()
    initial = client.get(SETTINGS).json()

    saved = client.patch(
        f"{SETTINGS}/inspection",
        json={
            "mode": "thorough",
            "timeout_spotify_s": 12,
            "timeout_spotdl_s": 240,
            "timeout_ytdlp_s": 90,
            "revision": initial["inspection"]["revision"],
        },
    )

    assert saved.status_code == 200
    assert saved.json() == {
        "mode": "thorough",
        "timeout_spotify_s": 12,
        "timeout_spotdl_s": 240,
        "timeout_ytdlp_s": 90,
        "revision": 2,
    }
    assert client.get(SETTINGS).json()["inspection"] == saved.json()

    stale = client.patch(
        f"{SETTINGS}/inspection",
        json={
            "mode": "fast",
            "timeout_spotify_s": 8,
            "timeout_spotdl_s": 150,
            "timeout_ytdlp_s": 60,
            "revision": initial["inspection"]["revision"],
        },
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "record_changed"
    assert client.get(SETTINGS).json()["inspection"] == saved.json()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("timeout_spotify_s", 31),
        ("timeout_spotdl_s", 29),
        ("timeout_ytdlp_s", 301),
    ],
)
def test_invalid_inspection_timeouts_are_rejected_without_a_write(
    start_api, field: str, value: int
) -> None:
    client: TestClient = start_api()
    initial = client.get(SETTINGS).json()["inspection"]
    payload = dict(initial)
    payload[field] = value

    rejected = client.patch(f"{SETTINGS}/inspection", json=payload)

    assert rejected.status_code == 422
    assert rejected.json()["error"]["field"] == field
    assert client.get(SETTINGS).json()["inspection"] == initial


def test_spotify_credentials_are_masked_retained_and_clearable(start_api) -> None:
    client: TestClient = start_api()
    initial = client.get(SETTINGS).json()["spotify_api"]

    saved = client.patch(
        f"{SETTINGS}/providers/spotify_api",
        json={
            "client_id": SENTINEL_CLIENT_ID,
            "client_secret": SENTINEL_CLIENT_SECRET,
            "revision": initial["revision"],
        },
    )
    assert saved.status_code == 200
    assert saved.json() == {"configured": True, "revision": 2}
    assert SENTINEL_CLIENT_ID not in saved.text
    assert SENTINEL_CLIENT_SECRET not in saved.text

    unchanged = client.patch(
        f"{SETTINGS}/providers/spotify_api",
        json={"client_id": "", "client_secret": "", "revision": saved.json()["revision"]},
    )
    assert unchanged.status_code == 200
    assert unchanged.json() == {"configured": True, "revision": 3}
    assert SENTINEL_CLIENT_SECRET not in client.get(SETTINGS).text

    service = client.app.state.composition.settings_service()
    assert service.current_spotify_credentials() == (SENTINEL_CLIENT_ID, SENTINEL_CLIENT_SECRET)
    assert service.current_inspection().mode is InspectionMode.FAST

    cleared = client.patch(
        f"{SETTINGS}/providers/spotify_api",
        json={"clear_secret": True, "revision": unchanged.json()["revision"]},
    )
    assert cleared.status_code == 200
    assert cleared.json() == {"configured": False, "revision": 4}
    assert service.current_spotify_credentials() is None
