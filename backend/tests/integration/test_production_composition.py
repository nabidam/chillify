"""Task 19 — the production composition resolves real adapters.

Every other integration/contract test in this suite deliberately runs against
`gate_composition` (fixture adapters, disposable Redis) so no test needs a live
provider. This file is the one place that proves the *other* half of the
composition root: `build_composition` against a `CHILLIFY_ENV=production`
environment binds the real Deezer/SpotDL/yt-dlp/HTTP-artwork classes named in
ARCHITECTURE's registry table, and `system_status()` reaches a legitimate
ready-or-degraded state on a disposable root — without calling out to any
provider. Building the registry only imports and instantiates adapters; it
never invokes them, so this stays true to "provider tests never need live
network" while still proving the classes bound are the real ones, not
fixtures.

The script-level behavior of `scripts/production_canary.sh` (household-root
refusal, live docker compose, network-failure handling) is covered at two
other layers instead of here: the fast, no-docker refusals it can hit before a
single container starts are contract-tested in this same file below; the full
live behavior — bringing up the real containers, reporting every adapter/tool,
and the network-failure-without-fallback proof — is exercised by
`frontend/tests/e2e/production-composition.spec.ts` (gate 4), which is the one
place in this repository already committed to driving real Docker Compose and
real network for a canary (ARCHITECTURE's "container canary" family).
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from chillify.composition import Composition, Health, build_composition
from chillify.config import load_settings
from chillify.domain.jobs import JobProvider
from chillify.infrastructure.providers.artwork_http import HttpArtworkFetcher
from chillify.infrastructure.providers.deezer import DeezerDiscoveryProvider
from chillify.infrastructure.providers.spotdl import SpotdlAcquisitionProvider, SpotdlInspector
from chillify.infrastructure.providers.ytdlp import YouTubeInspector, YtDlpAcquisitionProvider

pytestmark = pytest.mark.integration

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent
CANARY = REPO_ROOT / "scripts" / "production_canary.sh"


def _migrate(database_path: Path) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database_path}")
    command.upgrade(config, "head")


@pytest.fixture
def production_composition(
    storage_roots: tuple[Path, Path], secret_key: str
) -> Iterator[Composition]:
    """A migrated, production-mode composition on disposable roots.

    Redis is deliberately pointed at a port nothing listens on: acquisition
    must degrade, never make the library unready, and forcing the failure
    makes the degraded branch deterministic instead of depending on whether a
    developer happens to have a local Redis running.
    """
    data_root, music_root = storage_roots
    environment = {
        "CHILLIFY_DATA_ROOT": str(data_root),
        "CHILLIFY_MUSIC_ROOT": str(music_root),
        "REDIS_URL": "redis://127.0.0.1:1/0",
        "CHILLIFY_SECRET_KEY": secret_key,
        "CHILLIFY_ENV": "production",
    }
    _migrate(data_root / "db" / "chillify.sqlite3")
    settings = load_settings(environment)
    composition = build_composition(settings)
    try:
        yield composition
    finally:
        composition.dispose()


class TestRealAdapterResolution:
    """Criterion 3 (also exercised live at gate 4): real classes, not fixtures."""

    def test_discovery_is_the_real_deezer_adapter(
        self, production_composition: Composition
    ) -> None:
        assert isinstance(
            production_composition.registry.discovery["deezer"], DeezerDiscoveryProvider
        )

    def test_acquisition_adapters_are_the_real_ytdlp_and_spotdl_classes(
        self, production_composition: Composition
    ) -> None:
        registry = production_composition.registry
        assert isinstance(registry.acquisition[JobProvider.YT_DLP], YtDlpAcquisitionProvider)
        assert isinstance(registry.acquisition[JobProvider.SPOTDL], SpotdlAcquisitionProvider)

    def test_link_inspectors_are_the_real_ytdlp_and_spotdl_classes(
        self, production_composition: Composition
    ) -> None:
        registry = production_composition.registry
        assert isinstance(registry.link_inspectors[JobProvider.YT_DLP], YouTubeInspector)
        assert isinstance(registry.link_inspectors[JobProvider.SPOTDL], SpotdlInspector)

    def test_artwork_fetcher_is_the_real_http_adapter(
        self, production_composition: Composition
    ) -> None:
        assert isinstance(production_composition.registry.artwork["url"], HttpArtworkFetcher)

    def test_no_fixture_module_is_importable_from_the_production_registry(
        self, production_composition: Composition
    ) -> None:
        """None of the bound adapters come from the fixtures module.

        `build_registry` only imports `infrastructure.providers.fixtures` inside
        its gate branch, so a production registry never even reaches that
        import — this asserts the observable result of that import-time
        separation, not the import itself.
        """
        for adapter in (
            *production_composition.registry.discovery.values(),
            *production_composition.registry.acquisition.values(),
            *production_composition.registry.link_inspectors.values(),
            *production_composition.registry.artwork.values(),
        ):
            assert "fixtures" not in type(adapter).__module__


class TestReadyAndDegradedStates:
    """Criterion 1: real composition reaches a legitimate state, never crashes."""

    def test_a_migrated_disposable_root_is_ready(self, production_composition: Composition) -> None:
        status = production_composition.system_status()
        assert status.ready is True
        assert status.database.health is Health.OK
        assert status.environment == "production"

    def test_unreachable_redis_degrades_acquisition_without_failing_readiness(
        self, production_composition: Composition
    ) -> None:
        status = production_composition.system_status()
        assert status.degraded is True
        assert status.redis.health is Health.UNAVAILABLE
        # Local use is unaffected by the degraded queue transport.
        assert status.ready is True

    def test_every_named_tool_and_provider_is_reported(
        self, production_composition: Composition
    ) -> None:
        status = production_composition.system_status()
        tool_names = {tool.name for tool in status.tools}
        assert tool_names == {"ffmpeg", "ffprobe", "yt_dlp", "spotdl", "deno"}
        provider_names = {provider.name for provider in status.providers}
        assert provider_names == {"deezer", "spotdl", "yt_dlp", "lastfm"}


def _run(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(CANARY), *arguments],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO_ROOT,
        timeout=30,
        env={**os.environ, "PATH": os.environ.get("PATH", "")},
    )


@pytest.mark.contract
class TestCanaryFailsClosedBeforeAnyContainerStarts:
    """The canary's fast refusals — everything it can check before `docker
    compose up` ever runs. The live behavior these refusals guard (bringing up
    real containers, reporting real adapters, the network-failure proof) is
    exercised live, against the real script, by the gate-4 e2e spec — running
    it here too would mean building and starting the production stack once per
    assertion, which is the gate's job, not a unit of this contract."""

    def test_the_script_is_executable(self) -> None:
        assert CANARY.is_file()
        assert os.access(CANARY, os.X_OK)

    def test_a_missing_env_file_flag_is_a_usage_error(self) -> None:
        result = _run()

        assert result.returncode == 2
        assert "usage" in result.stderr.lower()

    def test_a_nonexistent_env_file_is_refused(self, tmp_path: Path) -> None:
        result = _run("--env-file", str(tmp_path / "does-not-exist" / ".env"))

        assert result.returncode == 1
        assert "does not exist" in result.stderr

    def test_an_env_file_outside_gate_is_refused(self, tmp_path: Path) -> None:
        household = tmp_path / "household.env"
        household.write_text("CHILLIFY_ENV=production\n", encoding="utf-8")

        result = _run("--env-file", str(household))

        assert result.returncode == 1
        assert "not beneath" in result.stderr

    def test_a_gate_mode_env_file_is_refused(self) -> None:
        gate_root = REPO_ROOT / ".gate" / "canary-contract-gate-mode"
        env_file = gate_root / ".env"
        gate_root.mkdir(parents=True, exist_ok=True)
        env_file.write_text(
            "CHILLIFY_ENV=gate\n"
            f"CHILLIFY_DATA_ROOT={gate_root}/data\n"
            f"CHILLIFY_MUSIC_ROOT={gate_root}/music\n"
            f"CHILLIFY_GATE_ROOT={gate_root}\n"
            f"CHILLIFY_FIXTURE_ROOT={gate_root}/fixtures\n",
            encoding="utf-8",
        )
        try:
            result = _run("--env-file", str(env_file))

            assert result.returncode == 1
            assert "gate" in result.stderr.lower()
        finally:
            env_file.unlink(missing_ok=True)
            gate_root.rmdir()

    def test_a_household_data_root_is_refused_even_inside_a_disposable_env_file(
        self,
    ) -> None:
        """The `.env` file itself can live in `.gate/`; the roots it names must
        too. This is the "refuses household roots" half of criterion 2: a
        gate-shaped env file that was hand-edited (or copy-pasted) to point at
        real household storage must never reach `docker compose up`."""
        gate_root = REPO_ROOT / ".gate" / "canary-contract-household-root"
        env_file = gate_root / ".env"
        gate_root.mkdir(parents=True, exist_ok=True)
        env_file.write_text(
            "CHILLIFY_ENV=production\n"
            "CHILLIFY_DATA_ROOT=/srv/chillify/data\n"
            "CHILLIFY_MUSIC_ROOT=/srv/chillify/music\n",
            encoding="utf-8",
        )
        try:
            result = _run("--env-file", str(env_file))

            assert result.returncode == 1
            assert "household" in result.stderr.lower()
        finally:
            env_file.unlink(missing_ok=True)
            gate_root.rmdir()

    def test_an_unrecognized_flag_is_a_usage_error(self) -> None:
        result = _run("--not-a-real-flag")

        assert result.returncode == 2
        assert "usage" in result.stderr.lower()
