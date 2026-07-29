"""Proxy and provider settings use cases.

The global proxy comes first: it is validated, encrypted, masked, saved, and
tested here, and every provider reaches the internet through it. Provider rows
carry an enabled flag and, for Last.fm alone, an optional API key. The public
state a browser may see is kept strictly apart from the encrypted credential —
a masked proxy or a `configured` flag crosses the boundary; a password or key
never does.

Reads and writes happen in a short transaction so an outbound proxy test, which
may hang, never holds the shared SQLite write lock while the household plays
music.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from sqlalchemy.orm import Session, sessionmaker

from chillify.domain.errors import RecordNotFoundError, ValidationFailedError
from chillify.infrastructure.db.repositories import SettingRecord, SettingsRepository
from chillify.infrastructure.logging.setup import redactor
from chillify.infrastructure.security.outbound import OutboundHttp, ProxyDiagnosis, parse_proxy
from chillify.infrastructure.security.secrets import SecretCipher

logger = logging.getLogger(__name__)

PROXY_KEY: Final = "proxy"
INSPECTION_KEY: Final = "inspection"
SPOTIFY_API_KEY: Final = "provider.spotify_api"

# Providers whose settings row this service edits, and whether each one carries
# a credential. Only Last.fm has a key; the rest are configured as soon as they
# are enabled.
_PROVIDER_NAMES: Final = ("deezer", "spotdl", "yt_dlp", "lastfm")
_CREDENTIALLED: Final = frozenset({"lastfm"})


class ProviderDiagnosisCode(StrEnum):
    """The outcomes a provider test can report."""

    OK = "ok"
    DISABLED = "disabled"
    UNCONFIGURED = "unconfigured"


class InspectionMode(StrEnum):
    """The persisted ordering policy for Spotify inspection."""

    FAST = "fast"
    THOROUGH = "thorough"


@dataclass(frozen=True, slots=True)
class InspectionSettings:
    """Validated timeout budget read by the inspection policy for one request."""

    mode: InspectionMode
    timeout_spotify_s: int
    timeout_spotdl_s: int
    timeout_ytdlp_s: int

    @classmethod
    def create(
        cls,
        *,
        mode: InspectionMode,
        timeout_spotify_s: int,
        timeout_spotdl_s: int,
        timeout_ytdlp_s: int,
    ) -> InspectionSettings:
        _validate_timeout("timeout_spotify_s", timeout_spotify_s, minimum=1, maximum=30)
        _validate_timeout("timeout_spotdl_s", timeout_spotdl_s, minimum=30, maximum=600)
        _validate_timeout("timeout_ytdlp_s", timeout_ytdlp_s, minimum=10, maximum=300)
        return cls(
            mode=mode,
            timeout_spotify_s=timeout_spotify_s,
            timeout_spotdl_s=timeout_spotdl_s,
            timeout_ytdlp_s=timeout_ytdlp_s,
        )


@dataclass(frozen=True, slots=True)
class ProxyView:
    """The public proxy state, safe to return verbatim."""

    configured: bool
    scheme: str | None
    host: str | None
    masked_url: str | None
    revision: int


@dataclass(frozen=True, slots=True)
class ProviderView:
    """One provider's public state, safe to return verbatim."""

    name: str
    enabled: bool
    configured: bool
    requires_credential: bool
    has_credential: bool
    revision: int


@dataclass(frozen=True, slots=True)
class SpotifyApiView:
    """The only Spotify credential state safe to expose to a browser."""

    configured: bool
    revision: int


@dataclass(frozen=True, slots=True)
class InspectionView:
    """The persisted inspection settings plus their optimistic revision."""

    mode: InspectionMode
    timeout_spotify_s: int
    timeout_spotdl_s: int
    timeout_ytdlp_s: int
    revision: int


@dataclass(frozen=True, slots=True)
class SettingsView:
    """The whole settings surface `GET /settings` returns."""

    proxy: ProxyView
    providers: tuple[ProviderView, ...]
    inspection: InspectionView
    spotify_api: SpotifyApiView


@dataclass(frozen=True, slots=True)
class ProviderDiagnosis:
    """One provider-test result, safe to return verbatim."""

    ok: bool
    code: ProviderDiagnosisCode
    message: str


