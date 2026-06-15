"""Push delivery to registered phones, plus an AlertService sink.

The push transport is pluggable: a dev ``LogPushSender`` and an ``FcmPushSender``
(Firebase Cloud Messaging) for the real Android app. ``PushAlertSink`` lets the
existing alerting layer fan alerts (new opportunities, TRIGGERED equities, 2FA,
security) out to every registered device with no engine changes.
"""

from __future__ import annotations

import abc
import logging

import httpx

from app.alerts.models import Alert
from app.alerts.sinks import AlertSink
from app.mobile.devices import DeviceRegistry

logger = logging.getLogger(__name__)


class PushSender(abc.ABC):
    name: str = "base"

    @abc.abstractmethod
    async def send(self, token: str, title: str, body: str, data: dict | None = None) -> None:
        raise NotImplementedError


class LogPushSender(PushSender):
    """Dev sender: logs instead of pushing."""

    name = "log"

    async def send(self, token: str, title: str, body: str, data: dict | None = None) -> None:
        logger.info("PUSH -> %s: %s — %s", token[:8], title, body)


class FcmPushSender(PushSender):
    """Sends via Firebase Cloud Messaging (legacy server-key endpoint).

    The modern HTTP v1 API (OAuth service account) is recommended for
    production; this keeps the dependency surface minimal for the scaffold.
    """

    name = "fcm"

    def __init__(self, server_key: str, timeout: float = 8.0) -> None:
        self._key = server_key
        self._timeout = timeout

    async def send(self, token: str, title: str, body: str, data: dict | None = None) -> None:
        payload = {
            "to": token,
            "notification": {"title": title, "body": body},
            "data": data or {},
        }
        headers = {"Authorization": f"key={self._key}", "Content-Type": "application/json"}
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    "https://fcm.googleapis.com/fcm/send", json=payload, headers=headers
                )
                resp.raise_for_status()
        except Exception as exc:  # never break the caller on a push failure
            logger.warning("FCM push failed: %s", exc)


def build_push_sender(settings) -> PushSender:
    if getattr(settings, "fcm_server_key", ""):
        return FcmPushSender(settings.fcm_server_key, settings.market_http_timeout)
    return LogPushSender()


class PushAlertSink(AlertSink):
    """Delivers every alert to all registered devices."""

    name = "push"

    def __init__(self, registry: DeviceRegistry, sender: PushSender) -> None:
        self._registry = registry
        self._sender = sender

    async def send(self, alert: Alert) -> None:
        data = {"kind": alert.kind.value, "symbol": alert.symbol or ""}
        for token in self._registry.tokens():
            await self._sender.send(token, alert.title, alert.message, data)
