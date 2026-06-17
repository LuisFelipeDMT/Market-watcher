"""Append-only time-series store (JSON lines).

Small and dependency-free: each refresh appends metric points; queries read the
file and filter. Good enough for a single-user watcher and makes "cheaper than
its 30-day norm" and lightweight backtests possible without a database.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class MetricPoint(BaseModel):
    """One observation: e.g. metric="bond.net_ytm", key="mock-sec-000"."""

    ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metric: str
    key: str
    value: float


class HistoryStore:
    """Appends and queries metric points in a JSONL file."""

    def __init__(self, path: str) -> None:
        self._path = path

    def record_many(self, points: list[MetricPoint]) -> None:
        if not points:
            return
        try:
            os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
            with open(self._path, "a", encoding="utf-8") as fh:
                for p in points:
                    fh.write(p.model_dump_json() + "\n")
        except Exception as exc:  # history must never break the tracker
            logger.warning("History write failed: %s", exc)

    def query(
        self, metric: str, key: str | None = None, since: datetime | None = None
    ) -> list[MetricPoint]:
        if not os.path.exists(self._path):
            return []
        out: list[MetricPoint] = []
        try:
            with open(self._path, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    p = MetricPoint.model_validate_json(line)
                    if p.metric != metric:
                        continue
                    if key is not None and p.key != key:
                        continue
                    if since is not None and p.ts < since:
                        continue
                    out.append(p)
        except Exception as exc:
            logger.warning("History read failed: %s", exc)
        return out


class NullHistoryStore(HistoryStore):
    """No-op store (history disabled)."""

    def __init__(self) -> None:
        super().__init__("")

    def record_many(self, points: list[MetricPoint]) -> None:
        pass

    def query(self, metric, key=None, since=None):  # type: ignore[override]
        return []


def build_history_store(settings) -> HistoryStore:
    path = getattr(settings, "history_path", "")
    return HistoryStore(path) if path else NullHistoryStore()
