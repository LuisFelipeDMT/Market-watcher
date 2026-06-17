"""Append-only ledger of executed orders (idempotency + daily-spend limits)."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

from app.execution.models import OrderReceipt

logger = logging.getLogger(__name__)


class OrderLedger:
    """Records executed orders so retries are idempotent and spend is capped."""

    def __init__(self, path: str) -> None:
        self._path = path

    def append(self, receipt: OrderReceipt) -> None:
        try:
            os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
            fd = os.open(self._path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            with os.fdopen(fd, "a", encoding="utf-8") as fh:
                fh.write(receipt.model_dump_json() + "\n")
        except Exception as exc:
            logger.warning("Ledger write failed: %s", exc)

    def all(self) -> list[OrderReceipt]:
        if not os.path.exists(self._path):
            return []
        out: list[OrderReceipt] = []
        try:
            with open(self._path, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        out.append(OrderReceipt.model_validate_json(line))
        except Exception as exc:
            logger.warning("Ledger read failed: %s", exc)
        return out

    def find_executed(self, order_id: str) -> OrderReceipt | None:
        for r in self.all():
            if r.order_id == order_id and r.status.value == "EXECUTED":
                return r
        return None

    def spent_today(self, now: datetime | None = None) -> float:
        now = now or datetime.now(timezone.utc)
        total = 0.0
        for r in self.all():
            if r.status.value == "EXECUTED" and r.executed_at.date() == now.date():
                total += r.total
        return round(total, 2)
