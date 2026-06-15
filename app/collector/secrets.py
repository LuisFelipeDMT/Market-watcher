"""Secrets handling for the trusted collector zone (Phase 2).

Goals:
- Keep the **password** out of the repo and out of logs; the TOTP seed never
  lives here at all (it stays on the phone — see the secure-delivery plan).
- Make the backend **pluggable**: a dev/self-host path (env vars) and a
  test path (in-memory), plus a host-grade path that decrypts a sealed blob via
  an external tool (``systemd-creds``/``age``) so the key can be TPM-bound.
- Best-effort memory hygiene: wrap secrets so they don't render in logs/reprs,
  ``mlock`` the buffer where possible, and scrub on release.

Perfect zeroization is impossible for Python ``str`` (immutable, copied,
possibly interned); these are defence-in-depth, not guarantees.
"""

from __future__ import annotations

import abc
import logging
import os
import subprocess
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# SecretStr: a value that refuses to print itself
# --------------------------------------------------------------------------


class SecretStr:
    """A string wrapper that never reveals itself in ``repr``/``str``/logs."""

    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        self._value = value

    def get(self) -> str:
        """Return the underlying secret. Call only at the point of use."""
        return self._value

    def __bool__(self) -> bool:
        return bool(self._value)

    def __len__(self) -> int:
        return len(self._value)

    def __repr__(self) -> str:
        return "SecretStr(***)"

    def __str__(self) -> str:
        return "***"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, SecretStr) and other._value == self._value

    def __hash__(self) -> int:  # so it can live in sets/dicts if needed
        return hash(("SecretStr", self._value))


def lock_memory(buf: bytearray) -> bool:
    """Best-effort ``mlock`` of a mutable buffer; returns success.

    Prevents the secret bytes from being swapped to disk. Silently returns
    ``False`` without privileges or on unsupported platforms.
    """
    try:
        import ctypes
        import ctypes.util

        libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
        addr = (ctypes.c_char * len(buf)).from_buffer(buf)
        return libc.mlock(addr, len(buf)) == 0
    except Exception:  # pragma: no cover - platform dependent
        return False


# --------------------------------------------------------------------------
# Log redaction
# --------------------------------------------------------------------------


class RedactionFilter(logging.Filter):
    """Replaces registered secret substrings with ``***`` in every log record."""

    def __init__(self) -> None:
        super().__init__()
        self._secrets: set[str] = set()

    def add(self, value: str) -> None:
        # Ignore very short values to avoid mangling unrelated text.
        if value and len(value) >= 4:
            self._secrets.add(value)

    def filter(self, record: logging.LogRecord) -> bool:
        if not self._secrets:
            return True
        try:
            msg = record.getMessage()
            redacted = msg
            for secret in self._secrets:
                if secret in redacted:
                    redacted = redacted.replace(secret, "***")
            if redacted != msg:
                record.msg = redacted
                record.args = ()
        except Exception:  # never let logging break the app
            pass
        return True


_REDACTION = RedactionFilter()
_INSTALLED = False


def redact(value: str) -> None:
    """Register a value to be scrubbed from all logs."""
    _REDACTION.add(value)
    install_redaction()


def install_redaction() -> None:
    """Attach the redaction filter to the root logger (idempotent)."""
    global _INSTALLED
    if _INSTALLED:
        return
    logging.getLogger().addFilter(_REDACTION)
    # Also attach to existing handlers so already-configured logs are covered.
    for handler in logging.getLogger().handlers:
        handler.addFilter(_REDACTION)
    _INSTALLED = True


# --------------------------------------------------------------------------
# Secrets providers
# --------------------------------------------------------------------------


class SecretsProvider(abc.ABC):
    """Source of named secrets for the collector."""

    name: str = "base"

    @abc.abstractmethod
    def get(self, key: str) -> SecretStr | None:
        raise NotImplementedError


class MemorySecretsProvider(SecretsProvider):
    """In-memory secrets, for tests and explicit injection."""

    name = "memory"

    def __init__(self, secrets: dict[str, str] | None = None) -> None:
        self._secrets = dict(secrets or {})

    def set(self, key: str, value: str) -> None:
        self._secrets[key] = value

    def get(self, key: str) -> SecretStr | None:
        value = self._secrets.get(key)
        return SecretStr(value) if value is not None else None


class EnvSecretsProvider(SecretsProvider):
    """Reads secrets from environment variables (dev / simple self-host).

    ``xp_password`` → ``XP_PASSWORD``. Convenient but the secret is plaintext in
    the process environment; prefer the command provider on a real host.
    """

    name = "env"

    def get(self, key: str) -> SecretStr | None:
        value = os.environ.get(key.upper())
        return SecretStr(value) if value else None


class CommandSecretsProvider(SecretsProvider):
    """Decrypts a sealed secret via an external command (host-grade).

    The command template is host-specific and can bind the key to the TPM, e.g.
        systemd-creds decrypt --name={key} {dir}/{key}.cred -
        age -d -i /root/.age/key {dir}/{key}.age
    The decrypted value is read from the command's stdout and never written to
    disk by this process.
    """

    name = "command"

    def __init__(self, template: str, sealed_dir: str) -> None:
        self._template = template
        self._dir = sealed_dir

    def get(self, key: str) -> SecretStr | None:
        if not self._template:
            return None
        cmd = self._template.format(key=key, dir=self._dir)
        try:
            out = subprocess.run(
                cmd, shell=True, capture_output=True, check=True, text=True
            )
        except Exception as exc:  # pragma: no cover - host dependent
            logger.warning("Secret decrypt failed for %s: %s", key, exc)
            return None
        value = out.stdout.strip("\n")
        return SecretStr(value) if value else None


def build_secrets_provider(settings) -> SecretsProvider:
    """Construct the configured secrets provider (defaults to env)."""
    mode = settings.secrets_provider.lower()
    if mode == "memory":
        return MemorySecretsProvider()
    if mode == "command":
        return CommandSecretsProvider(
            settings.secrets_decrypt_cmd, settings.secrets_sealed_dir
        )
    return EnvSecretsProvider()


# --------------------------------------------------------------------------
# Broker credentials
# --------------------------------------------------------------------------


@dataclass
class BrokerCredentials:
    """The (read-only) login material the collector needs. Password is sealed."""

    username: str
    password: SecretStr
    cpf: str | None = None


def load_broker_credentials(settings, provider: SecretsProvider) -> BrokerCredentials:
    """Assemble credentials, sourcing the password from the secrets provider.

    Falls back to ``settings.xp_password`` only with a loud deprecation warning,
    so existing dev setups keep working while the sealed path is adopted.
    """
    username = settings.xp_username
    cpf = settings.xp_cpf or None

    password = provider.get("xp_password")
    if password is None and settings.xp_password:
        logger.warning(
            "Using plaintext XP_PASSWORD from settings — deprecated. Move it to "
            "the secrets provider (SECRETS_PROVIDER=command) for production."
        )
        password = SecretStr(settings.xp_password)

    if not username or password is None or not password:
        raise RuntimeError(
            "Missing XP credentials: set XP_USERNAME and provide xp_password via "
            "the secrets provider (or XP_PASSWORD for dev)."
        )

    # Scrub the secret (and CPF) from any future log line.
    redact(password.get())
    if cpf:
        redact(cpf)
    return BrokerCredentials(username=username, password=password, cpf=cpf)
