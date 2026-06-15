"""Standalone collector service (trusted zone) — read-only by construction.

Runs as its own process/OS user, holds the credentials, and exposes ONLY GET
endpoints returning sanitized models. It accepts no command that could affect
the account. Intended to bind to a Unix domain socket behind a bearer token;
the analysis service reaches it via :class:`RemoteHttpCollectorClient`.

Also hosts the phone-push 2FA submit endpoints (the return channel for login
approvals). Run with:  python -m app.collector.server
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException

from app.collector.sources import build_collector
from app.collector.twofa import TwoFactorBroker
from app.config import Settings, get_settings
from app.models import Offer, Portfolio

logger = logging.getLogger(__name__)


def _require_token(settings: Settings):
    async def _check(authorization: str = Header(default="")) -> None:
        expected = settings.collector_token
        if not expected:
            raise HTTPException(status_code=503, detail="Collector token not set")
        if authorization != f"Bearer {expected}":
            raise HTTPException(status_code=401, detail="Unauthorized")

    return _check


def create_collector_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    collector = build_collector(settings)
    # Use the collector's own broker (so login approvals and the API agree);
    # fall back to a standalone one for collectors without 2FA (e.g. mock).
    broker = getattr(collector, "twofa", None) or TwoFactorBroker(settings)
    guard = _require_token(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await collector.startup()
        try:
            yield
        finally:
            await collector.shutdown()

    app = FastAPI(title="Market Watcher — Collector", lifespan=lifespan)
    app.state.collector = collector
    app.state.twofa = broker

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "collector": collector.name}

    @app.get("/offers", response_model=list[Offer], dependencies=[Depends(guard)])
    async def offers() -> list[Offer]:
        return await collector.fetch_offers()

    @app.get("/positions", dependencies=[Depends(guard)])
    async def positions() -> Portfolio | None:
        return await collector.fetch_positions()

    # --- phone-push 2FA return channel -----------------------------------
    @app.get("/2fa/pending", dependencies=[Depends(guard)])
    async def twofa_pending() -> list[dict]:
        return broker.pending()

    @app.post("/2fa/{request_id}/approve", dependencies=[Depends(guard)])
    async def twofa_approve(request_id: str, body: dict) -> dict:
        ok = broker.submit(request_id, str(body.get("code", "")))
        if not ok:
            raise HTTPException(status_code=404, detail="No such pending request")
        return {"status": "approved"}

    @app.post("/2fa/{request_id}/deny", dependencies=[Depends(guard)])
    async def twofa_deny(request_id: str) -> dict:
        broker.deny(request_id)
        return {"status": "denied"}

    return app


def main() -> None:  # pragma: no cover - process entrypoint
    import uvicorn

    settings = get_settings()
    logging.basicConfig(level=settings.log_level.upper())
    uvicorn.run(
        create_collector_app(settings),
        uds=settings.collector_socket_path,
        log_level=settings.log_level,
    )


if __name__ == "__main__":  # pragma: no cover
    main()
