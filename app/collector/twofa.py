"""Phone-push 2FA broker (collector trusted zone).

When XP asks for a second factor, the collector creates a pending, time-boxed,
single-use request and pushes an approval prompt to the phone (the seed lives on
the phone, never here). The phone replies with the code through the collector's
authenticated `/2fa/{id}/approve` endpoint; the waiting login resumes.

The push channel is pluggable (a notifier callable) so it can ride on ntfy /
Telegram / a custom app later; the default just logs. This module has no
brokerage credentials and no dependency on the analysis zone.
"""

from __future__ import annotations

import asyncio
import logging
import secrets as _secrets
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Awaitable, Callable, Optional

logger = logging.getLogger(__name__)

# A notifier delivers the approval prompt; (reason, request_id) -> awaitable.
Notifier = Callable[[str, str], Awaitable[None]]


class TwoFactorError(RuntimeError):
    """Base class for 2FA failures."""


class TwoFactorTimeout(TwoFactorError):
    """No approval arrived before the request expired."""


class TwoFactorDenied(TwoFactorError):
    """The request was explicitly denied from the phone."""


class _Status(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    DENIED = "DENIED"


class _Pending:
    __slots__ = ("reason", "created_at", "expires_at", "status", "code", "event")

    def __init__(self, reason: str, ttl: float) -> None:
        now = datetime.now(timezone.utc)
        self.reason = reason
        self.created_at = now
        self.expires_at = now + timedelta(seconds=ttl)
        self.status = _Status.PENDING
        self.code: Optional[str] = None
        self.event = asyncio.Event()


async def _log_notifier(reason: str, request_id: str) -> None:
    logger.info("2FA approval requested (%s): %s", request_id, reason)


class TwoFactorBroker:
    """Issues approval requests and waits for the phone to relay the code."""

    def __init__(self, settings, notifier: Notifier | None = None) -> None:
        self._ttl = settings.twofa_timeout_seconds
        self._notifier = notifier or _log_notifier
        self._pending: dict[str, _Pending] = {}

    async def request_code(self, reason: str) -> str:
        """Push an approval prompt and block until the code arrives or expires."""
        request_id = _secrets.token_urlsafe(12)
        pending = _Pending(reason, self._ttl)
        self._pending[request_id] = pending
        try:
            await self._notifier(reason, request_id)
            try:
                await asyncio.wait_for(pending.event.wait(), timeout=self._ttl)
            except asyncio.TimeoutError as exc:
                raise TwoFactorTimeout(
                    f"2FA approval timed out after {self._ttl:.0f}s"
                ) from exc
            if pending.status is _Status.DENIED:
                raise TwoFactorDenied("2FA request denied from phone")
            assert pending.code is not None
            return pending.code
        finally:
            # Single-use: always drop the request when we stop waiting.
            self._pending.pop(request_id, None)

    def submit(self, request_id: str, code: str) -> bool:
        """Phone-side: provide the approval code. Returns True if accepted."""
        pending = self._pending.get(request_id)
        if pending is None or pending.status is not _Status.PENDING:
            return False
        pending.code = code
        pending.status = _Status.APPROVED
        pending.event.set()
        return True

    def deny(self, request_id: str) -> bool:
        """Phone-side: reject the login attempt."""
        pending = self._pending.get(request_id)
        if pending is None or pending.status is not _Status.PENDING:
            return False
        pending.status = _Status.DENIED
        pending.event.set()
        return True

    def pending(self) -> list[dict]:
        """List in-flight requests (no codes) for the phone to display."""
        return [
            {
                "id": rid,
                "reason": p.reason,
                "created_at": p.created_at.isoformat(),
                "expires_at": p.expires_at.isoformat(),
            }
            for rid, p in self._pending.items()
            if p.status is _Status.PENDING
        ]
