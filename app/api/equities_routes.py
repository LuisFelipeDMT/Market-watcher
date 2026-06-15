"""REST + WebSocket endpoints for the equities (renda variável) tracker."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Query, Request, WebSocket, WebSocketDisconnect

from app.equities.models import AssetKind, EquityOpportunity, WatchState
from app.equities.tracker import EquityTracker, EquityTrackerState

router = APIRouter(prefix="/equities", tags=["equities"])


def _tracker(request: Request) -> EquityTracker:
    return request.app.state.equity_tracker


@router.get("/health")
async def health(request: Request) -> dict:
    state = _tracker(request).state
    return {
        "status": "ok",
        "source": state.source,
        "market_source": state.market_source,
        "refresh_count": state.refresh_count,
        "updated_at": state.updated_at,
        "tracked": len(state.opportunities),
        "state_counts": state.state_counts,
        "newly_triggered": state.newly_triggered,
        "error": state.error,
    }


@router.get("/opportunities", response_model=list[EquityOpportunity])
async def list_opportunities(
    request: Request,
    state: WatchState | None = Query(None, description="Filter by pipeline state."),
    kind: AssetKind | None = Query(None, description="STOCK or FII."),
    min_score: float = Query(0.0, ge=0.0, le=100.0),
    limit: int = Query(100, ge=1, le=500),
) -> list[EquityOpportunity]:
    """Evaluated, ranked universe (TRIGGERED first, then by score)."""
    items = _tracker(request).state.opportunities
    if state is not None:
        items = [o for o in items if o.state is state]
    if kind is not None:
        items = [o for o in items if o.stock.asset_kind is kind]
    if min_score > 0:
        items = [o for o in items if o.opportunity_score >= min_score]
    return items[:limit]


@router.get("/triggered", response_model=list[EquityOpportunity])
async def triggered(request: Request) -> list[EquityOpportunity]:
    """The "buy now" list — names in the buy zone with a timing signal."""
    return [
        o for o in _tracker(request).state.opportunities if o.is_opportunity
    ]


@router.get("/watchlist", response_model=list[EquityOpportunity])
async def watchlist(request: Request) -> list[EquityOpportunity]:
    """Names being tracked toward a buy (WATCH + ARMED + TRIGGERED)."""
    keep = {WatchState.WATCH, WatchState.ARMED, WatchState.TRIGGERED}
    return [o for o in _tracker(request).state.opportunities if o.state in keep]


@router.get("/{ticker}", response_model=EquityOpportunity)
async def get_ticker(request: Request, ticker: str) -> EquityOpportunity:
    """Full fundamental + valuation + technical breakdown for one ticker."""
    upper = ticker.upper()
    for o in _tracker(request).state.opportunities:
        if o.ticker.upper() == upper:
            return o
    raise HTTPException(status_code=404, detail=f"Ticker {ticker} not tracked")


@router.post("/refresh", response_model=EquityTrackerState)
async def force_refresh(request: Request) -> EquityTrackerState:
    """Trigger an immediate equity refresh + evaluation cycle."""
    return await _tracker(request).refresh_once()


@router.websocket("/ws")
async def ws_updates(websocket: WebSocket) -> None:
    """Stream a fresh equity snapshot on every refresh cycle."""
    from app.api.auth import ws_authorized

    if not ws_authorized(websocket):
        await websocket.close(code=1008)
        return
    await websocket.accept()
    tracker: EquityTracker = websocket.app.state.equity_tracker
    queue = tracker.subscribe()
    try:
        await websocket.send_text(tracker.state.model_dump_json())
        while True:
            state = await queue.get()
            await websocket.send_text(state.model_dump_json())
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    finally:
        tracker.unsubscribe(queue)
