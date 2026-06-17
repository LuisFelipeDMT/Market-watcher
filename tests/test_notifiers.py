"""Tests for the 2FA push notifier adapters (mocked HTTP)."""

from __future__ import annotations

import httpx
import pytest

from app.collector.notifiers import (
    NtfyNotifier,
    TelegramNotifier,
    build_twofa_notifier,
    log_notifier,
)
from app.config import Settings


@pytest.mark.asyncio
async def test_ntfy_posts_prompt():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = request.content.decode()
        return httpx.Response(200)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    notifier = NtfyNotifier("https://ntfy.sh", "my-topic", client=client)
    await notifier("XP login", "req-123")
    await client.aclose()
    assert seen["url"] == "https://ntfy.sh/my-topic"
    assert "XP login" in seen["body"] and "req-123" in seen["body"]


@pytest.mark.asyncio
async def test_telegram_posts_message():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        import json

        seen["json"] = json.loads(request.content.decode())
        return httpx.Response(200, json={"ok": True})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    notifier = TelegramNotifier("BOTTOKEN", "chat42", client=client)
    await notifier("XP login", "req-9")
    await client.aclose()
    assert "BOTTOKEN" in seen["url"]
    assert seen["json"]["chat_id"] == "chat42"
    assert "req-9" in seen["json"]["text"]


@pytest.mark.asyncio
async def test_notifier_swallows_errors():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    # Must not raise even though the transport fails.
    await NtfyNotifier("https://ntfy.sh", "t", client=client)("x", "y")
    await client.aclose()


def test_build_selects_channel():
    assert build_twofa_notifier(Settings()) is log_notifier
    assert isinstance(
        build_twofa_notifier(Settings(twofa_notifier="ntfy", ntfy_topic="t")),
        NtfyNotifier,
    )
    assert isinstance(
        build_twofa_notifier(
            Settings(twofa_notifier="telegram", telegram_bot_token="b", telegram_chat_id="c")
        ),
        TelegramNotifier,
    )
    # Misconfigured (missing topic) falls back to log.
    assert build_twofa_notifier(Settings(twofa_notifier="ntfy")) is log_notifier
