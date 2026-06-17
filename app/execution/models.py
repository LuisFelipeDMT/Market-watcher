"""Order models for the assisted-purchase path.

This is the **write** side, deliberately gated: an order goes DRAFT → CONFIRMED
→ EXECUTED only via explicit steps, with a signed intent, spending limits,
idempotency and a kill switch. Credentials are ephemeral and never stored.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, computed_field

from app.collector.secrets import SecretStr


class OrderStatus(str, Enum):
    DRAFT = "DRAFT"
    CONFIRMED = "CONFIRMED"
    EXECUTED = "EXECUTED"
    REJECTED = "REJECTED"
    ABORTED = "ABORTED"


class OrderIntent(BaseModel):
    """A proposed BUY, shown to the user for explicit confirmation."""

    id: str
    asset_ref: str  # offer id or ticker
    label: str = ""
    quantity: float
    unit_price: float
    status: OrderStatus = OrderStatus.DRAFT
    signature: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @computed_field  # type: ignore[prop-decorator]
    @property
    def estimated_total(self) -> float:
        return round(self.quantity * self.unit_price, 2)


class OrderReceipt(BaseModel):
    """The outcome of an execution attempt (success or refusal)."""

    order_id: str
    status: OrderStatus
    asset_ref: str
    filled_quantity: float = 0.0
    filled_price: float = 0.0
    total: float = 0.0
    broker_ref: Optional[str] = None
    message: str = ""
    executed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class OrderCredentials:
    """Ephemeral per-order credentials. Never persisted, never logged."""

    __slots__ = ("username", "password", "token")

    def __init__(self, password: str, token: str, username: str = "") -> None:
        self.username = username
        self.password = SecretStr(password)
        self.token = SecretStr(token)

    def __repr__(self) -> str:  # avoid leaking in tracebacks
        return "OrderCredentials(***)"
