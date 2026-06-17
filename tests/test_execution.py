"""Tests for the assisted-purchase machinery (mock executor + guardrails)."""

from __future__ import annotations

import asyncio

import pytest

from app.config import Settings
from app.execution import (
    IntentInvalid,
    KillSwitchEngaged,
    MockExecutor,
    OrderCredentials,
    OrderLedger,
    OrderService,
    OrderStatus,
)
from app.execution.signing import sign_intent, verify_intent


def _svc(tmp_path, **overrides) -> OrderService:
    settings = Settings(
        order_signing_key="testkey",
        order_ledger_path=str(tmp_path / "orders.jsonl"),
        **overrides,
    )
    return OrderService(settings, MockExecutor(), OrderLedger(settings.order_ledger_path))


def _creds() -> OrderCredentials:
    return OrderCredentials(password="pw", token="123456")


def test_happy_path_executes(tmp_path):
    svc = _svc(tmp_path)
    intent = svc.create_intent("rf:mock-001", quantity=10, unit_price=1000.0)
    assert intent.estimated_total == 10_000.0
    svc.confirm(intent.id)
    receipt = asyncio.run(svc.execute(intent.id, _creds()))
    assert receipt.status is OrderStatus.EXECUTED
    assert receipt.total == 10_000.0 and receipt.broker_ref
    assert len(svc.history()) == 1


def test_execute_requires_confirm(tmp_path):
    svc = _svc(tmp_path)
    intent = svc.create_intent("rf:x", 1, 100.0)
    with pytest.raises(IntentInvalid):
        asyncio.run(svc.execute(intent.id, _creds()))


def test_idempotent_no_double_buy(tmp_path):
    svc = _svc(tmp_path)
    intent = svc.create_intent("rf:x", 1, 1000.0)
    svc.confirm(intent.id)
    r1 = asyncio.run(svc.execute(intent.id, _creds()))
    r2 = asyncio.run(svc.execute(intent.id, _creds()))
    assert r1.broker_ref == r2.broker_ref  # same receipt returned
    assert len(svc.history()) == 1  # only one ledger entry


def test_per_order_limit(tmp_path):
    svc = _svc(tmp_path, order_max_per_order=5_000.0)
    intent = svc.create_intent("rf:x", 10, 1000.0)  # 10k > 5k
    svc.confirm(intent.id)
    receipt = asyncio.run(svc.execute(intent.id, _creds()))
    assert receipt.status is OrderStatus.REJECTED
    assert "per-order" in receipt.message.lower()
    assert svc.history() == []


def test_daily_limit(tmp_path):
    svc = _svc(tmp_path, order_max_daily=12_000.0)
    a = svc.create_intent("rf:a", 1, 10_000.0)
    svc.confirm(a.id)
    assert asyncio.run(svc.execute(a.id, _creds())).status is OrderStatus.EXECUTED
    b = svc.create_intent("rf:b", 1, 5_000.0)  # would push past 12k
    svc.confirm(b.id)
    rb = asyncio.run(svc.execute(b.id, _creds()))
    assert rb.status is OrderStatus.REJECTED and "daily" in rb.message.lower()


def test_kill_switch_blocks(tmp_path):
    svc = _svc(tmp_path)
    intent = svc.create_intent("rf:x", 1, 1000.0)
    svc.confirm(intent.id)
    svc.engage_kill_switch()
    with pytest.raises(KillSwitchEngaged):
        asyncio.run(svc.execute(intent.id, _creds()))
    svc.disengage_kill_switch()
    assert asyncio.run(svc.execute(intent.id, _creds())).status is OrderStatus.EXECUTED


def test_tampered_intent_rejected(tmp_path):
    svc = _svc(tmp_path)
    intent = svc.create_intent("rf:x", 1, 1000.0)
    svc.confirm(intent.id)
    intent.quantity = 999  # tamper after signing
    with pytest.raises(IntentInvalid):
        asyncio.run(svc.execute(intent.id, _creds()))


def test_missing_credentials_rejected(tmp_path):
    svc = _svc(tmp_path)
    intent = svc.create_intent("rf:x", 1, 1000.0)
    svc.confirm(intent.id)
    receipt = asyncio.run(svc.execute(intent.id, OrderCredentials(password="", token="")))
    assert receipt.status is OrderStatus.REJECTED


def test_signing_roundtrip(tmp_path):
    svc = _svc(tmp_path)
    intent = svc.create_intent("rf:x", 2, 500.0)
    assert verify_intent(intent, "testkey")
    assert not verify_intent(intent, "wrongkey")
    intent.signature = sign_intent(intent, "testkey")
    assert verify_intent(intent, "testkey")


def test_credentials_do_not_leak_in_repr():
    creds = OrderCredentials(password="supersecret", token="999999")
    assert "supersecret" not in repr(creds)
    assert "999999" not in repr(creds)


def test_orders_api_flow(monkeypatch, tmp_path):
    monkeypatch.setenv("MARKET_SOURCE", "fixtures")
    monkeypatch.setenv("OFFER_SOURCE", "mock")
    monkeypatch.setenv("EQUITY_SOURCE", "fixtures")
    monkeypatch.setenv("EQUITY_WATCHLIST_PATH", str(tmp_path / "wl.json"))
    monkeypatch.setenv("ORDER_LEDGER_PATH", str(tmp_path / "orders.jsonl"))
    monkeypatch.setenv("ORDER_SIGNING_KEY", "k")
    monkeypatch.setenv("HISTORY_PATH", str(tmp_path / "h.jsonl"))
    monkeypatch.setenv("AUDIT_LOG_PATH", str(tmp_path / "a.log"))
    from fastapi.testclient import TestClient

    from app.config import get_settings
    from app.main import create_app

    get_settings.cache_clear()
    try:
        with TestClient(create_app()) as client:
            intent = client.post(
                "/orders",
                json={"asset_ref": "rf:mock-001", "quantity": 5, "unit_price": 1000},
            ).json()
            oid = intent["id"]
            assert client.post(f"/orders/{oid}/confirm").json()["status"] == "CONFIRMED"
            receipt = client.post(
                f"/orders/{oid}/execute", json={"password": "pw", "token": "123456"}
            ).json()
            assert receipt["status"] == "EXECUTED" and receipt["total"] == 5000.0
            listing = client.get("/orders").json()
            assert len(listing["executed"]) == 1
            client.post("/orders/kill-switch", json={"engage": True})
            assert client.get("/orders").json()["kill_switch"] is True
    finally:
        get_settings.cache_clear()
