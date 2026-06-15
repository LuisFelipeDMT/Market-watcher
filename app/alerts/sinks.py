"""Alert sinks: where alerts are delivered.

Sinks must never raise into the tracker loop — a flaky webhook should drop the
alert with a warning, not blank the refresh cycle.
"""

from __future__ import annotations

import abc
import logging
from collections import deque

import httpx

from app.alerts.models import Alert

logger = logging.getLogger(__name__)


class AlertSink(abc.ABC):
    """A destination for alerts."""

    name: str = "base"

    @abc.abstractmethod
    async def send(self, alert: Alert) -> None:
        raise NotImplementedError


class LogSink(AlertSink):
    """Writes alerts to the application log (always on)."""

    name = "log"

    async def send(self, alert: Alert) -> None:
        logger.info("ALERT %s", alert.as_text())


class MemorySink(AlertSink):
    """Keeps the most recent alerts in a ring buffer for the /alerts API."""

    name = "memory"

    def __init__(self, capacity: int = 100) -> None:
        self._buffer: deque[Alert] = deque(maxlen=capacity)

    async def send(self, alert: Alert) -> None:
        self._buffer.appendleft(alert)

    def recent(self, limit: int = 50) -> list[Alert]:
        return list(self._buffer)[:limit]


class WebhookSink(AlertSink):
    """POSTs alerts to a generic JSON webhook (Slack/Discord/Telegram-compatible)."""

    name = "webhook"

    def __init__(self, url: str, timeout: float = 8.0) -> None:
        self._url = url
        self._timeout = timeout

    async def send(self, alert: Alert) -> None:
        # ``text`` works out of the box for Slack/Discord incoming webhooks;
        # the full structured alert is included for richer consumers.
        body = {"text": alert.as_text(), "alert": alert.model_dump(mode="json")}
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(self._url, json=body)
                resp.raise_for_status()
        except Exception as exc:  # never break the tracker on a webhook failure
            logger.warning("Webhook alert failed: %s", exc)
