"""Application entrypoint: wires the source, tracker, and API together."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.alerts import AlertService
from app.api import alerts_router, equities_router, router
from app.api.mobile_routes import router as mobile_router
from app.api.analysis_routes import router as analysis_router
from app.api.history_routes import router as history_router
from app.api.orders_routes import router as orders_router
from app.collector.audit import build_audit_log
from app.execution import OrderLedger, OrderService, build_executor
from app.collector import build_collector_client
from app.config import get_settings
from app.equities import EquityTracker, Watchlist
from app.equities.sources import build_equity_source
from app.history import build_history_store
from app.market import build_market_provider
from app.mobile import (
    DeviceRegistry,
    PushAlertSink,
    build_push_sender,
    build_twofa_gateway,
)
from app.portfolio import PortfolioService
from app.tracker import OpportunityTracker


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    # Shared alerting service feeds both trackers.
    alert_service = AlertService(settings)
    history = build_history_store(settings)
    # Analysis zone talks to the brokerage only through the collector client.
    collector_client = build_collector_client(settings)
    market_provider = build_market_provider(settings)
    portfolio_service = PortfolioService(settings)
    tracker = OpportunityTracker(
        collector_client, settings, market_provider, portfolio_service,
        alert_service, history,
    )
    # Equities (renda variável) tracker shares the market provider.
    equity_tracker = EquityTracker(
        build_equity_source(settings),
        settings,
        build_market_provider(settings),
        Watchlist(settings.equity_watchlist_path),
        alert_service,
        history,
    )
    # Mobile gateway: device registry, push sink, and the 2FA app surface.
    device_registry = DeviceRegistry(settings.device_registry_path)
    alert_service.add_sink(PushAlertSink(device_registry, build_push_sender(settings)))

    app.state.settings = settings
    app.state.alert_service = alert_service
    app.state.history = history
    app.state.tracker = tracker
    app.state.equity_tracker = equity_tracker
    app.state.device_registry = device_registry
    app.state.twofa_gateway = build_twofa_gateway(settings)
    # Assisted-purchase service (mock executor until live XP is wired).
    app.state.order_service = OrderService(
        settings,
        build_executor(settings),
        OrderLedger(settings.order_ledger_path),
        build_audit_log(settings),
        alert_service,
    )
    await tracker.start()
    await equity_tracker.start()
    try:
        yield
    finally:
        await equity_tracker.stop()
        await tracker.stop()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Market Watcher",
        description="XP Brazil renda fixa opportunity tracker.",
        version=__version__,
        lifespan=lifespan,
    )
    app.include_router(router)
    app.include_router(equities_router)
    app.include_router(alerts_router)
    app.include_router(mobile_router)
    app.include_router(history_router)
    app.include_router(analysis_router)
    app.include_router(orders_router)
    # Optional app-level auth (in addition to running behind a VPN).
    settings = get_settings()
    if settings.dashboard_token:
        from app.api.auth import BearerAuthMiddleware

        app.add_middleware(BearerAuthMiddleware, token=settings.dashboard_token)
    return app


app = create_app()


def main() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level,
    )


if __name__ == "__main__":
    main()
