"""Tests for the optional dashboard bearer auth (Phase 7)."""

from __future__ import annotations


def _client(monkeypatch, tmp_path, token: str | None):
    monkeypatch.setenv("MARKET_SOURCE", "fixtures")
    monkeypatch.setenv("OFFER_SOURCE", "mock")
    monkeypatch.setenv("EQUITY_SOURCE", "fixtures")
    monkeypatch.setenv("EQUITY_WATCHLIST_PATH", str(tmp_path / "wl.json"))
    monkeypatch.setenv("AUDIT_LOG_PATH", str(tmp_path / "audit.log"))
    if token is not None:
        monkeypatch.setenv("DASHBOARD_TOKEN", token)
    from fastapi.testclient import TestClient

    from app.config import get_settings
    from app.main import create_app

    get_settings.cache_clear()
    return TestClient(create_app())


def test_open_when_no_token(monkeypatch, tmp_path):
    from app.config import get_settings

    client = _client(monkeypatch, tmp_path, token=None)
    try:
        with client:
            assert client.get("/opportunities").status_code == 200
    finally:
        get_settings.cache_clear()


def test_requires_token_when_set(monkeypatch, tmp_path):
    from app.config import get_settings

    client = _client(monkeypatch, tmp_path, token="s3cret")
    try:
        with client:
            # Health stays open for liveness probes.
            assert client.get("/health").status_code == 200
            # Protected route needs the token.
            assert client.get("/opportunities").status_code == 401
            ok = client.get(
                "/opportunities", headers={"Authorization": "Bearer s3cret"}
            )
            assert ok.status_code == 200
            assert client.get("/equities/triggered").status_code == 401
    finally:
        get_settings.cache_clear()
