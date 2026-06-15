"""Tests for the phone-push 2FA broker."""

from __future__ import annotations

import asyncio

import pytest

from app.collector.twofa import (
    TwoFactorBroker,
    TwoFactorDenied,
    TwoFactorTimeout,
)
from app.config import Settings


async def _pending_id(broker: TwoFactorBroker) -> str:
    for _ in range(50):
        pend = broker.pending()
        if pend:
            return pend[0]["id"]
        await asyncio.sleep(0.01)
    raise AssertionError("no pending request appeared")


@pytest.mark.asyncio
async def test_approve_flow_returns_code():
    calls: list[tuple[str, str]] = []

    async def notifier(reason: str, rid: str) -> None:
        calls.append((reason, rid))

    broker = TwoFactorBroker(Settings(twofa_timeout_seconds=5), notifier=notifier)
    task = asyncio.create_task(broker.request_code("XP login"))
    rid = await _pending_id(broker)
    assert broker.submit(rid, "246810") is True
    assert await task == "246810"
    assert calls and calls[0][0] == "XP login"
    # Single-use: the request is gone after consumption.
    assert broker.submit(rid, "999999") is False
    assert broker.pending() == []


@pytest.mark.asyncio
async def test_timeout_raises():
    broker = TwoFactorBroker(Settings(twofa_timeout_seconds=0.05))
    with pytest.raises(TwoFactorTimeout):
        await broker.request_code("XP login")


@pytest.mark.asyncio
async def test_deny_raises():
    broker = TwoFactorBroker(Settings(twofa_timeout_seconds=5))
    task = asyncio.create_task(broker.request_code("XP login"))
    rid = await _pending_id(broker)
    assert broker.deny(rid) is True
    with pytest.raises(TwoFactorDenied):
        await task


def test_submit_unknown_id():
    broker = TwoFactorBroker(Settings())
    assert broker.submit("nope", "123") is False
    assert broker.deny("nope") is False
