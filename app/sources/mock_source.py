"""A realistic mock offer source for development and testing.

It generates a stable universe of papers whose rates jitter slightly on each
refresh, so the tracker has live, changing data to evaluate and highlight.
The issuer set mirrors the kind of names found on XP's renda fixa shelf.
"""

from __future__ import annotations

import random
from datetime import date, timedelta

from app.config import Settings
from app.models import IndexType, Liquidity, Offer, ProductType
from app.sources.base import OfferSource

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


class MockOfferSource(OfferSource):
    """Generates a lifelike, slightly fluctuating set of offers."""

    name = "mock"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._rng = random.Random()

    async def fetch_offers(self) -> list[Offer]:
        today = date.today()
        offers: list[Offer] = []
        for i, (
            issuer,
            product,
            index,
            base_rate,
            years,
            min_inv,
            fgc,
            tax_exempt,
            rating,
        ) in enumerate(_UNIVERSE):
            # Jitter the rate a touch each cycle to emulate a live shelf.
            jitter = self._rng.uniform(-0.015, 0.015)
            rate = round(base_rate * (1 + jitter), 4)

            liquidity = (
                Liquidity.DAILY
                if product in (ProductType.TESOURO,)
                else Liquidity.AT_MATURITY
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
                )
            )
        return offers
