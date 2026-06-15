"""REST endpoints for recent alerts (shared by both engines)."""

from __future__ import annotations

from fastapi import APIRouter, Query, Request

from app.alerts import Alert, AlertKind, AlertService

router = APIRouter(prefix="/alerts", tags=["alerts"])


def _alerts(request: Request) -> AlertService:
    return request.app.state.alert_service


@router.get("", response_model=list[Alert])
async def list_alerts(
    request: Request,
    kind: AlertKind | None = Query(None, description="Filter by alert kind."),
    limit: int = Query(50, ge=1, le=200),
) -> list[Alert]:
    """Most recent alerts (newest first)."""
    items = _alerts(request).recent(limit)
    if kind is not None:
        items = [a for a in items if a.kind is kind]
    return items


@router.get("/health")
async def alerts_health(request: Request) -> dict:
    service = _alerts(request)
    return {"status": "ok", "sinks": service.sink_names, "recent": len(service.recent(200))}
