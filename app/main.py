"""Application entrypoint: wires the source, tracker, and API together."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.api import router
from app.config import get_settings
from app.sources import build_source
from app.tracker import OpportunityTracker


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    source = build_source(settings)
    tracker = OpportunityTracker(source, settings)
    app.state.settings = settings
    app.state.tracker = tracker
    await tracker.start()
    try:
        yield
    finally:
        await tracker.stop()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Market Watcher",
        description="XP Brazil renda fixa opportunity tracker.",
        version=__version__,
        lifespan=lifespan,
    )
    app.include_router(router)
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
