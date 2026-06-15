"""Tests for the collector audit log + security alerts."""

from __future__ import annotations

import asyncio
import json
import os
import stat

from app.alerts import AlertKind, security_alert
from app.collector.audit import AuditLog, NullAuditLog, build_audit_log
from app.collector.twofa import TwoFactorBroker
from app.config import Settings


def test_audit_log_appends_jsonl_with_perms(tmp_path):
    path = tmp_path / "audit.log"
    log = AuditLog(str(path))
    log.record("login", user="u1")
    log.record("fetch", offers=12)
    lines = path.read_text().strip().splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["event"] == "login" and first["user"] == "u1" and "ts" in first
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600


def test_null_audit_log_is_noop(tmp_path):
    NullAuditLog().record("x", a=1)  # must not raise or write
    assert build_audit_log(Settings(audit_log_path="")).__class__ is NullAuditLog


def test_security_alert_builder():
    alert = security_alert("login_failed", "3 failed attempts")
    assert alert.kind is AlertKind.SECURITY
    assert "login_failed" in alert.title and alert.message


def test_broker_writes_audit_trail(tmp_path):
    path = tmp_path / "audit.log"
    broker = TwoFactorBroker(
        Settings(twofa_timeout_seconds=5, audit_log_path=str(path)),
        audit=AuditLog(str(path)),
    )

    async def run() -> str:
        task = asyncio.create_task(broker.request_code("XP login"))
        for _ in range(50):
            pend = broker.pending()
            if pend:
                break
            await asyncio.sleep(0.01)
        broker.submit(pend[0]["id"], "123456")
        return await task

    assert asyncio.run(run()) == "123456"
    events = [json.loads(line)["event"] for line in path.read_text().splitlines()]
    assert "2fa_requested" in events and "2fa_approved" in events
