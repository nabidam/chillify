"""Configuration validation.

Every rule fails closed with a named error before migration or Redis contact.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from chillify.config import (
    ConfigurationError,
    RuntimeEnvironment,
    load_settings,
    preflight_mounted_roots,
)

pytestmark = pytest.mark.unit


def test_valid_environment_produces_settings(valid_environment: dict[str, str]) -> None:
    settings = load_settings(valid_environment)

    assert settings.bind_port == 8787
    assert settings.redis_prefix == "chillify:"
    assert settings.environment is RuntimeEnvironment.PRODUCTION
    assert settings.database_path.name == "chillify.sqlite3"


def test_compose_environment_with_blank_optionals_is_accepted(
    valid_environment: dict[str, str],
) -> None:
    """Compose passes every documented variable, blank when unset.

    A blank value must mean "unset", not a parse failure.
    """
    environment = {
        **valid_environment,
        "CHILLIFY_ALLOWED_ORIGINS": "",
        "CHILLIFY_FIXTURE_ROOT": "",
        "CHILLIFY_BIND_PORT": "8788",
        "CHILLIFY_REDIS_PREFIX": "chillify:",
        "CHILLIFY_LOG_LEVEL": "INFO",
    }

    settings = load_settings(environment)

    assert settings.allowed_origins == ()
    assert settings.fixture_root is None
    assert settings.bind_port == 8788


def test_allowed_origins_parses_a_comma_separated_list(
    valid_environment: dict[str, str],
) -> None:
    environment = {
        **valid_environment,
        "CHILLIFY_ALLOWED_ORIGINS": "http://nas.lan:8787, http://desk.lan:8787",
    }

    settings = load_settings(environment)

    assert settings.allowed_origins == ("http://nas.lan:8787", "http://desk.lan:8787")


def test_settings_read_the_real_process_environment(
    valid_environment: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """load_settings() with no argument uses the deployed code path."""
    for key, value in valid_environment.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("CHILLIFY_ALLOWED_ORIGINS", "")
    monkeypatch.delenv("CHILLIFY_FIXTURE_ROOT", raising=False)

    settings = load_settings()

    assert settings.allowed_origins == ()
    assert str(settings.data_root) == valid_environment["CHILLIFY_DATA_ROOT"]


@pytest.mark.parametrize(
    ("variable", "value", "expected_fragment"),
    [
        ("CHILLIFY_DATA_ROOT", "relative/path", "absolute"),
        ("CHILLIFY_MUSIC_ROOT", "also/relative", "absolute"),
        ("CHILLIFY_BIND_PORT", "0", "CHILLIFY_BIND_PORT"),
        ("CHILLIFY_BIND_PORT", "70000", "CHILLIFY_BIND_PORT"),
        ("REDIS_URL", "amqp://broker.invalid", "redis://"),
        ("CHILLIFY_REDIS_PREFIX", "has whitespace:", "whitespace"),
        ("CHILLIFY_REDIS_PREFIX", "", "empty"),
        ("CHILLIFY_SECRET_KEY", "not-a-fernet-key", "Fernet"),
        ("CHILLIFY_UID", "0", "CHILLIFY_UID"),
        ("CHILLIFY_GID", "-1", "CHILLIFY_GID"),
        ("CHILLIFY_LOG_LEVEL", "CHATTY", "logging level"),
    ],
)
def test_invalid_value_is_rejected_with_a_named_error(
    valid_environment: dict[str, str],
    variable: str,
    value: str,
    expected_fragment: str,
) -> None:
    environment = {**valid_environment, variable: value}

    with pytest.raises(ConfigurationError) as caught:
        load_settings(environment)

    assert caught.value.code == "invalid_configuration"
    assert expected_fragment in caught.value.message


def test_missing_required_variable_is_rejected(valid_environment: dict[str, str]) -> None:
    environment = {
        key: value for key, value in valid_environment.items() if key != "CHILLIFY_SECRET_KEY"
    }

    with pytest.raises(ConfigurationError) as caught:
        load_settings(environment)

    assert "CHILLIFY_SECRET_KEY" in caught.value.message


def test_secret_value_is_never_echoed_in_the_error(valid_environment: dict[str, str]) -> None:
    leaked = "obviously-invalid-but-secret-looking-value"
    environment = {**valid_environment, "CHILLIFY_SECRET_KEY": leaked}

    with pytest.raises(ConfigurationError) as caught:
        load_settings(environment)

    assert leaked not in caught.value.message


def test_identical_roots_are_rejected(valid_environment: dict[str, str]) -> None:
    shared = valid_environment["CHILLIFY_DATA_ROOT"]
    environment = {**valid_environment, "CHILLIFY_MUSIC_ROOT": shared}

    with pytest.raises(ConfigurationError) as caught:
        load_settings(environment)

    assert "distinct" in caught.value.message


class TestGateSafety:
    """Fixture mode fails closed against household state."""

    def _gate_environment(self, repo_root: Path, secret_key: str) -> dict[str, str]:
        gate = repo_root / ".gate" / "gate-1"
        (gate / "data").mkdir(parents=True)
        (gate / "music").mkdir(parents=True)
        (gate / "fixtures").mkdir(parents=True)
        return {
            "CHILLIFY_ENV": "gate",
            "CHILLIFY_DATA_ROOT": str(gate / "data"),
            "CHILLIFY_MUSIC_ROOT": str(gate / "music"),
            "CHILLIFY_FIXTURE_ROOT": str(gate / "fixtures"),
            "CHILLIFY_GATE_ROOT": str(gate),
            "CHILLIFY_REDIS_PREFIX": "chillify:gate:gate-1:",
            "REDIS_URL": "redis://127.0.0.1:6379/9",
            "CHILLIFY_SECRET_KEY": secret_key,
        }

    def test_fully_conforming_gate_configuration_is_accepted(
        self, repo_root: Path, secret_key: str
    ) -> None:
        settings = load_settings(self._gate_environment(repo_root, secret_key))

        assert settings.is_gate

    def test_storage_root_outside_the_gate_tree_is_refused(
        self, repo_root: Path, secret_key: str, tmp_path: Path
    ) -> None:
        household = tmp_path / "household-music"
        household.mkdir()
        environment = {
            **self._gate_environment(repo_root, secret_key),
            "CHILLIFY_MUSIC_ROOT": str(household),
        }

        with pytest.raises(ConfigurationError) as caught:
            load_settings(environment)

        assert caught.value.code == "gate_root_escape"

    def test_non_gate_redis_prefix_is_refused(self, repo_root: Path, secret_key: str) -> None:
        environment = {
            **self._gate_environment(repo_root, secret_key),
            "CHILLIFY_REDIS_PREFIX": "chillify:",
        }

        with pytest.raises(ConfigurationError) as caught:
            load_settings(environment)

        assert caught.value.code == "gate_prefix_invalid"

    def test_missing_fixture_root_is_refused(self, repo_root: Path, secret_key: str) -> None:
        environment = self._gate_environment(repo_root, secret_key)
        del environment["CHILLIFY_FIXTURE_ROOT"]

        with pytest.raises(ConfigurationError) as caught:
            load_settings(environment)

        assert caught.value.code == "fixture_root_missing"

    def test_split_gate_directories_are_refused(self, repo_root: Path, secret_key: str) -> None:
        """Storage roots must share one directory, not merely one boundary.

        The music root here stays inside the declared containment root, so it
        clears the escape check and reaches the split check — which is the one
        under test. A root in a *different* gate tree is refused earlier, by
        `test_storage_root_in_another_gate_tree_is_refused`.
        """
        environment = self._gate_environment(repo_root, secret_key)
        other = repo_root / ".gate" / "gate-1" / "elsewhere" / "music"
        other.mkdir(parents=True)
        environment["CHILLIFY_MUSIC_ROOT"] = str(other)

        with pytest.raises(ConfigurationError) as caught:
            load_settings(environment)

        assert caught.value.code == "gate_roots_split"

    def test_storage_root_in_another_gate_tree_is_refused(
        self, repo_root: Path, secret_key: str
    ) -> None:
        """One gate may not reach into another gate's disposable tree."""
        other = repo_root / ".gate" / "gate-2" / "music"
        other.mkdir(parents=True)
        environment = {
            **self._gate_environment(repo_root, secret_key),
            "CHILLIFY_MUSIC_ROOT": str(other),
        }

        with pytest.raises(ConfigurationError) as caught:
            load_settings(environment)

        assert caught.value.code == "gate_root_escape"

    def test_production_may_not_borrow_the_gate_namespace(
        self, valid_environment: dict[str, str]
    ) -> None:
        environment = {**valid_environment, "CHILLIFY_REDIS_PREFIX": "chillify:gate:sneaky:"}

        with pytest.raises(ConfigurationError) as caught:
            load_settings(environment)

        assert caught.value.code == "gate_prefix_outside_gate"

    def test_production_may_not_declare_a_fixture_root(
        self, valid_environment: dict[str, str], tmp_path: Path
    ) -> None:
        environment = {**valid_environment, "CHILLIFY_FIXTURE_ROOT": str(tmp_path)}

        with pytest.raises(ConfigurationError) as caught:
            load_settings(environment)

        assert caught.value.code == "fixture_root_outside_gate"

    def test_production_may_not_declare_a_gate_root(
        self, valid_environment: dict[str, str], tmp_path: Path
    ) -> None:
        """The containment root is as gate-only as the fixtures it contains.

        A production deployment that names one is either mislabelled or being
        pointed at a disposable tree, and both are refused before startup.
        """
        environment = {**valid_environment, "CHILLIFY_GATE_ROOT": str(tmp_path)}

        with pytest.raises(ConfigurationError) as caught:
            load_settings(environment)

        assert caught.value.code == "fixture_root_outside_gate"

    def test_gate_mode_without_a_declared_containment_root_is_refused(
        self, repo_root: Path, secret_key: str
    ) -> None:
        """Containment is declared, never inferred.

        Gates run through the production Compose file, where the process sees
        only bind mounts, so there is no repository layout to fall back on. An
        undeclared boundary is refused rather than guessed at.
        """
        environment = self._gate_environment(repo_root, secret_key)
        del environment["CHILLIFY_GATE_ROOT"]

        with pytest.raises(ConfigurationError) as caught:
            load_settings(environment)

        assert caught.value.code == "gate_root_missing"

    def test_container_style_mount_paths_are_accepted_under_their_gate_root(
        self, secret_key: str, tmp_path: Path
    ) -> None:
        """The shape a gate actually runs in: mounts, not repository paths.

        Inside the production containers the roots are `/var/lib/chillify/...`
        and no repository is present. The declared containment root is what
        makes that configuration checkable at all.
        """
        mount = tmp_path / "var" / "lib" / "chillify"
        for child in ("data", "music", "fixtures"):
            (mount / child).mkdir(parents=True)
        settings = load_settings(
            {
                "CHILLIFY_ENV": "gate",
                "CHILLIFY_GATE_ROOT": str(mount),
                "CHILLIFY_DATA_ROOT": str(mount / "data"),
                "CHILLIFY_MUSIC_ROOT": str(mount / "music"),
                "CHILLIFY_FIXTURE_ROOT": str(mount / "fixtures"),
                "CHILLIFY_REDIS_PREFIX": "chillify:gate:gate-1:",
                "REDIS_URL": "redis://127.0.0.1:6379/9",
                "CHILLIFY_SECRET_KEY": secret_key,
            }
        )

        assert settings.is_gate
        assert settings.gate_root == mount


