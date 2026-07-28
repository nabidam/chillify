"""Composition root.

Every real implementation is bound here and nowhere else. Fixture adapters may
only be resolved when the gate-safety conditions in `config` already passed, and
production mode never imports them.

Readiness and degradation are deliberately distinct: readiness means valid
configuration, a migrated database, and writable mounted roots. Redis and
provider failures degrade acquisition; they never make the library unreadable.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Final

from celery import Celery
from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from chillify.application.artwork import ArtworkService
from chillify.application.deletion import DeletionService
from chillify.application.downloads import DownloadService
from chillify.application.inspection import InspectionService
from chillify.application.library import LibraryService
from chillify.application.links import LinkInspectionService, RegisteredInspector
from chillify.application.metadata import MetadataService
from chillify.application.playlists import PlaylistService
from chillify.application.reconciliation import ReconciliationService
from chillify.application.search import SearchService
from chillify.application.settings import SettingsService
from chillify.config import Settings, preflight_mounted_roots
from chillify.domain.errors import ProviderDisabledError
from chillify.domain.jobs import JobProvider
from chillify.infrastructure.db.engine import create_database_engine, create_session_factory
from chillify.infrastructure.logging.setup import redactor
from chillify.infrastructure.media.recovery import MediaRecoveryService
from chillify.infrastructure.providers.registry import ProviderRegistry, build_registry
from chillify.infrastructure.queue.celery_app import create_celery_app, make_dispatcher
from chillify.infrastructure.security.secrets import SecretCipher

logger = logging.getLogger(__name__)

TOOL_PROBE_TIMEOUT_SECONDS: Final = 5.0
REDIS_PROBE_TIMEOUT_SECONDS: Final = 2.0

# Tools the acquisition path shells out to, as argument vectors. There is no
# shell involved and no metadata ever reaches these argument lists.
#
# The third element names an environment variable holding an absolute path to
# the executable. SpotDL in particular lives in an isolated environment that is
# deliberately kept off PATH, so it is only reachable through its variable.
_TOOL_PROBES: Final = (
    ("ffmpeg", ("ffmpeg", "-version"), "CHILLIFY_FFMPEG_BIN"),
    ("ffprobe", ("ffprobe", "-version"), "CHILLIFY_FFPROBE_BIN"),
    ("yt_dlp", ("yt-dlp", "--version"), "CHILLIFY_YT_DLP_BIN"),
    ("spotdl", ("spotdl", "--version"), "CHILLIFY_SPOTDL_BIN"),
    ("deno", ("deno", "--version"), "CHILLIFY_DENO_BIN"),
)

_PROVIDER_KEYS: Final = (
    "provider.deezer",
    "provider.spotdl",
    "provider.yt_dlp",
    "provider.lastfm",
)


class Health(StrEnum):
    OK = "ok"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class ComponentStatus:
    name: str
    health: Health
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class ProviderStatus:
    name: str
    enabled: bool
    configured: bool


@dataclass(frozen=True, slots=True)
class SystemStatus:
    ready: bool
    degraded: bool
    environment: str
    checked_at: str
    database: ComponentStatus
    storage: tuple[ComponentStatus, ...]
    redis: ComponentStatus
    tools: tuple[ComponentStatus, ...]
    providers: tuple[ProviderStatus, ...]


@dataclass(slots=True)
class Composition:
    """Bound runtime dependencies for one process."""

    settings: Settings
    engine: Engine
    session_factory: sessionmaker[Session]
    registry: ProviderRegistry = field(default_factory=ProviderRegistry)
    _tool_cache: dict[str, ComponentStatus] = field(default_factory=dict)
    _celery_app: Celery | None = None
    _inspection_service: InspectionService | None = None

    def dispose(self) -> None:
        if self._inspection_service is not None:
            self._inspection_service.shutdown()
        self.engine.dispose()

    # -- use cases --------------------------------------------------------

    def library_service(self) -> LibraryService:
        """Bind the profile, library, and stream use cases to this process."""
        return LibraryService(
            session_factory=self.session_factory,
            music_root=self.settings.music_root,
        )

    def metadata_service(self) -> MetadataService:
        """Bind the recoverable track-correction use case to this process."""
        return MetadataService(
            session_factory=self.session_factory,
            music_root=self.settings.music_root,
        )

    def deletion_service(self) -> DeletionService:
        """Bind the recoverable permanent-deletion use case to this process."""
        return DeletionService(
            session_factory=self.session_factory,
            music_root=self.settings.music_root,
        )

    def media_recovery_service(self) -> MediaRecoveryService:
        """Bind startup recovery of interrupted edit and deletion mutations."""
        return MediaRecoveryService(
            session_factory=self.session_factory,
            music_root=self.settings.music_root,
        )

    def playlist_service(self) -> PlaylistService:
        """Bind the per-profile playlist use cases."""
        return PlaylistService(session_factory=self.session_factory)

    def artwork_service(self) -> ArtworkService:
        """Bind cover staging to the adapters this environment allows."""
        return ArtworkService(
            session_factory=self.session_factory,
            music_root=self.settings.music_root,
            registry=self.registry,
        )

    def search_service(self) -> SearchService:
        """Bind explicit online discovery to the adapters this environment allows.

        The proxy is supplied as a callable bound to a fresh `SettingsService`,
        not a snapshotted value: `current_proxy_url` re-reads the database on
        every call, so a proxy change an operator saves in Settings takes effect
        on the very next search without restarting anything.
        """
        return SearchService(
            session_factory=self.session_factory,
            registry=self.registry,
            proxy_provider=self.settings_service().current_proxy_url,
        )

    def settings_service(self) -> SettingsService:
        """Bind the proxy and provider settings use cases.

        The cipher is built from the already-validated deployment key, so the
        key is parsed once at startup and never re-read from the environment
        here.
        """
        return SettingsService(
            session_factory=self.session_factory,
            cipher=SecretCipher.from_key(self.settings.secret_key),
        )

    def link_inspection_service(self) -> LinkInspectionService:
        """Bind direct-link inspection to the inspectors this environment allows."""
        inspectors = tuple(
            RegisteredInspector(provider=provider, inspector=inspector)
            for provider, inspector in self.registry.link_inspectors.items()
        )
        # Same runtime-freshness rationale as `search_service`: the callable
        # re-reads the saved proxy from the database on every inspection.
        return LinkInspectionService(
            session_factory=self.session_factory,
            inspectors=inspectors,
            proxy_provider=self.settings_service().current_proxy_url,
        )

    def inspection_service(self) -> InspectionService:
        """Bind tracked inspections to the policy and current saved settings."""
        if self._inspection_service is not None:
            return self._inspection_service
        spotify_api = self.registry.spotify_api
        spotdl = self.registry.link_inspectors.get(JobProvider.SPOTDL)
        if spotify_api is None or spotdl is None:
            raise ProviderDisabledError("Link inspection is unavailable in this deployment.")
        self._inspection_service = InspectionService(
            session_factory=self.session_factory,
            spotify_api=spotify_api,
            spotdl=spotdl,
            youtube=self.registry.link_inspectors.get(JobProvider.YT_DLP),
            settings_provider=self.settings_service().current_inspection,
            proxy_provider=self.settings_service().current_proxy_url,
        )
        return self._inspection_service

    def download_service(self, *, worker_identity: str = "api") -> DownloadService:
        """Bind the acquisition use cases.

        The API and the worker build the same service against the same
        database; only the lease owner differs, so a job's history records
        which process performed it.
        """
        # Same runtime-freshness rationale as `search_service`: the callable
        # re-reads the saved proxy from the database on every use, which matters
        # most here — the worker builds one `DownloadService` per job and a job
        # can run for minutes, so a mid-run proxy change must still apply.
        return DownloadService(
            session_factory=self.session_factory,
            registry=self.registry,
            music_root=self.settings.music_root,
            dispatch=make_dispatcher(self.celery_app(), self.settings),
            queue_reachable=self.is_queue_reachable,
            worker_identity=worker_identity,
            proxy_provider=self.settings_service().current_proxy_url,
        )

    def reconciliation_service(self) -> ReconciliationService:
        """Bind interrupted-job recovery to this process's database and broker."""
        return ReconciliationService(
            session_factory=self.session_factory,
            music_root=self.settings.music_root,
            dispatch=make_dispatcher(self.celery_app(), self.settings),
            queue_reachable=self.is_queue_reachable,
        )

    def celery_app(self) -> Celery:
        """The process's Celery application, built once and reused."""
        if self._celery_app is None:
            self._celery_app = create_celery_app(self.settings)
        return self._celery_app

    def is_queue_reachable(self) -> bool:
        """Whether the queue transport can accept work right now."""
        return self._redis_status().health is Health.OK

    # -- status -----------------------------------------------------------

    def system_status(self, *, refresh_tools: bool = False) -> SystemStatus:
        """Assemble current status. Local process checks only; no provider calls."""
        database = self._database_status()
        storage = self._storage_status()
        redis_status = self._redis_status()
        tools = self._tool_status(refresh=refresh_tools)
        providers = self._provider_status()

        ready = database.health is Health.OK and all(
            component.health is Health.OK for component in storage
        )
        degraded = redis_status.health is not Health.OK or any(
            tool.health is not Health.OK for tool in tools
        )
        return SystemStatus(
            ready=ready,
            degraded=degraded,
            environment=str(self.settings.environment),
            checked_at=datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            database=database,
            storage=tuple(storage),
            redis=redis_status,
            tools=tuple(tools),
            providers=tuple(providers),
        )

    def _database_status(self) -> ComponentStatus:
        try:
            with self.engine.connect() as connection:
                revision = connection.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar_one_or_none()
                journal = connection.execute(text("PRAGMA journal_mode")).scalar_one()
        except SQLAlchemyError as exc:
            logger.warning("database status probe failed", extra={"error": str(exc)})
            return ComponentStatus("database", Health.UNAVAILABLE, "database is not readable")
        if revision is None:
            return ComponentStatus("database", Health.UNAVAILABLE, "schema is not migrated")
        if str(journal).lower() != "wal":
            return ComponentStatus(
                "database", Health.DEGRADED, f"journal mode is {journal}, expected wal"
            )
        return ComponentStatus("database", Health.OK, f"migrated to {revision}")

    def _storage_status(self) -> list[ComponentStatus]:
        statuses = []
        for name, root in (
            ("data_root", self.settings.data_root),
            ("music_root", self.settings.music_root),
        ):
            if not root.is_dir():
                statuses.append(ComponentStatus(name, Health.UNAVAILABLE, "mounted path is absent"))
                continue
            usage = shutil.disk_usage(root)
            free_mib = usage.free // (1024 * 1024)
            health = Health.OK if free_mib > 256 else Health.DEGRADED
            statuses.append(ComponentStatus(name, health, f"{free_mib} MiB free"))
        return statuses

    def _redis_status(self) -> ComponentStatus:
        """Probe the operator's Redis. Its loss degrades acquisition only."""
        try:
            import redis

            client = redis.Redis.from_url(
                self.settings.redis_url,
                socket_connect_timeout=REDIS_PROBE_TIMEOUT_SECONDS,
                socket_timeout=REDIS_PROBE_TIMEOUT_SECONDS,
            )
            try:
                client.ping()
            finally:
                client.close()
        except Exception as exc:
            logger.info("redis unavailable; acquisition is degraded", extra={"error": str(exc)})
            return ComponentStatus("redis", Health.UNAVAILABLE, "queue transport is unreachable")
        return ComponentStatus("redis", Health.OK, "queue transport reachable")

    def _tool_status(self, *, refresh: bool) -> list[ComponentStatus]:
        statuses = []
        for name, argv, path_variable in _TOOL_PROBES:
            if not refresh and name in self._tool_cache:
                statuses.append(self._tool_cache[name])
                continue
            status = _probe_tool(name, argv, path_variable)
            self._tool_cache[name] = status
            statuses.append(status)
        return statuses

    def _provider_status(self) -> list[ProviderStatus]:
        """Read the seeded provider rows.

        A missing row is configuration corruption, not a reason to guess a
        default: the provider is reported disabled and unconfigured so Settings
        can surface a repairable error.
        """
        rows: dict[str, str] = {}
        try:
            with self.engine.connect() as connection:
                for key, public_json in connection.execute(
                    text("SELECT key, public_json FROM settings")
                ):
                    rows[str(key)] = str(public_json)
        except SQLAlchemyError as exc:
            logger.warning("provider settings unreadable", extra={"error": str(exc)})

        statuses = []
        for key in _PROVIDER_KEYS:
            name = key.removeprefix("provider.")
            raw = rows.get(key)
            if raw is None:
                statuses.append(ProviderStatus(name, enabled=False, configured=False))
                continue
            try:
                public = json.loads(raw)
            except json.JSONDecodeError:
                statuses.append(ProviderStatus(name, enabled=False, configured=False))
                continue
            statuses.append(
                ProviderStatus(
                    name,
                    enabled=bool(public.get("enabled", False)),
                    # Providers without a credential requirement are configured
                    # as soon as they are enabled.
                    configured=bool(public.get("configured", public.get("enabled", False))),
                )
            )
        return statuses


