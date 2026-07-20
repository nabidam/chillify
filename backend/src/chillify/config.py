"""Validated deployment configuration.

Every rule in ARCHITECTURE section 12 is enforced here, at process startup,
before any migration or Redis mutation. Parsing rules are pure so they can be
exercised without a filesystem; the mounted-root preflight is a separate,
explicitly invoked step.
"""

from __future__ import annotations

import logging
import os
import re
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Final, Self

from cryptography.fernet import Fernet
from pydantic import Field, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic_settings.exceptions import SettingsError

_WHITESPACE: Final = re.compile(r"\s")
_REDIS_SCHEMES: Final = ("redis://", "rediss://")
_GATE_PREFIX: Final = "chillify:gate:"

# Pseudo and container-layer filesystems are never acceptable durable roots.
# NFR-12 requires household media and data to live outside writable image layers.
_REJECTED_FILESYSTEMS: Final = frozenset(
    {"overlay", "overlayfs", "tmpfs", "ramfs", "proc", "sysfs", "devtmpfs", "cgroup2"}
)


class ConfigurationError(Exception):
    """A named, operator-facing configuration failure.

    The message names the variable and the rule it violated. It never contains a
    secret value; only the offending variable name and the expected shape.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class RuntimeEnvironment(StrEnum):
    PRODUCTION = "production"
    GATE = "gate"


class Settings(BaseSettings):
    """Deployment configuration parsed and validated from the environment."""

    model_config = SettingsConfigDict(
        env_prefix="",
        extra="ignore",
        frozen=True,
        case_sensitive=True,
        # Without this, pydantic-settings JSON-decodes any complex-typed field
        # before validation runs, so an empty CHILLIFY_ALLOWED_ORIGINS fails to
        # parse instead of meaning "no extra origins". The field validators own
        # every conversion here.
        enable_decoding=False,
    )

    bind_port: int = Field(default=8787, ge=1, le=65535, alias="CHILLIFY_BIND_PORT")
    data_root: Path = Field(alias="CHILLIFY_DATA_ROOT")
    music_root: Path = Field(alias="CHILLIFY_MUSIC_ROOT")
    redis_url: str = Field(alias="REDIS_URL")
    redis_prefix: str = Field(default="chillify:", alias="CHILLIFY_REDIS_PREFIX")
    secret_key: str = Field(alias="CHILLIFY_SECRET_KEY")
    uid: int = Field(default=1000, ge=1, alias="CHILLIFY_UID")
    gid: int = Field(default=1000, ge=1, alias="CHILLIFY_GID")
    log_level: str = Field(default="INFO", alias="CHILLIFY_LOG_LEVEL")
    allowed_origins: tuple[str, ...] = Field(default=(), alias="CHILLIFY_ALLOWED_ORIGINS")
    environment: RuntimeEnvironment = Field(
        default=RuntimeEnvironment.PRODUCTION, alias="CHILLIFY_ENV"
    )
    fixture_root: Path | None = Field(default=None, alias="CHILLIFY_FIXTURE_ROOT")

    @field_validator("fixture_root", mode="before")
    @classmethod
    def _blank_is_unset(cls, value: object) -> object:
        """Compose always passes this variable, blank when the operator left it
        empty. Blank means unset, not an invalid path."""
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("data_root", "music_root", "fixture_root")
    @classmethod
    def _absolute_path(cls, value: Path | None) -> Path | None:
        if value is None:
            return None
        if not value.is_absolute():
            raise ValueError("must be an absolute path")
        # Resolve without requiring existence so parsing stays filesystem-free;
        # existence and writability belong to the mounted-root preflight.
        return Path(os.path.normpath(str(value)))

    @field_validator("redis_url")
    @classmethod
    def _redis_scheme(cls, value: str) -> str:
        if not value.startswith(_REDIS_SCHEMES):
            raise ValueError("must start with redis:// or rediss://")
        return value

    @field_validator("redis_prefix")
    @classmethod
    def _prefix_shape(cls, value: str) -> str:
        if not value:
            raise ValueError("must not be empty")
        if _WHITESPACE.search(value):
            raise ValueError("must not contain whitespace")
        return value

    @field_validator("secret_key")
    @classmethod
    def _fernet_key(cls, value: str) -> str:
        try:
            Fernet(value.encode("ascii"))
        except (ValueError, TypeError, UnicodeEncodeError) as exc:
            raise ValueError("must be a URL-safe base64-encoded 32-byte Fernet key") from exc
        return value

    @field_validator("log_level")
    @classmethod
    def _standard_level(cls, value: str) -> str:
        level = value.strip().upper()
        if level not in logging.getLevelNamesMapping():
            raise ValueError("must be a standard logging level name")
        return level

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def _origin_list(cls, value: object) -> object:
        if isinstance(value, str):
            return tuple(origin.strip() for origin in value.split(",") if origin.strip())
        return value

    @model_validator(mode="after")
    def _distinct_roots(self) -> Self:
        if self.data_root == self.music_root:
            raise ValueError("CHILLIFY_DATA_ROOT and CHILLIFY_MUSIC_ROOT must be distinct paths")
        return self

    @property
    def database_path(self) -> Path:
        return self.data_root / "db" / "chillify.sqlite3"

    @property
    def database_url(self) -> str:
        return f"sqlite+pysqlite:///{self.database_path}"

    @property
    def is_gate(self) -> bool:
        return self.environment is RuntimeEnvironment.GATE


def load_settings(
    environ: dict[str, str] | None = None, *, repo_root: Path | None = None
) -> Settings:
    """Parse and validate configuration, raising one named ConfigurationError.

    `repo_root` anchors the gate-mode safety check; it defaults to the repository
    that contains this package so production callers need not supply it.
    """
    try:
        # Construct through the environment source rather than init keyword
        # arguments, so a supplied mapping exercises exactly the code path a
        # deployed process uses. Passing kwargs would skip that source and hide
        # env-parsing failures from tests.
        with _environment(environ):
            # Every value comes from the environment source, which mypy
            # cannot see as satisfying the required fields.
            settings = Settings()  # type: ignore[call-arg]
    except ValidationError as exc:
        raise ConfigurationError("invalid_configuration", _format(exc)) from exc
    except SettingsError as exc:
        raise ConfigurationError("invalid_configuration", str(exc)) from exc
    _assert_gate_safety(settings, repo_root=repo_root or default_repo_root())
    return settings


@contextmanager
def _environment(environ: dict[str, str] | None) -> Iterator[None]:
    """Temporarily replace the process environment with `environ`."""
    if environ is None:
        yield
        return
    original = dict(os.environ)
    os.environ.clear()
    os.environ.update(environ)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(original)


def default_repo_root() -> Path:
    """The repository root: backend/src/chillify/config.py -> four parents up."""
    return Path(__file__).resolve().parents[3]


def _format(exc: ValidationError) -> str:
    parts = []
    for error in exc.errors():
        name = str(error["loc"][0]) if error["loc"] else "configuration"
        parts.append(f"{name}: {error['msg']}")
    return "Invalid deployment configuration — " + "; ".join(sorted(parts))


def _assert_gate_safety(settings: Settings, *, repo_root: Path) -> None:
    """Fail closed unless every gate-mode condition holds.

    Fixture adapters may bind only when the environment is `gate`, the fixture
    root and both storage roots resolve beneath the repository `.gate/` tree, and
    the Redis prefix is gate-namespaced. Any mismatch is refused here, before
    migration or Redis contact.
    """
    if not settings.is_gate:
        if settings.fixture_root is not None:
            raise ConfigurationError(
                "fixture_root_outside_gate",
                "CHILLIFY_FIXTURE_ROOT is only permitted when CHILLIFY_ENV=gate.",
            )
        if settings.redis_prefix.startswith(_GATE_PREFIX):
            raise ConfigurationError(
                "gate_prefix_outside_gate",
                "CHILLIFY_REDIS_PREFIX may only use the "
                f"'{_GATE_PREFIX}' namespace when CHILLIFY_ENV=gate.",
            )
        return

    gate_root = Path(os.path.normpath(str(repo_root / ".gate")))
    if settings.fixture_root is None:
        raise ConfigurationError(
            "fixture_root_missing",
            "CHILLIFY_ENV=gate requires CHILLIFY_FIXTURE_ROOT beneath the "
            "repository .gate/ directory.",
        )
    for name, value in (
        ("CHILLIFY_FIXTURE_ROOT", settings.fixture_root),
        ("CHILLIFY_DATA_ROOT", settings.data_root),
        ("CHILLIFY_MUSIC_ROOT", settings.music_root),
    ):
        if not _is_beneath(value, gate_root):
            raise ConfigurationError(
                "gate_root_escape",
                f"{name} must resolve beneath {gate_root} when CHILLIFY_ENV=gate.",
            )
    if settings.data_root.parent != settings.music_root.parent:
        raise ConfigurationError(
            "gate_roots_split",
            "CHILLIFY_DATA_ROOT and CHILLIFY_MUSIC_ROOT must share one gate "
            "directory when CHILLIFY_ENV=gate.",
        )
    if not settings.redis_prefix.startswith(_GATE_PREFIX):
        raise ConfigurationError(
            "gate_prefix_invalid",
            f"CHILLIFY_REDIS_PREFIX must begin with '{_GATE_PREFIX}' when CHILLIFY_ENV=gate.",
        )


def _is_beneath(candidate: Path, root: Path) -> bool:
    return candidate != root and root in candidate.parents


@dataclass(frozen=True, slots=True)
class MountedRootReport:
    """One mounted-root preflight result, safe to print verbatim."""

    variable: str
    path: Path
    expected_uid: int
    expected_gid: int


def preflight_mounted_roots(settings: Settings) -> tuple[MountedRootReport, ...]:
    """Report, then fail before migration if a mounted root is unusable.

    Each root must exist as a directory on a normal filesystem and be writable by
    the configured identity. The error names the exact path and the expected
    UID/GID so the operator can fix ownership without reading container internals.
    """
    reports = []
    for variable, path in (
        ("CHILLIFY_DATA_ROOT", settings.data_root),
        ("CHILLIFY_MUSIC_ROOT", settings.music_root),
    ):
        reports.append(
            MountedRootReport(
                variable=variable,
                path=path,
                expected_uid=settings.uid,
                expected_gid=settings.gid,
            )
        )
        if not path.is_dir():
            raise ConfigurationError(
                "mounted_root_absent",
                f"{variable} {path} is not a mounted directory; expected a normal "
                f"filesystem owned by {settings.uid}:{settings.gid}.",
            )
        filesystem = filesystem_type(path)
        if filesystem in _REJECTED_FILESYSTEMS:
            raise ConfigurationError(
                "mounted_root_not_normal",
                f"{variable} {path} is on '{filesystem}', not a normal mounted "
                "filesystem; durable data must live outside container layers.",
            )
        if not _is_writable(path):
            raise ConfigurationError(
                "mounted_root_unwritable",
                f"{variable} {path} is not writable by {settings.uid}:{settings.gid}.",
            )
    return tuple(reports)


def filesystem_type(path: Path) -> str:
    """Resolve the mount source filesystem for `path`, or 'unknown' off Linux."""
    mounts = Path("/proc/self/mounts")
    if not mounts.exists():
        return "unknown"
    target = path.resolve()
    best: tuple[int, str] = (-1, "unknown")
    for line in mounts.read_text(encoding="utf-8", errors="replace").splitlines():
        fields = line.split()
        if len(fields) < 3:
            continue
        mount_point = Path(fields[1].replace("\\040", " "))
        if mount_point == target or mount_point in target.parents:
            depth = len(mount_point.parts)
            if depth > best[0]:
                best = (depth, fields[2])
    return best[1]


def _is_writable(path: Path) -> bool:
    probe = path / f".chillify-write-probe-{uuid.uuid4().hex}"
    try:
        probe.touch()
    except OSError:
        return False
    finally:
        probe.unlink(missing_ok=True)
    return True
