"""Tests for the collector secrets + encrypted-session layer (Phase 2)."""

from __future__ import annotations

import logging
import os
import stat

import pytest

from app.collector.secrets import (
    EnvSecretsProvider,
    MemorySecretsProvider,
    RedactionFilter,
    SecretStr,
    build_secrets_provider,
    load_broker_credentials,
    lock_memory,
)
from app.collector.session import (
    EncryptedFileSessionStore,
    NullSessionStore,
    PlaintextCipher,
    build_cipher,
    build_session_store,
)
from app.config import Settings


def test_secretstr_hides_value_but_get_returns_it():
    s = SecretStr("hunter2pass")
    assert s.get() == "hunter2pass"
    assert "hunter2pass" not in repr(s)
    assert str(s) == "***"
    assert bool(s) is True


def test_redaction_filter_scrubs_registered_secret():
    f = RedactionFilter()
    f.add("supersecretvalue")
    record = logging.LogRecord(
        "t", logging.INFO, __file__, 1,
        "logging in with %s", ("supersecretvalue",), None,
    )
    assert f.filter(record) is True
    assert "supersecretvalue" not in record.getMessage()
    assert "***" in record.getMessage()


def test_lock_memory_returns_bool_and_does_not_crash():
    assert isinstance(lock_memory(bytearray(b"secret-bytes")), bool)


def test_memory_and_env_providers():
    mem = MemorySecretsProvider({"xp_password": "abc123"})
    assert mem.get("xp_password").get() == "abc123"
    assert mem.get("missing") is None


def test_env_provider(monkeypatch):
    monkeypatch.setenv("XP_PASSWORD", "envpass99")
    assert EnvSecretsProvider().get("xp_password").get() == "envpass99"
    monkeypatch.delenv("XP_PASSWORD", raising=False)
    assert EnvSecretsProvider().get("xp_password") is None


def test_build_secrets_provider_default_and_memory():
    assert build_secrets_provider(Settings()).name == "env"
    assert build_secrets_provider(Settings(secrets_provider="memory")).name == "memory"


def test_load_credentials_from_provider():
    provider = MemorySecretsProvider({"xp_password": "sealedpass"})
    settings = Settings(xp_username="user1", xp_cpf="12345678900", xp_password="")
    creds = load_broker_credentials(settings, provider)
    assert creds.username == "user1"
    assert creds.password.get() == "sealedpass"
    assert creds.cpf == "12345678900"


def test_load_credentials_falls_back_to_plaintext_with_warning(caplog):
    provider = MemorySecretsProvider()  # no sealed secret
    settings = Settings(xp_username="user1", xp_password="legacyplain")
    with caplog.at_level(logging.WARNING):
        creds = load_broker_credentials(settings, provider)
    assert creds.password.get() == "legacyplain"
    assert any("deprecated" in r.message.lower() for r in caplog.records)


def test_load_credentials_missing_raises():
    provider = MemorySecretsProvider()
    with pytest.raises(RuntimeError):
        load_broker_credentials(Settings(xp_username="u", xp_password=""), provider)


def test_encrypted_session_store_roundtrip_and_perms(tmp_path):
    path = tmp_path / "sess.enc"
    store = EncryptedFileSessionStore(str(path), PlaintextCipher())
    assert store.load() is None
    state = {"cookies": [{"name": "a", "value": "b"}]}
    store.save(state)
    assert store.load() == state
    mode = stat.S_IMODE(os.stat(path).st_mode)
    assert mode == 0o600
    store.clear()
    assert not path.exists()


def test_build_session_store_modes():
    assert isinstance(build_session_store(Settings(session_store_path=""), None),
                      NullSessionStore)
    store = build_session_store(
        Settings(session_store_path="data/x.enc", session_cipher="none"),
        MemorySecretsProvider(),
    )
    assert isinstance(store, EncryptedFileSessionStore)


def test_build_cipher_fernet_requires_key():
    with pytest.raises(RuntimeError):
        build_cipher(Settings(session_cipher="fernet"), MemorySecretsProvider())
