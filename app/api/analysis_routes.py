"""Allocator + macro-view endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from app.analysis.allocator import AllocationPlan, allocate
from app.analysis.copom import MacroView, macro_view
from app.analysis.equivalence import IndexEquivalence, equivalents, offer_equivalence
from app.analysis.yields import net_ytm
from app.models import IndexType

router = APIRouter(tags=["analysis"])


class CompareRow(BaseModel):
    offer_id: str
    issuer: str
    product_type: str
    index_type: str
    input_rate: float
    nominal_annual: float
    as_cdi_pct: float
    as_ipca_spread: float
    as_selic_spread: float
    net_ytm: float
    tax_exempt: bool


@router.get("/allocator", response_model=AllocationPlan)
async def allocator(
    request: Request,
    budget: float = Query(..., gt=0, description="BRL to deploy"),
) -> AllocationPlan:
    """Spread a budget across flagged opportunities under FGC/diversification caps."""
    tracker = request.app.state.tracker
    return allocate(
        budget,
        tracker.state.opportunities,
        tracker.portfolio_service,
        request.app.state.settings,
    )


@router.get("/macro/view", response_model=MacroView)
async def macro(request: Request) -> MacroView:
    """Copom-aware rate direction + duration posture."""
    ctx = request.app.state.tracker.market_context
    if ctx is None:
        raise HTTPException(status_code=503, detail="Market context not ready")
    return macro_view(ctx)


@router.get("/equivalence", response_model=IndexEquivalence)
async def equivalence(
    request: Request,
    index: IndexType = Query(..., description="PRE | CDI | IPCA | SELIC"),
    rate: float = Query(..., description="Quote in that index's convention"),
    expected_ipca: bool = Query(False, description="Use forward (Focus) IPCA"),
) -> IndexEquivalence:
    """Convert one quote into its equivalent rate on every other index."""
    ctx = request.app.state.tracker.market_context
    if ctx is None:
        raise HTTPException(status_code=503, detail="Market context not ready")
    return equivalents(index, rate, ctx, expected_ipca)


@router.get("/compare", response_model=list[CompareRow])
async def compare(
    request: Request,
    index: IndexType | None = Query(None, description="Filter by index"),
    expected_ipca: bool = Query(False, description="Use forward (Focus) IPCA"),
) -> list[CompareRow]:
    """Every current offer normalized to a common basis, ranked by nominal yield."""
    tracker = request.app.state.tracker
    ctx = tracker.market_context
    if ctx is None:
        raise HTTPException(status_code=503, detail="Market context not ready")
    rows: list[CompareRow] = []
    for opp in tracker.state.opportunities:
        o = opp.offer
        if index is not None and o.index_type is not index:
            continue
        eq = offer_equivalence(o, ctx, expected_ipca)
        rows.append(
            CompareRow(
                offer_id=o.id,
                issuer=o.issuer,
                product_type=o.product_type.value,
                index_type=o.index_type.value,
                input_rate=o.effective_rate,
                nominal_annual=eq.nominal_annual,
                as_cdi_pct=eq.as_cdi_pct,
                as_ipca_spread=eq.as_ipca_spread,
                as_selic_spread=eq.as_selic_spread,
                net_ytm=round(net_ytm(o, ctx), 4),
                tax_exempt=o.tax_exempt,
            )
        )
    rows.sort(key=lambda r: r.nominal_annual, reverse=True)
    return rows