class TestReleaseSafety:
    """`release` is disposable (seedable) but never binds fixture adapters.

    Task 20's release gate needs the real production composition — the
    unchanged Compose entry point, real adapters — seeded with fixture data.
    `release` is the environment that makes both true at once: `is_gate` is
    false (so `build_registry` never imports the fixtures module), while
    `is_disposable` is true (so seeding and the containment rules that guard
    it both apply, identically to gate mode).
    """

    def _release_environment(self, repo_root: Path, secret_key: str) -> dict[str, str]:
        release = repo_root / ".gate" / "release"
        (release / "data").mkdir(parents=True)
        (release / "music").mkdir(parents=True)
        return {
            "CHILLIFY_ENV": "release",
            "CHILLIFY_DATA_ROOT": str(release / "data"),
            "CHILLIFY_MUSIC_ROOT": str(release / "music"),
            "CHILLIFY_GATE_ROOT": str(release),
            "CHILLIFY_REDIS_PREFIX": "chillify:gate:release:",
            "REDIS_URL": "redis://127.0.0.1:6379/9",
            "CHILLIFY_SECRET_KEY": secret_key,
        }

    def test_fully_conforming_release_configuration_is_accepted(
        self, repo_root: Path, secret_key: str
    ) -> None:
        settings = load_settings(self._release_environment(repo_root, secret_key))

        assert settings.is_disposable
        assert not settings.is_gate

    def test_storage_root_outside_the_release_tree_is_refused(
        self, repo_root: Path, secret_key: str, tmp_path: Path
    ) -> None:
        household = tmp_path / "household-music"
        household.mkdir()
        environment = {
            **self._release_environment(repo_root, secret_key),
            "CHILLIFY_MUSIC_ROOT": str(household),
        }

        with pytest.raises(ConfigurationError) as caught:
            load_settings(environment)

        assert caught.value.code == "gate_root_escape"

    def test_release_without_a_declared_containment_root_is_refused(
        self, repo_root: Path, secret_key: str
    ) -> None:
        environment = self._release_environment(repo_root, secret_key)
        del environment["CHILLIFY_GATE_ROOT"]

        with pytest.raises(ConfigurationError) as caught:
            load_settings(environment)

        assert caught.value.code == "gate_root_missing"

    def test_release_may_not_declare_a_fixture_root(self, repo_root: Path, secret_key: str) -> None:
        """Release proves the real composition, never fixture adapters."""
        environment = {
            **self._release_environment(repo_root, secret_key),
            "CHILLIFY_FIXTURE_ROOT": str(repo_root / ".gate" / "release"),
        }

        with pytest.raises(ConfigurationError) as caught:
            load_settings(environment)

        assert caught.value.code == "fixture_root_outside_gate"

    def test_release_requires_the_gate_redis_namespace(
        self, repo_root: Path, secret_key: str
    ) -> None:
        environment = {
            **self._release_environment(repo_root, secret_key),
            "CHILLIFY_REDIS_PREFIX": "chillify:",
        }

        with pytest.raises(ConfigurationError) as caught:
            load_settings(environment)

        assert caught.value.code == "gate_prefix_invalid"

    def test_production_is_not_disposable(self, valid_environment: dict[str, str]) -> None:
        settings = load_settings(valid_environment)

        assert not settings.is_disposable
        assert not settings.is_gate


