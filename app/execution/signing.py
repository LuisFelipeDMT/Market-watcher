"""Tamper-evident signing of order intents (HMAC-SHA256)."""

from __future__ import annotations

import hmac
from hashlib import sha256

from app.execution.models import OrderIntent


def _payload(intent: OrderIntent) -> bytes:
    return f"{intent.id}|{intent.asset_ref}|{intent.quantity}|{intent.unit_price}".encode()


def sign_intent(intent: OrderIntent, key: str) -> str:
    return hmac.new(key.encode(), _payload(intent), sha256).hexdigest()


def verify_intent(intent: OrderIntent, key: str) -> bool:
    if not intent.signature:
        return False
    return hmac.compare_digest(sign_intent(intent, key), intent.signature)