def _probe_tool(name: str, argv: Sequence[str], path_variable: str) -> ComponentStatus:
    executable = _resolve_executable(argv[0], path_variable)
    if executable is None:
        return ComponentStatus(name, Health.UNAVAILABLE, "not installed")
    try:
        completed = subprocess.run(
            [executable, *argv[1:]],
            capture_output=True,
            timeout=TOOL_PROBE_TIMEOUT_SECONDS,
            check=False,
            text=True,
        )
    except OSError, subprocess.SubprocessError:
        return ComponentStatus(name, Health.UNAVAILABLE, "did not respond")
    if completed.returncode != 0:
        return ComponentStatus(name, Health.UNAVAILABLE, "reported an error")
    first_line = completed.stdout.strip().splitlines()[:1]
    return ComponentStatus(name, Health.OK, first_line[0][:120] if first_line else None)


def _resolve_executable(command: str, path_variable: str) -> str | None:
    """Prefer the configured absolute path, then PATH.

    The image pins each tool's location explicitly. Falling back to PATH keeps
    local development working without container-specific configuration.
    """
    configured = os.environ.get(path_variable, "").strip()
    if configured:
        candidate = Path(configured)
        return str(candidate) if os.access(candidate, os.X_OK) else None
    return shutil.which(command)


def build_composition(settings: Settings, *, verify_mounts: bool = True) -> Composition:
    """Bind the real implementations for this process.

    Mounted roots are verified before an engine is created so a misconfigured
    deployment fails with a named path error rather than a database error.
    """
    if verify_mounts:
        for report in preflight_mounted_roots(settings):
            logger.info(
                "mounted root ready",
                extra={
                    "variable": report.variable,
                    "path": str(report.path),
                    "expected_identity": f"{report.expected_uid}:{report.expected_gid}",
                },
            )

    # Register secrets before anything can log them.
    redactor().register(settings.secret_key)
    redactor().register(settings.redis_url)

    engine = create_database_engine(settings.database_path)
    session_factory = create_session_factory(engine)
    settings_service = SettingsService(
        session_factory=session_factory,
        cipher=SecretCipher.from_key(settings.secret_key),
    )
    return Composition(
        settings=settings,
        engine=engine,
        session_factory=session_factory,
        registry=build_registry(
            settings,
            spotify_credentials_provider=settings_service.current_spotify_credentials,
        ),
    )


def database_path_for(settings: Settings) -> Path:
    return settings.database_path
