"""Application entrypoint: wires the source, tracker, and API together."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.alerts import AlertService
from app.api import alerts_router, equities_router, router
from app.collector import build_collector_client
from app.config import get_settings
from app.equities import EquityTracker, Watchlist
from app.equities.sources import build_equity_source
from app.market import build_market_provider
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
    # Analysis zone talks to the brokerage only through the collector client.
    collector_client = build_collector_client(settings)
    market_provider = build_market_provider(settings)
    portfolio_service = PortfolioService(settings)
    tracker = OpportunityTracker(
        collector_client, settings, market_provider, portfolio_service, alert_service
    )
    # Equities (renda variável) tracker shares the market provider.
    equity_tracker = EquityTracker(
        build_equity_source(settings),
        settings,
        build_market_provider(settings),
        Watchlist(settings.equity_watchlist_path),
        alert_service,
    )
    app.state.settings = settings
    app.state.alert_service = alert_service
    app.state.tracker = tracker
    app.state.equity_tracker = equity_tracker
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
