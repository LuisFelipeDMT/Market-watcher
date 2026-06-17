"""Mobile gateway models: a unified proposal feed + device registration.

The phone app reads one ranked list regardless of asset class, so both the
renda fixa flagged opportunities and the equities TRIGGERED names are projected
onto a single compact :class:`Proposal` shape.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class AssetClass(str, Enum):
    RENDA_FIXA = "RENDA_FIXA"
    STOCK = "STOCK"
    FII = "FII"


class Proposal(BaseModel):
    """A single thing worth the investor's attention, app-ready."""

    id: str  # "rf:<offer-id>" or "eq:<ticker>"
    asset_class: AssetClass
    title: str
    subtitle: str
    score: float
    # Display-ready key/value metrics (already formatted strings).
    metrics: dict[str, str] = Field(default_factory=dict)
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    action: str = "Comprar no XP"  # what the user would do
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DeviceRegistration(BaseModel):
    """A registered phone for push delivery (FCM token)."""

    id: str
    token: str
    platform: str = "android"
    label: str | None = None
    registered_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class FeedSummary(BaseModel):
    """At-a-glance home/badge data for the app."""

    updated_at: datetime | None = None
    total: int = 0
    counts: dict[str, int] = Field(default_factory=dict)  # by asset class
    top: list[str] = Field(default_factory=list)  # top proposal titles
