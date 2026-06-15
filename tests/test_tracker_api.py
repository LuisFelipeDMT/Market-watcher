import pytest

from app.config import Settings
from app.market import build_market_provider
from app.portfolio import PortfolioService
from app.sources import build_source
from app.tracker import OpportunityTracker


def _build_tracker(settings: Settings) -> OpportunityTracker:
    return OpportunityTracker(
        build_source(settings),
        settings,
        build_market_provider(settings),
        PortfolioService(settings),
    )


@pytest.mark.asyncio
async def test_tracker_refresh_populates_state():
    settings = Settings(offer_source="mock", market_source="fixtures")
    tracker = _build_tracker(settings)
    await tracker._refresh_market(force=True)
    state = await tracker.refresh_once()
    assert state.refresh_count == 1
    assert len(state.opportunities) > 0
    assert state.error is None
    assert state.market_source == "fixtures"


@pytest.mark.asyncio
async def test_new_opportunities_detected_once():
    settings = Settings(
        offer_source="mock", market_source="fixtures", opportunity_threshold=50
    )
    tracker = _build_tracker(settings)
    await tracker._refresh_market(force=True)
    first = await tracker.refresh_once()
    flagged = [o for o in first.opportunities if o.is_opportunity]
    assert len(first.new_opportunity_ids) == len(flagged)
    second = await tracker.refresh_once()
    assert set(second.new_opportunity_ids).isdisjoint(
        {o.offer.id for o in flagged}
    )


def test_api_endpoints_smoke(monkeypatch):
    monkeypatch.setenv("MARKET_SOURCE", "fixtures")
    monkeypatch.setenv("OFFER_SOURCE", "mock")
    from fastapi.testclient import TestClient

    from app.config import get_settings
    from app.main import create_app

    get_settings.cache_clear()  # pick up the env overrides above
    app = create_app()
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/offers").status_code == 200
        opps = client.get("/opportunities").json()
        assert isinstance(opps, list) and len(opps) > 0
        client.post("/refresh")
        assert client.get("/opportunities/highlights").status_code == 200
        assert client.get("/opportunities/secondary").status_code == 200
        assert client.get("/market").json()["cdi_annual"] > 0
        port = client.get("/portfolio").json()
        assert "holdings" in port
