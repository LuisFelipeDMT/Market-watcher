"""Recommend how much to allocate to a candidate buy.

For FGC-covered papers: never exceed the remaining R$250k room in the issuer's
conglomerate (nor the R$1M global cap). For non-FGC papers (CRI/CRA/debentures):
spread the risk — cap exposure per issuer and per sector as a fraction of the
portfolio, so a single default can't sink you.
"""

from __future__ import annotations

from app.config import Settings
from app.models import NON_FGC_PRODUCTS, Offer, PositionSizing, ProductType
from app.portfolio.service import PortfolioService


def recommend_size(
    offer: Offer, service: PortfolioService, settings: Settings
) -> PositionSizing:
    total = service.total_value()
    notes: list[str] = []

    if offer.fgc_eligible and offer.product_type not in NON_FGC_PRODUCTS:
        room = service.fgc_room(offer.issuer)
        global_room = service.fgc_global_room()
        max_rec = min(room, global_room)
        notes.append(
            f"FGC room R${room:,.0f} in conglomerate; global room R${global_room:,.0f}"
        )
        if max_rec <= 0:
            notes.append("FGC cap already reached for this conglomerate")
        fgc_room = room
    else:
        issuer_cap = settings.max_issuer_concentration * total
        sector_cap = settings.max_sector_concentration * total
        issuer_room = max(issuer_cap - service.issuer_exposure(offer.issuer), 0.0)
        sector_room = max(sector_cap - service.sector_exposure(offer.issuer), 0.0)
        max_rec = min(issuer_room, sector_room)
        kind = "sovereign" if offer.product_type is ProductType.TESOURO else "no FGC"
        notes.append(
            f"{kind}: diversify — issuer room R${issuer_room:,.0f}, "
            f"sector room R${sector_room:,.0f}"
        )
        fgc_room = None

    if 0 < max_rec < offer.min_investment:
        notes.append(
            f"Room (R${max_rec:,.0f}) below minimum (R${offer.min_investment:,.0f})"
        )
        max_rec = 0.0

    resulting = service.issuer_exposure(offer.issuer) + max_rec
    concentration = round(resulting / total * 100.0, 2) if total else 0.0

    return PositionSizing(
        fgc_room=fgc_room,
        max_recommended=round(max_rec, 2),
        concentration_pct=concentration,
        notes=notes,
    )