class TestMountedRootPreflight:
    def test_writable_roots_are_reported_with_the_expected_identity(
        self, valid_environment: dict[str, str]
    ) -> None:
        settings = load_settings(valid_environment)

        reports = preflight_mounted_roots(settings)

        assert [report.variable for report in reports] == [
            "CHILLIFY_DATA_ROOT",
            "CHILLIFY_MUSIC_ROOT",
        ]
        assert all(report.expected_uid == settings.uid for report in reports)

    def test_absent_root_names_the_path_and_expected_identity(
        self, valid_environment: dict[str, str], tmp_path: Path
    ) -> None:
        missing = tmp_path / "never-mounted"
        settings = load_settings({**valid_environment, "CHILLIFY_MUSIC_ROOT": str(missing)})

        with pytest.raises(ConfigurationError) as caught:
            preflight_mounted_roots(settings)

        assert caught.value.code == "mounted_root_absent"
        assert str(missing) in caught.value.message
        assert f"{settings.uid}:{settings.gid}" in caught.value.message

    def test_unwritable_root_is_refused(
        self, valid_environment: dict[str, str], disposable_root: Path
    ) -> None:
        locked = disposable_root / "read-only-mount"
        locked.mkdir()
        locked.chmod(0o500)
        settings = load_settings({**valid_environment, "CHILLIFY_MUSIC_ROOT": str(locked)})

        try:
            with pytest.raises(ConfigurationError) as caught:
                preflight_mounted_roots(settings)
            assert caught.value.code == "mounted_root_unwritable"
        finally:
            locked.chmod(0o700)
