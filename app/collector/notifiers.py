"""Push channels for the phone-push 2FA broker.

Each is a ``Notifier`` — an async callable ``(reason, request_id) -> None`` — so
it drops straight into :class:`TwoFactorBroker`. The code is never sent through
the channel; the prompt just asks you to open the app and approve. A failing
push must never block login, so send errors are swallowed with a warning.
"""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)


async def log_notifier(reason: str, request_id: str) -> None:
    logger.info("2FA approval requested (%s): %s", request_id, reason)


class NtfyNotifier:
    """Publishes to an ntfy topic (self-hostable)."""

    def __init__(self, base_url: str, topic: str, client: httpx.AsyncClient | None = None,
                 timeout: float = 8.0) -> None:
        self._url = f"{base_url.rstrip('/')}/{topic}"
        self._client = client
        self._timeout = timeout

    async def __call__(self, reason: str, request_id: str) -> None:
        body = f"Approve XP login? {reason} (id {request_id})"
        headers = {"Title": "Market Watcher 2FA", "Priority": "high"}
        try:
            if self._client is not None:
                await self._client.post(self._url, content=body, headers=headers)
            else:
                async with httpx.AsyncClient(timeout=self._timeout) as c:
                    await c.post(self._url, content=body, headers=headers)
        except Exception as exc:
            logger.warning("ntfy 2FA push failed: %s", exc)


class TelegramNotifier:
    """Sends a message via a Telegram bot."""

    def __init__(self, bot_token: str, chat_id: str, client: httpx.AsyncClient | None = None,
                 timeout: float = 8.0) -> None:
        self._url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        self._chat_id = chat_id
        self._client = client
        self._timeout = timeout

    async def __call__(self, reason: str, request_id: str) -> None:
        payload = {
            "chat_id": self._chat_id,
            "text": f"Approve XP login? {reason} (id {request_id})",
        }
        try:
            if self._client is not None:
                await self._client.post(self._url, json=payload)
            else:
                async with httpx.AsyncClient(timeout=self._timeout) as c:
                    await c.post(self._url, json=payload)
        except Exception as exc:
            logger.warning("Telegram 2FA push failed: %s", exc)


def build_twofa_notifier(settings):
    """Select the configured 2FA push channel (defaults to log)."""
    mode = settings.twofa_notifier.lower()
    if mode == "ntfy" and settings.ntfy_topic:
        return NtfyNotifier(settings.ntfy_url, settings.ntfy_topic, timeout=settings.market_http_timeout)
    if mode == "telegram" and settings.telegram_bot_token and settings.telegram_chat_id:
        return TelegramNotifier(
            settings.telegram_bot_token, settings.telegram_chat_id,
            timeout=settings.market_http_timeout,
        )
    return log_notifier
