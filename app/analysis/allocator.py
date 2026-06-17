"""'Deploy R$X' allocator.

Spreads a budget across the best flagged opportunities while respecting the
same guardrails as sizing: FGC room per conglomerate (and the global cap) for
covered papers, and per-issuer / per-sector concentration caps for non-FGC
papers. Allocations are simulated cumulatively so one pass never over-commits a
conglomerate or sector.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.config import Settings
from app.models import NON_FGC_PRODUCTS, Opportunity, ProductType
from app.portfolio.conglomerates import conglomerate_of, sector_of
from app.portfolio.service import PortfolioService


class Allocation(BaseModel):
    offer_id: str
    issuer: str
    product_type: str
    amount: float
    reason: str


class AllocationPlan(BaseModel):
    budget: float
    allocated: float
    leftover: float
    allocations: list[Allocation] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


def allocate(
    budget: float,
    opportunities: list[Opportunity],
    service: PortfolioService,
    settings: Settings,
) -> AllocationPlan:
    """Allocate ``budget`` across flagged opportunities, best-first."""
    total_value = service.total_value() + budget
    remaining = budget

    # Running, simulated exposures (start from the current portfolio).
    cong_used = dict(service.fgc_exposure_by_conglomerate())
    global_used = service.fgc_global_used()
    issuer_used: dict[str, float] = {}
    sector_used: dict[str, float] = {}

    allocations: list[Allocation] = []
    notes: list[str] = []

    flagged = [o for o in opportunities if o.is_opportunity]
    for opp in flagged:
        if remaining <= 0:
            break
        o = opp.offer
        if o.fgc_eligible and o.product_type not in NON_FGC_PRODUCTS:
            cong = conglomerate_of(o.issuer)
            cong_room = max(settings.fgc_per_institution - cong_used.get(cong, 0.0), 0.0)
            global_room = max(settings.fgc_global_4y - global_used, 0.0)
            room = min(cong_room, global_room)
            reason = f"FGC: R${room:,.0f} room in {cong}"
        else:
            issuer_cap = settings.max_issuer_concentration * total_value
            sector_cap = settings.max_sector_concentration * total_value
            sec = sector_of(o.issuer)
            issuer_room = max(
                issuer_cap - service.issuer_exposure(o.issuer) - issuer_used.get(o.issuer, 0.0),
                0.0,
            )
            sector_room = max(
                sector_cap - service.sector_exposure(o.issuer) - sector_used.get(sec, 0.0),
                0.0,
            )
            room = min(issuer_room, sector_room)
            kind = "sovereign" if o.product_type is ProductType.TESOURO else "no-FGC"
            reason = f"{kind}: issuer R${issuer_room:,.0f} / sector R${sector_room:,.0f}"

        amount = min(room, remaining)
        if amount < o.min_investment:
            continue  # not enough room/budget to meet the minimum
        amount = round(amount, 2)

        allocations.append(
            Allocation(
                offer_id=o.id,
                issuer=o.issuer,
                product_type=o.product_type.value,
                amount=amount,
                reason=reason,
            )
        )
        remaining -= amount
        if o.fgc_eligible and o.product_type not in NON_FGC_PRODUCTS:
            cong = conglomerate_of(o.issuer)
            cong_used[cong] = cong_used.get(cong, 0.0) + amount
            global_used += amount
        else:
            issuer_used[o.issuer] = issuer_used.get(o.issuer, 0.0) + amount
            sector_used[sector_of(o.issuer)] = sector_used.get(sector_of(o.issuer), 0.0) + amount

    if not flagged:
        notes.append("No flagged opportunities to allocate into")
    if remaining > 0 and flagged:
        notes.append(f"R${remaining:,.0f} left unallocated (caps/minimums reached)")

    return AllocationPlan(
        budget=round(budget, 2),
        allocated=round(budget - remaining, 2),
        leftover=round(remaining, 2),
        allocations=allocations,
        notes=notes,
    )
