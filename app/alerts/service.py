"""Alert service: fan an alert out to all configured sinks + keep history.

Both trackers already de-duplicate (they emit only *newly* flagged offers /
*newly* triggered tickers), so the service simply dispatches what it is given
and remembers it for the API. Sinks are isolated: one failing never blocks the
others or the tracker loop.
"""

from __future__ import annotations

import asyncio
import logging

from app.alerts.models import Alert
from app.alerts.sinks import AlertSink, LogSink, MemorySink, WebhookSink
from app.config import Settings

logger = logging.getLogger(__name__)


class AlertService:
    """Builds the configured sinks and dispatches alerts to all of them."""

    def __init__(self, settings: Settings) -> None:
        self._enabled = settings.alerts_enabled
        self._min_score = settings.alert_min_score
        self._memory = MemorySink(capacity=settings.alert_history_size)
        self._sinks: list[AlertSink] = [LogSink(), self._memory]
        if settings.alert_webhook_url:
            self._sinks.append(
                WebhookSink(settings.alert_webhook_url, settings.market_http_timeout)
            )

    def add_sink(self, sink: AlertSink) -> None:
        """Register an additional sink (e.g. push to phones) at startup."""
        self._sinks.append(sink)

    async def dispatch(self, alerts: list[Alert]) -> None:
        """Send each alert to every sink concurrently (best-effort)."""
        if not self._enabled or not alerts:
            return
        for alert in alerts:
            if self._min_score and (alert.score or 0) < self._min_score:
                continue
            results = await asyncio.gather(
                *(sink.send(alert) for sink in self._sinks),
                return_exceptions=True,
            )
            for sink, result in zip(self._sinks, results):
                if isinstance(result, Exception):
                    logger.warning("Sink %s failed: %s", sink.name, result)

    def recent(self, limit: int = 50) -> list[Alert]:
        return self._memory.recent(limit)

    @property
    def sink_names(self) -> list[str]:
        return [s.name for s in self._sinks]