@dataclass(frozen=True, slots=True)
class SettingsService:
    """Read, save, and test proxy and provider settings."""

    session_factory: sessionmaker[Session]
    cipher: SecretCipher

    @contextmanager
    def _transaction(self) -> Iterator[Session]:
        session = self.session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # -- reads ------------------------------------------------------------

    def read(self) -> SettingsView:
        with self._transaction() as session:
            repository = SettingsRepository(session)
            proxy = _proxy_view(repository.get(PROXY_KEY))
            providers = tuple(
                _provider_view(name, repository.get(_provider_key(name)))
                for name in _PROVIDER_NAMES
            )
            inspection = _inspection_view(repository.get(INSPECTION_KEY))
            spotify_api = _spotify_api_view(repository.get(SPOTIFY_API_KEY))
        return SettingsView(
            proxy=proxy,
            providers=providers,
            inspection=inspection,
            spotify_api=spotify_api,
        )

    def current_proxy_url(self) -> str | None:
        """Decrypt the saved proxy for outbound use, or None when none is set.

        The decrypted URL is registered for redaction before it is returned, so
        it can never reach a log line as plaintext.
        """
        with self._transaction() as session:
            record = SettingsRepository(session).get(PROXY_KEY)
        if not record.public.get("configured") or record.secret_ciphertext is None:
            return None
        url = self.cipher.decrypt(record.secret_ciphertext)
        redactor().register(url)
        return url

    def current_inspection(self) -> InspectionSettings:
        """Return the validated settings snapshot for the next inspection."""
        with self._transaction() as session:
            return _inspection_settings(SettingsRepository(session).get(INSPECTION_KEY))

    def current_spotify_credentials(self) -> tuple[str, str] | None:
        """Decrypt Spotify credentials only at the provider boundary."""
        with self._transaction() as session:
            record = SettingsRepository(session).get(SPOTIFY_API_KEY)
        if not record.public.get("configured") or record.secret_ciphertext is None:
            return None
        client_id, client_secret = _decode_spotify_credentials(
            self.cipher.decrypt(record.secret_ciphertext)
        )
        redactor().register(client_id)
        redactor().register(client_secret)
        return client_id, client_secret

    def current_lastfm_api_key(self) -> str | None:
        """Decrypt the enabled Last.fm key only at the enrichment boundary."""
        with self._transaction() as session:
            record = SettingsRepository(session).get(_provider_key("lastfm"))
        if (
            not record.public.get("enabled")
            or not record.public.get("configured")
            or record.secret_ciphertext is None
        ):
            return None
        api_key = self.cipher.decrypt(record.secret_ciphertext)
        redactor().register(api_key)
        return api_key

    # -- proxy ------------------------------------------------------------

    def save_proxy(self, url: str | None, *, revision: int, clear: bool = False) -> ProxyView:
        """Validate and persist the proxy, or remove it.

        A malformed URL or unsupported scheme is refused before anything is
        stored: `parse_proxy` raises the typed configuration error, and no row
        is touched. A cleared proxy drops both the ciphertext and the masked
        public form.
        """
        if clear or url is None or not url.strip():
            public: dict[str, object] = {"configured": False}
            secret: bytes | None = None
        else:
            endpoint = parse_proxy(url)
            public = {
                "configured": True,
                "scheme": endpoint.scheme,
                "host": endpoint.host,
                "masked_url": endpoint.masked_url,
            }
            secret = self.cipher.encrypt(endpoint.raw)
            redactor().register(endpoint.raw)
        with self._transaction() as session:
            record = SettingsRepository(session).update(
                PROXY_KEY,
                expected_revision=revision,
                public=public,
                secret_ciphertext=secret,
            )
        logger.info("proxy setting saved", extra={"configured": public["configured"]})
        return _proxy_view(record)

    def test_proxy(self, url: str | None = None) -> ProxyDiagnosis:
        """Test a supplied proxy, or the saved one, always through the proxy.

        A supplied URL is tested as-is so the operator can verify a change
        before saving it; otherwise the saved proxy is decrypted and tested.
        Either way the request goes through the proxy — there is no direct probe.
        """
        target = url.strip() if url and url.strip() else self.current_proxy_url()
        return OutboundHttp(proxy=target).probe(target)

    # -- inspection -------------------------------------------------------

    def save_inspection(
        self,
        *,
        mode: InspectionMode,
        timeout_spotify_s: int,
        timeout_spotdl_s: int,
        timeout_ytdlp_s: int,
        revision: int,
    ) -> InspectionView:
        """Persist the timeout budget used by future inspection requests."""
        inspection = InspectionSettings.create(
            mode=mode,
            timeout_spotify_s=timeout_spotify_s,
            timeout_spotdl_s=timeout_spotdl_s,
            timeout_ytdlp_s=timeout_ytdlp_s,
        )
        with self._transaction() as session:
            record = SettingsRepository(session).update(
                INSPECTION_KEY,
                expected_revision=revision,
                public=_inspection_public(inspection),
                secret_ciphertext=None,
            )
        logger.info("inspection settings saved", extra={"mode": inspection.mode})
        return _inspection_view(record)

    def save_spotify_credentials(
        self,
        *,
        client_id: str | None,
        client_secret: str | None,
        clear_secret: bool,
        revision: int,
    ) -> SpotifyApiView:
        """Save, retain, or remove the encrypted Spotify client credentials."""
        with self._transaction() as session:
            repository = SettingsRepository(session)
            existing = repository.get(SPOTIFY_API_KEY)
            secret: bytes | None
            if clear_secret:
                secret = None
                public: dict[str, object] = {"configured": False}
            else:
                current = _decrypt_spotify_credentials(self.cipher, existing)
                next_client_id = _new_credential_value(client_id, current, index=0)
                next_client_secret = _new_credential_value(client_secret, current, index=1)
                if next_client_id is None and next_client_secret is None:
                    secret = None
                    public = {"configured": False}
                elif next_client_id is None:
                    raise ValidationFailedError(
                        "Spotify client ID is required when configuring Spotify credentials.",
                        field="client_id",
                    )
                elif next_client_secret is None:
                    raise ValidationFailedError(
                        "Spotify client secret is required when configuring Spotify credentials.",
                        field="client_secret",
                    )
                else:
                    redactor().register(next_client_id)
                    redactor().register(next_client_secret)
                    secret = self.cipher.encrypt(
                        json.dumps(
                            {"client_id": next_client_id, "client_secret": next_client_secret},
                            separators=(",", ":"),
                            sort_keys=True,
                        )
                    )
                    public = {"configured": True}
            record = repository.update(
                SPOTIFY_API_KEY,
                expected_revision=revision,
                public=public,
                secret_ciphertext=secret,
            )
        logger.info("Spotify API credentials saved", extra={"configured": record.has_secret})
        return _spotify_api_view(record)

    # -- providers --------------------------------------------------------

    def save_provider(
        self,
        name: str,
        *,
        revision: int,
        enabled: bool | None = None,
        credential: str | None = None,
        clear_secret: bool = False,
    ) -> ProviderView:
        """Toggle a provider and, for Last.fm, set or clear its API key.

        A credential submitted for a keyless provider is a request error rather
        than a silently ignored field: it means the caller misunderstood the
        provider, and dropping it quietly would hide that.
        """
        if name not in _PROVIDER_NAMES:
            raise RecordNotFoundError("That provider does not exist.", context={"provider": name})
        requires_credential = name in _CREDENTIALLED
        with self._transaction() as session:
            repository = SettingsRepository(session)
            existing = repository.get(_provider_key(name))
            public = dict(existing.public)
            secret = existing.secret_ciphertext

            if enabled is not None:
                public["enabled"] = enabled

            if requires_credential:
                if clear_secret:
                    secret = None
                elif credential is not None and credential.strip():
                    secret = self.cipher.encrypt(credential.strip())
                    redactor().register(credential.strip())
                public["configured"] = secret is not None
            else:
                if clear_secret or (credential is not None and credential.strip()):
                    raise ValidationFailedError(
                        "This provider does not take a credential.", field="credential"
                    )
                public["configured"] = bool(public.get("enabled", False))

            record = repository.update(
                _provider_key(name),
                expected_revision=revision,
                public=public,
                secret_ciphertext=secret,
            )
        logger.info(
            "provider setting saved",
            extra={"provider": name, "enabled": bool(public.get("enabled", False))},
        )
        return _provider_view(name, record)

    def test_provider(self, name: str) -> ProviderDiagnosis:
        """Report whether a provider is ready, isolated to that provider.

        A disabled provider or an unconfigured Last.fm is that provider's own
        state, not a global fault: the message names the next action and never
        marks the deployment unhealthy.
        """
        if name not in _PROVIDER_NAMES:
            raise RecordNotFoundError("That provider does not exist.", context={"provider": name})
        view = _provider_view(name, self._read_provider(name))
        if not view.enabled:
            return ProviderDiagnosis(
                ok=False,
                code=ProviderDiagnosisCode.DISABLED,
                message="This provider is switched off. Enable it to use it.",
            )
        if view.requires_credential and not view.has_credential:
            return ProviderDiagnosis(
                ok=False,
                code=ProviderDiagnosisCode.UNCONFIGURED,
                message="Add an API key to enable optional Last.fm enrichment.",
            )
        return ProviderDiagnosis(
            ok=True,
            code=ProviderDiagnosisCode.OK,
            message="This provider is enabled and configured.",
        )

    def _read_provider(self, name: str) -> SettingRecord:
        with self._transaction() as session:
            return SettingsRepository(session).get(_provider_key(name))


