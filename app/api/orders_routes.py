"""Assisted-purchase endpoints (behind dashboard auth).

Write path: create a signed intent, confirm it, then execute with ephemeral
credentials. Backed by a MockExecutor until the live XP step is wired.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.execution import (
    IntentInvalid,
    KillSwitchEngaged,
    OrderCredentials,
    OrderIntent,
    OrderReceipt,
)

router = APIRouter(prefix="/orders", tags=["orders"])


def _svc(request: Request):
    return request.app.state.order_service


@router.post("", response_model=OrderIntent)
async def create(request: Request, body: dict) -> OrderIntent:
    try:
        return _svc(request).create_intent(
            asset_ref=str(body["asset_ref"]),
            quantity=float(body["quantity"]),
            unit_price=float(body["unit_price"]),
            label=str(body.get("label", "")),
        )
    except (KeyError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=f"Invalid order: {exc}")


@router.post("/{intent_id}/confirm", response_model=OrderIntent)
async def confirm(request: Request, intent_id: str) -> OrderIntent:
    try:
        return _svc(request).confirm(intent_id)
    except KillSwitchEngaged as exc:
        raise HTTPException(status_code=423, detail=str(exc))
    except IntentInvalid as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/{intent_id}/execute", response_model=OrderReceipt)
async def execute(request: Request, intent_id: str, body: dict) -> OrderReceipt:
    creds = OrderCredentials(
        password=str(body.get("password", "")),
        token=str(body.get("token", "")),
        username=str(body.get("username", "")),
    )
    try:
        return await _svc(request).execute(intent_id, creds)
    except KillSwitchEngaged as exc:
        raise HTTPException(status_code=423, detail=str(exc))
    except IntentInvalid as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("")
async def list_orders(request: Request) -> dict:
    svc = _svc(request)
    return {
        "kill_switch": svc.kill_switch_engaged,
        "pending": [i.model_dump(mode="json") for i in svc.pending()],
        "executed": [r.model_dump(mode="json") for r in svc.history()],
    }


@router.post("/kill-switch")
async def kill_switch(request: Request, body: dict) -> dict:
    svc = _svc(request)
    if bool(body.get("engage", True)):
        svc.engage_kill_switch()
    else:
        svc.disengage_kill_switch()
    return {"kill_switch": svc.kill_switch_engaged}
