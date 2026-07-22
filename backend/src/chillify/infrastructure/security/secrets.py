"""Encryption at rest for stored settings secrets.

The optional proxy credential and the Last.fm API key are the only secrets the
application persists. They are encrypted with Fernet before they reach SQLite
and decrypted only in memory at the moment of use. The key itself lives solely
in the process environment (`CHILLIFY_SECRET_KEY`); it never enters the
database, an image layer, a Compose file, or a log line.

A decrypt failure means the running key cannot open a value a previous key
sealed — configuration corruption, not ordinary input. It is raised as a named
error rather than returned as an empty string, so a wrong key fails loudly
instead of silently discarding a saved credential.
"""

from __future__ import annotations

from dataclasses import dataclass

from cryptography.fernet import Fernet, InvalidToken


class SecretDecryptionError(Exception):
    """A stored ciphertext could not be decrypted with the current key.

    The message carries no key material and no ciphertext: the only actionable
    fact is that the deployment's `CHILLIFY_SECRET_KEY` does not match the one
    that encrypted the stored settings.
    """


@dataclass(frozen=True, slots=True)
class SecretCipher:
    """Fernet encryption bound to one deployment key.

    Constructed from the already-validated `CHILLIFY_SECRET_KEY`, so the key is
    never re-parsed here; `config` has proven it is a usable Fernet key before
    any composition is built.
    """

    _fernet: Fernet

    @classmethod
    def from_key(cls, key: str) -> SecretCipher:
        return cls(Fernet(key.encode("ascii")))

    def encrypt(self, plaintext: str) -> bytes:
        """Seal one secret. The returned bytes are what SQLite stores."""
        return self._fernet.encrypt(plaintext.encode("utf-8"))

    def decrypt(self, token: bytes) -> str:
        """Open one stored secret, or fail with a named, credential-free error."""
        try:
            return self._fernet.decrypt(token).decode("utf-8")
        except (InvalidToken, ValueError) as exc:
            raise SecretDecryptionError(
                "A stored setting could not be decrypted with the current CHILLIFY_SECRET_KEY."
            ) from exc
