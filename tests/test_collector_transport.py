"""Tests for the remote collector transports (snapshot files + HTTP)."""

from __future__ import annotations

from datetime import date, timedelta

import httpx
import pytest

from app.collector import build_collector_client
from app.collector.remote import (
    RemoteHttpCollectorClient,
    SnapshotFileCollectorClient,
)
from app.collector.server import create_collector_app
from app.collector.snapshot import SnapshotReader, SnapshotWriter
from app.config import Settings
from app.models import IndexType, MarketKind, Offer, ProductType


def _offer(oid: str = "s-1") -> Offer:
    return Offer(
        id=oid,
        issuer="Banco BTG Pactual",
        product_type=ProductType.CDB,
        index_type=IndexType.CDI,
        rate=110,
        maturity=date.today() + timedelta(days=365 * 2),
        min_investment=1000.0,
        fgc_eligible=True,
        rating="AAA",
        market=MarketKind.PRIMARY,
    )


def test_snapshot_roundtrip_and_tamper_detection(tmp_path):
    writer = SnapshotWriter(str(tmp_path), key="topsecretkey")
    writer.write_offers([_offer("a"), _offer("b")])
    writer.write_positions(None)

    reader = SnapshotReader(str(tmp_path), key="topsecretkey")
    offers = reader.read_offers()
    assert [o.id for o in offers] == ["a", "b"]
    assert reader.read_positions() is None

    # Wrong key (forged/!=) must fail verification.
    with pytest.raises(ValueError):
        SnapshotReader(str(tmp_path), key="wrongkey").read_offers()

    # Tampering with the file body is rejected.
    path = tmp_path / "offers.json"
    path.write_text(path.read_text().replace("Banco BTG Pactual", "Evil Bank"))
    with pytest.raises(ValueError):
        reader.read_offers()


@pytest.mark.asyncio
async def test_snapshot_client_reads_snapshots(tmp_path):
    SnapshotWriter(str(tmp_path), "k").write_offers([_offer("x")])
    settings = Settings(snapshot_dir=str(tmp_path), snapshot_key="k")
    client = SnapshotFileCollectorClient(settings)
    offers = await client.get_offers()
    assert [o.id for o in offers] == ["x"]
    assert await client.get_positions() is None


def test_factory_selects_transport():
    assert isinstance(
        build_collector_client(Settings(collector_transport="snapshot")),
        SnapshotFileCollectorClient,
    )
    assert isinstance(
        build_collector_client(Settings(collector_transport="http")),
        RemoteHttpCollectorClient,
    )


def test_collector_server_requires_token():
    from fastapi.testclient import TestClient

    app = create_collector_app(Settings(offer_source="mock", collector_token="tok"))
    with TestClient(app) as client:
        assert client.get("/offers").status_code == 401
        assert client.get("/health").status_code == 200
        ok = client.get("/offers", headers={"Authorization": "Bearer tok"})
        assert ok.status_code == 200 and len(ok.json()) > 0
        pos = client.get("/positions", headers={"Authorization": "Bearer tok"})
        assert pos.status_code == 200


@pytest.mark.asyncio
async def test_remote_http_client_against_collector_app():
    settings = Settings(offer_source="mock", collector_token="tok")
    app = create_collector_app(settings)
    transport = httpx.ASGITransport(app=app)
    http = httpx.AsyncClient(
        transport=transport,
        base_url="http://collector",
        headers={"Authorization": "Bearer tok"},
    )
    client = RemoteHttpCollectorClient(settings, client=http)
    try:
        offers = await client.get_offers()
        assert offers and all(isinstance(o, Offer) for o in offers)
    finally:
        await http.aclose()
