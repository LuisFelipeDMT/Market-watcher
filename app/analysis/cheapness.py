"""Secondary-market cheapness: is an offer priced above its fair yield?

The user's edge is buying papers another investor is dumping under urgency (or
that depreciated via marcação a mercado) at a yield above what the paper is
worth for its risk and duration. We build a fair *reference* nominal YTM from
the risk-free curve plus the credit spread for the issuer's tier, and compare
it to the offered yield. A positive ``cheapness`` (in bps) means the buyer is
being paid more than fair — the paper is cheap.
"""

from __future__ import annotations

from app.analysis.credit import credit_spread_bps, credit_tier
from app.analysis.yields import gross_annual_yield
from app.models import InstitutionHealth, MarketContext, Offer


def interpolate_curve(curve: dict[str, float], years: float) -> float:
    """Linearly interpolate an annual rate from a {years: rate} curve."""
    if not curve:
        return 0.0
    points = sorted((float(k), v) for k, v in curve.items())
    if years <= points[0][0]:
        return points[0][1]
    if years >= points[-1][0]:
        return points[-1][1]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x0 <= years <= x1:
            w = (years - x0) / (x1 - x0) if x1 != x0 else 0.0
            return y0 + w * (y1 - y0)
    return points[-1][1]


def reference_ytm(
    offer: Offer, context: MarketContext, health: InstitutionHealth
) -> float:
    """Fair nominal annual YTM (%) for the offer's risk and duration."""
    rf = interpolate_curve(context.risk_free_curve, offer.years_to_maturity)
    tier = credit_tier(offer, health)
    spread_pct = credit_spread_bps(tier, context) / 100.0
    return round(rf + spread_pct, 4)


def cheapness_bps(
    offer: Offer, context: MarketContext, health: InstitutionHealth
) -> float:
    """Offered nominal YTM minus fair reference YTM, in basis points.

    Positive => cheap (offered above fair). Computed for all offers but most
    meaningful for SECONDARY ones.
    """
    offered = gross_annual_yield(offer, context)
    reference = reference_ytm(offer, context, health)
    return round((offered - reference) * 100.0, 1)
