"""Allocator + macro-view endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from app.analysis.allocator import AllocationPlan, allocate
from app.analysis.copom import MacroView, macro_view

router = APIRouter(tags=["analysis"])


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
