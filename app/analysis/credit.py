"""Credit tiering for offers, especially the non-FGC universe (CRI/CRA/deb).

Maps an offer's rating to a coarse credit tier and looks up the market credit
spread (bps over the risk-free curve) for that tier from the MarketContext.
"""

from __future__ import annotations

from app.models import InstitutionHealth, MarketContext, Offer, ProductType

_TIERS = ("AAA", "AA", "A", "BBB", "BB", "B")


def credit_tier(offer: Offer, health: InstitutionHealth) -> str:
    """Return a coarse credit tier: SOVEREIGN/AAA/AA/A/BBB/BB/B."""
    if offer.product_type is ProductType.TESOURO:
        return "SOVEREIGN"
    rating = (health.rating or offer.rating or "").upper().strip()
    if not rating:
        return "BBB"  # unknown -> cautious mid tier
    for tier in _TIERS:  # match longest prefix first (AAA before AA before A)
        if rating.startswith(tier):
            return tier
    if rating.startswith(("C", "D")):
        return "B"
    return "BBB"


def credit_spread_bps(tier: str, context: MarketContext) -> float:
    """Look up the market credit spread (bps) for a tier; 0 for sovereign."""
    return float(context.credit_spreads_bps.get(tier, 360.0))