def _provider_key(name: str) -> str:
    return f"provider.{name}"


def _proxy_view(record: SettingRecord) -> ProxyView:
    public = record.public
    return ProxyView(
        configured=bool(public.get("configured", False)),
        scheme=_optional_str(public.get("scheme")),
        host=_optional_str(public.get("host")),
        masked_url=_optional_str(public.get("masked_url")),
        revision=record.revision,
    )


def _provider_view(name: str, record: SettingRecord) -> ProviderView:
    public = record.public
    enabled = bool(public.get("enabled", False))
    requires_credential = name in _CREDENTIALLED
    return ProviderView(
        name=name,
        enabled=enabled,
        configured=bool(public.get("configured", enabled)),
        requires_credential=requires_credential,
        has_credential=record.has_secret,
        revision=record.revision,
    )


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _validate_timeout(name: str, value: int, *, minimum: int, maximum: int) -> None:
    if not minimum <= value <= maximum:
        raise ValidationFailedError(
            f"{name} must be between {minimum} and {maximum} seconds.", field=name
        )


def _inspection_public(inspection: InspectionSettings) -> dict[str, object]:
    return {
        "mode": inspection.mode.value,
        "timeout_spotify_s": inspection.timeout_spotify_s,
        "timeout_spotdl_s": inspection.timeout_spotdl_s,
        "timeout_ytdlp_s": inspection.timeout_ytdlp_s,
    }


