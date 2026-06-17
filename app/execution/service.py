"""Order service: create → confirm → execute, with all the guardrails.

Guardrails (independent of the executor): a signed intent, explicit confirm
step, kill switch, per-order + daily spend limits, and idempotency so a retry
never double-buys. Credentials are passed in only at execute time and discarded.
"""

from __future__ import annotations

import logging
import secrets as _secrets

from app.execution.executor import Executor
from app.execution.ledger import OrderLedger
from app.execution.models import (
    OrderCredentials,
    OrderIntent,
    OrderReceipt,
    OrderStatus,
)
from app.execution.signing import sign_intent, verify_intent

logger = logging.getLogger(__name__)


class OrderError(RuntimeError):
    pass


class KillSwitchEngaged(OrderError):
    pass


class LimitExceeded(OrderError):
    pass


class IntentInvalid(OrderError):
    pass


class OrderService:
    def __init__(self, settings, executor: Executor, ledger: OrderLedger,
                 audit=None, alerts=None) -> None:
        self._settings = settings
        self._executor = executor
        self._ledger = ledger
        self._audit = audit
        self._alerts = alerts
        self._pending: dict[str, OrderIntent] = {}
        self._killed = False

    # --- kill switch -------------------------------------------------------
    @property
    def kill_switch_engaged(self) -> bool:
        return self._killed

    def engage_kill_switch(self) -> None:
        self._killed = True
        self._record("kill_switch_engaged")

    def disengage_kill_switch(self) -> None:
        self._killed = False
        self._record("kill_switch_disengaged")

    # --- lifecycle ---------------------------------------------------------
    def create_intent(
        self, asset_ref: str, quantity: float, unit_price: float, label: str = ""
    ) -> OrderIntent:
        intent = OrderIntent(
            id=_secrets.token_urlsafe(10),
            asset_ref=asset_ref,
            label=label,
            quantity=quantity,
            unit_price=unit_price,
        )
        intent.signature = sign_intent(intent, self._settings.order_signing_key)
        self._pending[intent.id] = intent
        self._record("order_created", order_id=intent.id, total=intent.estimated_total)
        return intent

    def confirm(self, intent_id: str) -> OrderIntent:
        intent = self._pending.get(intent_id)
        if intent is None:
            raise IntentInvalid("Unknown order intent")
        if self._killed:
            raise KillSwitchEngaged("Kill switch engaged")
        intent.status = OrderStatus.CONFIRMED
        self._record("order_confirmed", order_id=intent_id)
        return intent

    async def execute(self, intent_id: str, credentials: OrderCredentials) -> OrderReceipt:
        intent = self._pending.get(intent_id)
        if intent is None:
            raise IntentInvalid("Unknown order intent")
        if self._killed:
            raise KillSwitchEngaged("Kill switch engaged")
        if not verify_intent(intent, self._settings.order_signing_key):
            raise IntentInvalid("Order intent signature invalid (tampered?)")

        # Idempotency first: a retry of an already-executed intent returns the
        # same receipt and never places a second order.
        existing = self._ledger.find_executed(intent_id)
        if existing is not None:
            return existing

        if intent.status is not OrderStatus.CONFIRMED:
            raise IntentInvalid("Order must be confirmed before execution")

        # Spend limits.
        total = intent.estimated_total
        if total > self._settings.order_max_per_order:
            return self._reject(intent, "Exceeds per-order limit")
        if self._ledger.spent_today() + total > self._settings.order_max_daily:
            return self._reject(intent, "Exceeds daily spend limit")

        receipt = await self._executor.execute(intent, credentials)
        if receipt.status is OrderStatus.EXECUTED:
            intent.status = OrderStatus.EXECUTED
            self._ledger.append(receipt)
            self._record(
                "order_executed", order_id=intent_id, total=receipt.total,
                broker_ref=receipt.broker_ref,
            )
            await self._push(f"Order executed: {intent.asset_ref}",
                             f"{receipt.filled_quantity} @ R${receipt.filled_price} "
                             f"= R${receipt.total} ({receipt.broker_ref})")
        return receipt

    def pending(self) -> list[OrderIntent]:
        return list(self._pending.values())

    def history(self) -> list[OrderReceipt]:
        return self._ledger.all()

    # --- internals ---------------------------------------------------------
    def _reject(self, intent: OrderIntent, message: str) -> OrderReceipt:
        intent.status = OrderStatus.REJECTED
        self._record("order_rejected", order_id=intent.id, reason=message)
        return OrderReceipt(
            order_id=intent.id,
            status=OrderStatus.REJECTED,
            asset_ref=intent.asset_ref,
            message=message,
        )

    def _record(self, event: str, **fields) -> None:
        if self._audit is not None:
            self._audit.record(event, **fields)

    async def _push(self, title: str, message: str) -> None:
        if self._alerts is None:
            return
        from app.alerts import security_alert

        alert = security_alert("order", message)
        alert.title = title
        await self._alerts.dispatch([alert])
