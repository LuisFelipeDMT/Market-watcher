"""Mobile gateway endpoints consumed by the phone app (behind dashboard auth)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.mobile.feed import build_proposals
from app.mobile.models import DeviceRegistration, FeedSummary, Proposal

router = APIRouter(prefix="/mobile", tags=["mobile"])


def _proposals(request: Request) -> list[Proposal]:
    bond_state = request.app.state.tracker.state
    equity_state = request.app.state.equity_tracker.state
    return build_proposals(bond_state.opportunities, equity_state.opportunities)


@router.get("/summary", response_model=FeedSummary)
async def summary(request: Request) -> FeedSummary:
    """At-a-glance home/badge data: counts by asset class + the top names."""
    proposals = _proposals(request)
    counts: dict[str, int] = {}
    for p in proposals:
        counts[p.asset_class.value] = counts.get(p.asset_class.value, 0) + 1
    updates = [
        request.app.state.tracker.state.updated_at,
        request.app.state.equity_tracker.state.updated_at,
    ]
    updates = [u for u in updates if u is not None]
    return FeedSummary(
        updated_at=max(updates) if updates else None,
        total=len(proposals),
        counts=counts,
        top=[p.title for p in proposals[:5]],
    )


@router.get("/proposals", response_model=list[Proposal])
async def proposals(request: Request) -> list[Proposal]:
    """The unified, ranked feed of things to consider buying."""
    return _proposals(request)


@router.get("/proposals/{proposal_id:path}", response_model=Proposal)
async def proposal_detail(request: Request, proposal_id: str) -> Proposal:
    for p in _proposals(request):
        if p.id == proposal_id:
            return p
    raise HTTPException(status_code=404, detail="Proposal not found")


# --- device registration for push -----------------------------------------
@router.get("/devices", response_model=list[DeviceRegistration])
async def list_devices(request: Request) -> list[DeviceRegistration]:
    return request.app.state.device_registry.list()


@router.post("/devices", response_model=DeviceRegistration)
async def register_device(request: Request, reg: DeviceRegistration) -> DeviceRegistration:
    return request.app.state.device_registry.register(reg)


@router.delete("/devices/{device_id}")
async def unregister_device(request: Request, device_id: str) -> dict:
    removed = request.app.state.device_registry.unregister(device_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Device not found")
    return {"status": "removed"}


# --- 2FA approval surface (forwarded to the collector) ---------------------
@router.get("/2fa/pending")
async def twofa_pending(request: Request) -> list[dict]:
    return await request.app.state.twofa_gateway.pending()


@router.post("/2fa/{request_id}/approve")
async def twofa_approve(request: Request, request_id: str, body: dict) -> dict:
    ok = await request.app.state.twofa_gateway.approve(
        request_id, str(body.get("code", ""))
    )
    if not ok:
        raise HTTPException(status_code=404, detail="No such pending request")
    return {"status": "approved"}


@router.post("/2fa/{request_id}/deny")
async def twofa_deny(request: Request, request_id: str) -> dict:
    await request.app.state.twofa_gateway.deny(request_id)
    return {"status": "denied"}
