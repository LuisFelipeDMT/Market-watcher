"""Encrypted session cache for the collector (Phase 2).

Persisting the authenticated XP session (cookies/storage state) lets the
collector run unattended between logins and keeps phone-push 2FA prompts rare.
Because it is account-sensitive, it is always encrypted at rest with a
pluggable cipher:

- ``fernet``  — AES via the ``cryptography`` library (key from the secrets
  provider). Recommended default on a real host.
- ``command`` — pipes through ``age``/``systemd-creds`` so the key can be
  TPM-bound and never lives in the process.
- ``none``    — dev only: stores plaintext JSON, refuses if it looks like real
  data should be protected. Never use with live credentials.
"""

from __future__ import annotations

import abc
import json
import logging
import os
import subprocess

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# Ciphers
# --------------------------------------------------------------------------


class Cipher(abc.ABC):
    name: str = "base"

    @abc.abstractmethod
    def encrypt(self, data: bytes) -> bytes:
        raise NotImplementedError

    @abc.abstractmethod
    def decrypt(self, data: bytes) -> bytes:
        raise NotImplementedError


class PlaintextCipher(Cipher):
    """No encryption — development only. Emits a warning on construction."""

    name = "none"

    def __init__(self) -> None:
        logger.warning(
            "PlaintextCipher in use: session state is NOT encrypted. "
            "Set SESSION_CIPHER=fernet|command before going live."
        )

    def encrypt(self, data: bytes) -> bytes:
        return data

    def decrypt(self, data: bytes) -> bytes:
        return data


class FernetCipher(Cipher):
    """AES (Fernet) using a key from the secrets provider."""

    name = "fernet"

    def __init__(self, key: str) -> None:
        from cryptography.fernet import Fernet  # lazy: optional dependency

        self._f = Fernet(key)

    def encrypt(self, data: bytes) -> bytes:
        return self._f.encrypt(data)

    def decrypt(self, data: bytes) -> bytes:
        return self._f.decrypt(data)


class CommandCipher(Cipher):
    """Encrypt/decrypt by piping through host tools (age/systemd-creds)."""

    name = "command"

    def __init__(self, encrypt_cmd: str, decrypt_cmd: str) -> None:
        self._enc = encrypt_cmd
        self._dec = decrypt_cmd

    def _run(self, cmd: str, data: bytes) -> bytes:
        out = subprocess.run(
            cmd, shell=True, input=data, capture_output=True, check=True
        )
        return out.stdout

    def encrypt(self, data: bytes) -> bytes:
        return self._run(self._enc, data)

    def decrypt(self, data: bytes) -> bytes:
        return self._run(self._dec, data)


def build_cipher(settings, provider) -> Cipher:
    """Construct the configured cipher for session-at-rest encryption."""
    mode = settings.session_cipher.lower()
    if mode == "fernet":
        key = provider.get("session_key")
        if key is None:
            raise RuntimeError(
                "SESSION_CIPHER=fernet requires a 'session_key' secret."
            )
        return FernetCipher(key.get())
    if mode == "command":
        return CommandCipher(
            settings.session_cipher_cmd_encrypt, settings.session_cipher_cmd_decrypt
        )
    return PlaintextCipher()


# --------------------------------------------------------------------------
# Session stores
# --------------------------------------------------------------------------


class SessionStore(abc.ABC):
    """Loads/saves the collector's authenticated session state."""

    @abc.abstractmethod
    def load(self) -> dict | None:
        raise NotImplementedError

    @abc.abstractmethod
    def save(self, state: dict) -> None:
        raise NotImplementedError

    @abc.abstractmethod
    def clear(self) -> None:
        raise NotImplementedError


class NullSessionStore(SessionStore):
    """No persistence — every start requires a fresh login."""

    def load(self) -> dict | None:
        return None

    def save(self, state: dict) -> None:
        pass

    def clear(self) -> None:
        pass


class EncryptedFileSessionStore(SessionStore):
    """Stores the session as an encrypted blob with owner-only permissions."""

    def __init__(self, path: str, cipher: Cipher) -> None:
        self._path = path
        self._cipher = cipher

    def load(self) -> dict | None:
        if not os.path.exists(self._path):
            return None
        try:
            with open(self._path, "rb") as fh:
                blob = fh.read()
            return json.loads(self._cipher.decrypt(blob).decode("utf-8"))
        except Exception as exc:
            logger.warning("Could not load session (will re-login): %s", exc)
            return None

    def save(self, state: dict) -> None:
        try:
            os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
            blob = self._cipher.encrypt(json.dumps(state).encode("utf-8"))
            # Write 0600 so only the collector's user can read the session.
            fd = os.open(self._path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "wb") as fh:
                fh.write(blob)
        except Exception as exc:
            logger.warning("Could not save session: %s", exc)

    def clear(self) -> None:
        try:
            os.remove(self._path)
        except FileNotFoundError:
            pass


def build_session_store(settings, provider) -> SessionStore:
    """Construct the configured session store (Null when no path is set)."""
    if not settings.session_store_path:
        return NullSessionStore()
    return EncryptedFileSessionStore(
        settings.session_store_path, build_cipher(settings, provider)
    )
