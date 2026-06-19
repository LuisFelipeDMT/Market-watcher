"""Translate engine outputs into Alerts.

Keeps the alert wording in one place so both trackers stay thin and the two
asset classes produce consistent notifications.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.alerts.models import Alert, AlertKind, AlertSeverity

if TYPE_CHECKING:  # avoid an import cycle: builders ← trackers ← alerts
    from app.analysis.marktomarket import HoldingMark
    from app.equities.models import EquityOpportunity
    from app.models import Opportunity


def offer_alert(opp: Opportunity) -> Alert:
    """Alert for a renda fixa offer that just became an opportunity."""
    o = opp.offer
    edge = ""
    if opp.cheapness_bps and opp.cheapness_bps > 0:
        edge = f", {opp.cheapness_bps:.0f} bps cheap"
    return Alert(
        id=f"{AlertKind.NEW_OPPORTUNITY.value}:{o.id}",
        kind=AlertKind.NEW_OPPORTUNITY,
        severity=AlertSeverity.ACTIONABLE,
        title=f"New opportunity: {o.issuer} {o.product_type.value}",
        message=(
            f"Net YTM {opp.net_ytm:.2f}% ({opp.yield_pct_of_cdi:.0f}% CDI), "
            f"score {opp.opportunity_score:.0f}{edge}"
        ),
        symbol=o.id,
        score=opp.opportunity_score,
        payload={"market": o.market.value, "rating": o.rating},
    )


def security_alert(
    event: str, detail: str, severity: AlertSeverity = AlertSeverity.ACTIONABLE
) -> Alert:
    """Alert for a security/ops signal (login failure, new-device prompt, etc.)."""
    return Alert(
        id=f"SECURITY:{event}",
        kind=AlertKind.SECURITY,
        severity=severity,
        title=f"Security: {event}",
        message=detail,
        symbol=None,
    )


def sell_alert(mark: "HoldingMark") -> Alert:
    """Alert for a held paper that should be sold or exited (marcação a mercado)."""
    return Alert(
        id=f"SELL_SIGNAL:{mark.issuer}:{mark.signal}",
        kind=AlertKind.SELL_SIGNAL,
        severity=AlertSeverity.ACTIONABLE,
        title=f"{mark.signal.replace('_', ' ').title()}: {mark.issuer}",
        message=(
            f"{mark.product_type} marked {mark.unrealized_pct * 100:+.1f}% vs entry — "
            + (mark.reasons[0] if mark.reasons else "")
        ),
        symbol=mark.issuer,
        score=abs(mark.unrealized_pct) * 100,
    )


def equity_alert(opp: EquityOpportunity) -> Alert:
    """Alert for an equity that just entered the TRIGGERED (buy-now) state."""
    v = opp.valuation
    mos = f"{v.margin_of_safety * 100:.0f}%" if v.margin_of_safety is not None else "n/a"
    fair = f"R${v.fair_value_mid:.2f}" if v.fair_value_mid is not None else "n/a"
    return Alert(
        id=f"{AlertKind.EQUITY_TRIGGERED.value}:{opp.ticker}",
        kind=AlertKind.EQUITY_TRIGGERED,
        severity=AlertSeverity.ACTIONABLE,
        title=f"Buy zone: {opp.ticker} ({opp.stock.asset_kind.value})",
        message=(
            f"R${opp.stock.price:.2f} vs fair {fair} (MoS {mos}), "
            f"quality {opp.quality_score:.0f}, entry {opp.technical.entry_score:.0f}"
        ),
        symbol=opp.ticker,
        score=opp.opportunity_score,
        payload={"sector": opp.stock.sector, "state": opp.state.value},
    )
