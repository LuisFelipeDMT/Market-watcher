"""REST + WebSocket endpoints for the opportunity tracker."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Query, Request, WebSocket, WebSocketDisconnect

from app.models import Opportunity
from app.tracker import OpportunityTracker, TrackerState

router = APIRouter()


def _tracker(request: Request) -> OpportunityTracker:
    return request.app.state.tracker


@router.get("/health")
async def health(request: Request) -> dict:
    tracker = _tracker(request)
    state = tracker.state
    return {
        "status": "ok",
        "source": state.source,
        "refresh_count": state.refresh_count,
        "updated_at": state.updated_at,
        "tracked_offers": len(state.opportunities),
        "error": state.error,
    }


@router.get("/offers", response_model=list)
async def list_offers(request: Request) -> list:
    """Raw offers from the latest snapshot (the papers on the shelf)."""
    return [o.offer for o in _tracker(request).state.opportunities]


@router.get("/opportunities", response_model=list[Opportunity])
async def list_opportunities(
    request: Request,
    only_highlights: bool = Query(
        False, description="Return only flagged opportunities."
    ),
    min_score: float = Query(0.0, ge=0.0, le=100.0),
    limit: int = Query(100, ge=1, le=500),
) -> list[Opportunity]:
    """Evaluated, ranked offers (best opportunity first)."""
    items = _tracker(request).state.opportunities
    if only_highlights:
        items = [o for o in items if o.is_opportunity]
    if min_score > 0:
        items = [o for o in items if o.opportunity_score >= min_score]
    return items[:limit]


@router.get("/opportunities/highlights", response_model=list[Opportunity])
async def highlights(request: Request) -> list[Opportunity]:
    """Shortcut for the currently flagged (highlighted) opportunities."""
    return [o for o in _tracker(request).state.opportunities if o.is_opportunity]


@router.post("/refresh", response_model=TrackerState)
async def force_refresh(request: Request) -> TrackerState:
    """Trigger an immediate refresh cycle (in addition to the timer)."""
    return await _tracker(request).refresh_once()


@router.websocket("/ws")
async def ws_updates(websocket: WebSocket) -> None:
    """Stream a fresh snapshot on every refresh cycle."""
    await websocket.accept()
    tracker: OpportunityTracker = websocket.app.state.tracker
    queue = tracker.subscribe()
    try:
        # Send the current snapshot immediately so clients aren't blank.
        await websocket.send_text(tracker.state.model_dump_json())
        while True:
            state = await queue.get()
            await websocket.send_text(state.model_dump_json())
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    finally:
        tracker.unsubscribe(queue)
