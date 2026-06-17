"""Order executors. Only the mock is real; the XP one is the live integration."""

from __future__ import annotations

import abc
import logging
import secrets as _secrets

from app.execution.models import OrderCredentials, OrderIntent, OrderReceipt, OrderStatus

logger = logging.getLogger(__name__)


class Executor(abc.ABC):
    name: str = "base"

    @abc.abstractmethod
    async def execute(self, intent: OrderIntent, credentials: OrderCredentials) -> OrderReceipt:
        raise NotImplementedError


class MockExecutor(Executor):
    """Simulates a fill at the intent's price. No real order is placed."""

    name = "mock"

    async def execute(self, intent: OrderIntent, credentials: OrderCredentials) -> OrderReceipt:
        # Ephemeral creds are *required* to mirror the real flow, but unused.
        if not credentials.password or not credentials.token:
            return OrderReceipt(
                order_id=intent.id,
                status=OrderStatus.REJECTED,
                asset_ref=intent.asset_ref,
                message="Missing ephemeral credentials",
            )
        return OrderReceipt(
            order_id=intent.id,
            status=OrderStatus.EXECUTED,
            asset_ref=intent.asset_ref,
            filled_quantity=intent.quantity,
            filled_price=intent.unit_price,
            total=intent.estimated_total,
            broker_ref=f"MOCK-{_secrets.token_hex(4)}",
            message="Simulated fill (MockExecutor)",
        )


class XpExecutor(Executor):
    """Live integration: drive the authenticated XP session to place the order."""

    name = "xp"

    async def execute(self, intent: OrderIntent, credentials: OrderCredentials) -> OrderReceipt:
        raise NotImplementedError(
            "XP order placement is not wired yet — drive the authenticated "
            "browser session here, then return a real OrderReceipt."
        )


def build_executor(settings) -> Executor:
    if settings.executor.lower() == "xp":
        return XpExecutor()
    return MockExecutor()
