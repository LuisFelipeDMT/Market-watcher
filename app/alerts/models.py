"""Alert domain models shared by both the bond and equity engines."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class AlertKind(str, Enum):
    """What produced the alert."""

    NEW_OPPORTUNITY = "NEW_OPPORTUNITY"  # renda fixa: a new flagged offer
    EQUITY_TRIGGERED = "EQUITY_TRIGGERED"  # renda variável: a name entered the buy zone
    SECURITY = "SECURITY"  # security/ops signal (login failure, new device, etc.)


class AlertSeverity(str, Enum):
    INFO = "INFO"
    ACTIONABLE = "ACTIONABLE"  # "you may want to act now"


class Alert(BaseModel):
    """A single notification about something worth the investor's attention."""

    id: str  # stable key (kind + symbol) used for de-duplication
    kind: AlertKind
    severity: AlertSeverity = AlertSeverity.ACTIONABLE
    title: str
    message: str
    symbol: Optional[str] = None  # ticker / offer id
    score: Optional[float] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    payload: dict = Field(default_factory=dict)

    def as_text(self) -> str:
        """A compact single-line form for chat webhooks (Slack/Discord)."""
        return f"[{self.severity.value}] {self.title} — {self.message}"