def _inspection_view(record: SettingRecord) -> InspectionView:
    inspection = _inspection_settings(record)
    return InspectionView(
        mode=inspection.mode,
        timeout_spotify_s=inspection.timeout_spotify_s,
        timeout_spotdl_s=inspection.timeout_spotdl_s,
        timeout_ytdlp_s=inspection.timeout_ytdlp_s,
        revision=record.revision,
    )


def _inspection_settings(record: SettingRecord) -> InspectionSettings:
    public = record.public
    mode_value = public.get("mode")
    if not isinstance(mode_value, str):
        raise ValidationFailedError("The saved inspection mode is invalid.")
    try:
        mode = InspectionMode(mode_value)
    except ValueError as exc:
        raise ValidationFailedError("The saved inspection mode is invalid.") from exc
    timeout_spotify_s = _read_timeout(public, "timeout_spotify_s", minimum=1, maximum=30)
    timeout_spotdl_s = _read_timeout(public, "timeout_spotdl_s", minimum=30, maximum=600)
    timeout_ytdlp_s = _read_timeout(public, "timeout_ytdlp_s", minimum=10, maximum=300)
    return InspectionSettings.create(
        mode=mode,
        timeout_spotify_s=timeout_spotify_s,
        timeout_spotdl_s=timeout_spotdl_s,
        timeout_ytdlp_s=timeout_ytdlp_s,
    )


def _read_timeout(public: dict[str, object], name: str, *, minimum: int, maximum: int) -> int:
    value = public.get(name)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValidationFailedError(f"The saved {name} is invalid.")
    _validate_timeout(name, value, minimum=minimum, maximum=maximum)
    return value


def _spotify_api_view(record: SettingRecord) -> SpotifyApiView:
    return SpotifyApiView(configured=record.has_secret, revision=record.revision)


def _decode_spotify_credentials(plaintext: str) -> tuple[str, str]:
    try:
        payload = json.loads(plaintext)
    except json.JSONDecodeError as exc:
        raise ValidationFailedError("The saved Spotify credentials are invalid.") from exc
    if not isinstance(payload, dict):
        raise ValidationFailedError("The saved Spotify credentials are invalid.")
    client_id = payload.get("client_id")
    client_secret = payload.get("client_secret")
    if (
        not isinstance(client_id, str)
        or not client_id
        or not isinstance(client_secret, str)
        or not client_secret
    ):
        raise ValidationFailedError("The saved Spotify credentials are invalid.")
    return client_id, client_secret


def _decrypt_spotify_credentials(
    cipher: SecretCipher, record: SettingRecord
) -> tuple[str | None, str | None]:
    if record.secret_ciphertext is None:
        return None, None
    return _decode_spotify_credentials(cipher.decrypt(record.secret_ciphertext))


def _new_credential_value(
    submitted: str | None, current: tuple[str | None, str | None], *, index: int
) -> str | None:
    if submitted is None or not submitted.strip():
        return current[index]
    return submitted.strip()
