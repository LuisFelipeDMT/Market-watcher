import pytest

from app.config import Settings
from app.sources import build_source
from app.tracker import OpportunityTracker


@pytest.mark.asyncio
async def test_tracker_refresh_populates_state():
    settings = Settings(offer_source="mock")
    tracker = OpportunityTracker(build_source(settings), settings)
    state = await tracker.refresh_once()
    assert state.refresh_count == 1
    assert len(state.opportunities) > 0
    assert state.error is None


@pytest.mark.asyncio
async def test_new_opportunities_detected_once():
    settings = Settings(offer_source="mock", opportunity_threshold=50)
    tracker = OpportunityTracker(build_source(settings), settings)
    first = await tracker.refresh_once()
    # First cycle: any flagged offers are "new".
    flagged = [o for o in first.opportunities if o.is_opportunity]
    assert len(first.new_opportunity_ids) == len(flagged)
    # Second cycle: already-known opportunities are not re-reported as new.
    second = await tracker.refresh_once()
    assert set(second.new_opportunity_ids).isdisjoint(
        {o.offer.id for o in flagged}
    )


def test_api_endpoints_smoke():
    from fastapi.testclient import TestClient

    from app.main import create_app

    app = create_app()
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/offers").status_code == 200
        opps = client.get("/opportunities").json()
        assert isinstance(opps, list)
        assert len(opps) > 0
        client.post("/refresh")
        highlights = client.get("/opportunities/highlights").json()
        assert isinstance(highlights, list)
