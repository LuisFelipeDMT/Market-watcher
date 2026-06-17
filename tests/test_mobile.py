"""Tests for the mobile gateway (feed, devices, push, 2FA surface)."""

from __future__ import annotations

import asyncio

import pytest

from app.alerts import AlertKind, AlertSeverity
from app.alerts.models import Alert
from app.collector.twofa import TwoFactorBroker
from app.config import Settings
from app.equities.analysis import evaluate_universe
from app.equities.sources.fixtures import FixturesEquitySource
from app.market.fixtures import fixtures_context
from app.mobile import DeviceRegistry, build_proposals, build_push_sender
from app.mobile.models import AssetClass, DeviceRegistration
from app.mobile.push import FcmPushSender, LogPushSender, PushAlertSink, PushSender
from app.mobile.twofa_gateway import InProcessTwoFactorGateway


def _equity_ops():
    settings = Settings()
    ctx = fixtures_context(settings)
    src = FixturesEquitySource()
    snaps = asyncio.run(src.fetch_universe())
    return evaluate_universe(snaps, ctx, settings, src.sector_multiples())


def test_feed_projects_triggered_equities_and_ranks():
    proposals = build_proposals([], _equity_ops())
    assert proposals  # fixtures trigger at least one name
    assert all(p.id.startswith("eq:") for p in proposals)
    assert all(p.asset_class in (AssetClass.STOCK, AssetClass.FII) for p in proposals)
    # Ranked best-first.
    scores = [p.score for p in proposals]
    assert scores == sorted(scores, reverse=True)
    # Carries the decision context.
    assert proposals[0].metrics.get("MoS") and proposals[0].reasons


def test_device_registry_roundtrip(tmp_path):
    reg = DeviceRegistry(tmp_path / "devices.json")
    reg.register(DeviceRegistration(id="d1", token="tok-1"))
    reg.register(DeviceRegistration(id="d2", token="tok-2"))
    assert set(reg.tokens()) == {"tok-1", "tok-2"}
    # Persisted across instances.
    assert len(DeviceRegistry(tmp_path / "devices.json").list()) == 2
    assert reg.unregister("d1") is True
    assert reg.unregister("d1") is False
    assert reg.tokens() == ["tok-2"]


def test_build_push_sender_selects_backend():
    assert isinstance(build_push_sender(Settings()), LogPushSender)
    assert isinstance(build_push_sender(Settings(fcm_server_key="k")), FcmPushSender)


@pytest.mark.asyncio
async def test_push_alert_sink_fans_to_all_devices(tmp_path):
    sent: list[tuple[str, str]] = []

    class _Fake(PushSender):
        async def send(self, token, title, body, data=None):
            sent.append((token, title))

    reg = DeviceRegistry(tmp_path / "d.json")
    reg.register(DeviceRegistration(id="a", token="t1"))
    reg.register(DeviceRegistration(id="b", token="t2"))
    sink = PushAlertSink(reg, _Fake())
    await sink.send(
        Alert(
            id="EQUITY_TRIGGERED:PETR4",
            kind=AlertKind.EQUITY_TRIGGERED,
            severity=AlertSeverity.ACTIONABLE,
            title="Buy zone: PETR4",
            message="now",
        )
    )
    assert {t for t, _ in sent} == {"t1", "t2"}


@pytest.mark.asyncio
async def test_inprocess_twofa_gateway_forwards_to_broker():
    broker = TwoFactorBroker(Settings(twofa_timeout_seconds=5))
    gw = InProcessTwoFactorGateway(broker)
    task = asyncio.create_task(broker.request_code("XP login"))
    for _ in range(50):
        pend = await gw.pending()
        if pend:
            break
        await asyncio.sleep(0.01)
    assert await gw.approve(pend[0]["id"], "246810") is True
    assert await task == "246810"


def test_mobile_api_smoke(monkeypatch, tmp_path):
    monkeypatch.setenv("MARKET_SOURCE", "fixtures")
    monkeypatch.setenv("OFFER_SOURCE", "mock")
    monkeypatch.setenv("EQUITY_SOURCE", "fixtures")
    monkeypatch.setenv("EQUITY_WATCHLIST_PATH", str(tmp_path / "wl.json"))
    monkeypatch.setenv("DEVICE_REGISTRY_PATH", str(tmp_path / "devices.json"))
    monkeypatch.setenv("AUDIT_LOG_PATH", str(tmp_path / "audit.log"))
    from fastapi.testclient import TestClient

    from app.config import get_settings
    from app.main import create_app

    get_settings.cache_clear()
    try:
        with TestClient(create_app()) as client:
            proposals = client.get("/mobile/proposals").json()
            assert isinstance(proposals, list) and len(proposals) > 0
            assert {"id", "asset_class", "title", "score"} <= set(proposals[0])
            summary = client.get("/mobile/summary").json()
            assert summary["total"] == len(proposals)
            assert sum(summary["counts"].values()) == summary["total"]
            assert len(summary["top"]) <= 5
            detail = client.get(f"/mobile/proposals/{proposals[0]['id']}").json()
            assert detail["id"] == proposals[0]["id"]
            reg = client.post(
                "/mobile/devices", json={"id": "phone1", "token": "fcm-xyz"}
            )
            assert reg.status_code == 200
            assert any(d["id"] == "phone1" for d in client.get("/mobile/devices").json())
            assert client.get("/mobile/2fa/pending").json() == []
    finally:
        get_settings.cache_clear()
