"""A realistic mock collector for development and testing.

It generates a stable universe of primary papers whose rates jitter slightly
each refresh, plus a set of SECONDARY-market offers (papers other investors are
reselling) — some deliberately priced cheap vs fair to exercise the
opportunity engine. It also returns a mock portfolio so FGC/diversification
sizing is demonstrable offline.
"""

from __future__ import annotations

import random
from datetime import date, timedelta

from app.collector.base import Collector
from app.config import Settings
from app.models import (
    Holding,
    IndexType,
    Liquidity,
    MarketKind,
    Offer,
    Portfolio,
    ProductType,
)
from app.portfolio.conglomerates import conglomerate_of, sector_of

# (issuer, product, index, base_rate, years, min_inv, fgc, tax_exempt, rating)
_UNIVERSE: list[tuple] = [
    ("Banco BTG Pactual", ProductType.CDB, IndexType.CDI, 104, 2, 1000, True, False, "AAA"),
    ("Banco BTG Pactual", ProductType.LCI, IndexType.CDI, 92, 3, 1000, True, True, "AAA"),
    ("Banco Master", ProductType.CDB, IndexType.CDI, 120, 3, 1000, True, False, "BBB"),
    ("Banco Master", ProductType.CDB, IndexType.PRE, 14.2, 2, 1000, True, False, "BBB"),
    ("Banco Daycoval", ProductType.CDB, IndexType.CDI, 108, 2, 5000, True, False, "AA"),
    ("Banco ABC Brasil", ProductType.CDB, IndexType.IPCA, 6.4, 4, 5000, True, False, "AA+"),
    ("Banco Inter", ProductType.LCI, IndexType.CDI, 90, 2, 1000, True, True, "A+"),
    ("Banco do Brasil", ProductType.LCA, IndexType.CDI, 88, 2, 1000, True, True, "AAA"),
    ("Itau Unibanco", ProductType.CDB, IndexType.CDI, 98, 3, 1000, True, False, "AAA"),
    ("Tesouro Nacional", ProductType.TESOURO, IndexType.IPCA, 6.0, 10, 30, False, False, "AAA"),
    ("Tesouro Nacional", ProductType.TESOURO, IndexType.PRE, 12.8, 5, 30, False, False, "AAA"),
    ("Tesouro Nacional", ProductType.TESOURO, IndexType.SELIC, 0.10, 3, 30, False, False, "AAA"),
    ("Vale S.A.", ProductType.DEBENTURE, IndexType.IPCA, 6.8, 6, 1000, False, True, "AAA"),
    ("Energisa", ProductType.DEBENTURE, IndexType.IPCA, 7.2, 7, 1000, False, True, "AA"),
    ("Rumo Logistica", ProductType.CRA, IndexType.IPCA, 7.6, 6, 1000, False, True, "AA-"),
    ("MRV Engenharia", ProductType.CRI, IndexType.IPCA, 8.4, 5, 1000, False, True, "A"),
    ("Banco Pine", ProductType.CDB, IndexType.CDI, 116, 3, 1000, True, False, "BBB-"),
    ("Banco Sofisa", ProductType.LCA, IndexType.CDI, 94, 2, 1000, True, True, "A"),
]

# Secondary offers: (issuer, product, index, offered_ytm, years, min_inv, fgc,
# tax_exempt, rating, qty). offered_ytm is the taxa de compra (the resale yield)
# — set deliberately above fair on several to model urgency/deságio.
_SECONDARY: list[tuple] = [
    ("Vale S.A.", ProductType.DEBENTURE, IndexType.IPCA, 8.3, 5, 1000, False, True, "AAA", 40),
    ("Energisa", ProductType.DEBENTURE, IndexType.IPCA, 8.9, 6, 1000, False, True, "AA", 25),
    ("Rumo Logistica", ProductType.CRA, IndexType.IPCA, 9.4, 5, 1000, False, True, "AA-", 30),
    ("MRV Engenharia", ProductType.CRI, IndexType.IPCA, 7.5, 4, 1000, False, True, "A", 15),
    ("Tesouro Nacional", ProductType.TESOURO, IndexType.PRE, 13.6, 5, 30, False, False, "AAA", 200),
    ("Banco Daycoval", ProductType.CDB, IndexType.PRE, 13.9, 3, 5000, True, False, "AA", 10),
]


class MockCollector(Collector):
    """Generates lifelike, slightly fluctuating primary + secondary offers."""

    name = "mock"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._rng = random.Random()

    async def fetch_offers(self) -> list[Offer]:
        today = date.today()
        offers: list[Offer] = []

        for i, (
            issuer, product, index, base_rate, years, min_inv, fgc, tax_exempt, rating
        ) in enumerate(_UNIVERSE):
            jitter = self._rng.uniform(-0.015, 0.015)
            rate = round(base_rate * (1 + jitter), 4)
            liquidity = (
                Liquidity.DAILY if product is ProductType.TESOURO else Liquidity.AT_MATURITY
            )
            offers.append(
                Offer(
                    id=f"mock-{i:03d}",
                    issuer=issuer,
                    product_type=product,
                    index_type=index,
                    rate=rate,
                    maturity=today + timedelta(days=int(years * 365)),
                    min_investment=float(min_inv),
                    liquidity=liquidity,
                    fgc_eligible=fgc,
                    tax_exempt=tax_exempt,
                    rating=rating,
                    market=MarketKind.PRIMARY,
                )
            )

        for j, (
            issuer, product, index, ytm, years, min_inv, fgc, tax_exempt, rating, qty
        ) in enumerate(_SECONDARY):
            jitter = self._rng.uniform(-0.03, 0.03)
            offered = round(ytm + jitter, 4)
            offers.append(
                Offer(
                    id=f"mock-sec-{j:03d}",
                    issuer=issuer,
                    product_type=product,
                    index_type=index,
                    rate=offered,
                    offered_ytm=offered,
                    maturity=today + timedelta(days=int(years * 365)),
                    min_investment=float(min_inv),
                    liquidity=Liquidity.AT_MATURITY,
                    fgc_eligible=fgc,
                    tax_exempt=tax_exempt,
                    rating=rating,
                    market=MarketKind.SECONDARY,
                    quantity_available=qty,
                    face_value=1000.0,
                )
            )
        return offers

    async def fetch_positions(self) -> Portfolio:
        """A demo portfolio with some FGC usage and a concentrated issuer."""
        holdings = [
            Holding(
                issuer="Banco BTG Pactual",
                conglomerate=conglomerate_of("Banco BTG Pactual"),
                product_type=ProductType.CDB,
                amount=180_000.0,
                fgc_eligible=True,
            ),
            Holding(
                issuer="Banco Master",
                conglomerate=conglomerate_of("Banco Master"),
                product_type=ProductType.CDB,
                amount=250_000.0,
                fgc_eligible=True,
            ),
            Holding(
                issuer="Vale S.A.",
                conglomerate=conglomerate_of("Vale S.A."),
                product_type=ProductType.DEBENTURE,
                amount=30_000.0,
                fgc_eligible=False,
                sector=sector_of("Vale S.A."),
            ),
        ]
        return Portfolio(holdings=holdings)
