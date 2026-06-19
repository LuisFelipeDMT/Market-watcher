"""Marcação a mercado on held papers → early-exit / sell signals.

For each holding with entry details we reconstruct the paper, mark it to the
*current* fair yield (risk-free curve + credit spread for its tier), and estimate
the unrealized price move via modified duration. When yields have fallen enough
that the paper has appreciated, selling on the secondary market can lock the gain
or fund a rotation; when the issuer's health turns negative, exit on credit.
"""

from __future__ import annotations

from datetime import date, timedelta

from pydantic import BaseModel, Field

from app.analysis.cheapness import reference_ytm
from app.analysis.duration import compute_duration
from app.analysis.equivalence import nominal_gross
from app.analysis.institution import get_institution_health
from app.config import Settings
from app.models import (
    Holding,
    IndexType,
    MarketContext,
    Offer,
    Portfolio,
    ProductType,
)


class HoldingMark(BaseModel):
    issuer: str
    product_type: str
    index_type: str
    entry_nominal: float  # gross nominal % at purchase
    current_nominal: float  # fair gross nominal % now
    yield_delta_bps: float  # current - entry (negative = appreciated)
    modified_duration: float
    unrealized_pct: float  # approx price move since entry
    cost_amount: float
    mark_value: float
    signal: str  # "HOLD" | "CONSIDER_SELL" | "EXIT"
    reasons: list[str] = Field(default_factory=list)


def _synthetic_offer(h: Holding) -> Offer:
    return Offer(
        id=f"hold-{h.issuer}",
        issuer=h.issuer,
        product_type=h.product_type,
        index_type=h.index_type or IndexType.PRE,
        rate=h.entry_rate or 0.0,
        maturity=h.maturity or (date.today() + timedelta(days=365)),
        min_investment=1000.0,
        fgc_eligible=h.fgc_eligible,
        rating=h.rating,
    )


def mark_holding(h: Holding, context: MarketContext, settings: Settings) -> HoldingMark | None:
    """Mark one holding to market; returns None if it lacks entry details."""
    if h.index_type is None or h.entry_rate is None or h.maturity is None:
        return None

    offer = _synthetic_offer(h)
    health = get_institution_health(h.issuer, h.rating)

    entry_nominal = nominal_gross(h.index_type, h.entry_rate, context)
    current_nominal = reference_ytm(offer, context, health)
    delta = current_nominal - entry_nominal  # percentage points
    modified = compute_duration(offer, context).modified
    unrealized = -modified * (delta / 100.0)  # +ve when yields fell (price up)

    cost = h.cost_amount if h.cost_amount is not None else h.amount
    mark_value = round(cost * (1 + unrealized), 2)

    reasons: list[str] = []
    if health.under_intervention or health.negative_news:
        signal = "EXIT"
        reasons.append("Issuer health deteriorated — exit on credit")
    elif unrealized >= settings.mtm_sell_gain_threshold:
        signal = "CONSIDER_SELL"
        reasons.append(
            f"Appreciated ~{unrealized * 100:.1f}% (yields {(-delta) * 100:.0f} bps "
            "below entry) — lock the gain or rotate"
        )
    else:
        signal = "HOLD"
        reasons.append(f"Marked {unrealized * 100:+.1f}% vs entry")

    return HoldingMark(
        issuer=h.issuer,
        product_type=h.product_type.value,
        index_type=h.index_type.value,
        entry_nominal=round(entry_nominal, 4),
        current_nominal=round(current_nominal, 4),
        yield_delta_bps=round(delta * 100, 1),
        modified_duration=modified,
        unrealized_pct=round(unrealized, 6),
        cost_amount=round(cost, 2),
        mark_value=mark_value,
        signal=signal,
        reasons=reasons,
    )


def mark_portfolio(
    portfolio: Portfolio, context: MarketContext, settings: Settings
) -> list[HoldingMark]:
    marks = [mark_holding(h, context, settings) for h in portfolio.holdings]
    return [m for m in marks if m is not None]
