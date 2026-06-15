from datetime import date, timedelta

import pytest

from app.config import Settings
from app.models import IndexType, Liquidity, Offer, ProductType


@pytest.fixture
def settings() -> Settings:
    return Settings(
        offer_source="mock",
        cdi_annual=10.65,
        selic_annual=10.75,
        ipca_annual=4.50,
        opportunity_threshold=70.0,
    )


def make_offer(**overrides) -> Offer:
    base = dict(
        id="t-1",
        issuer="Banco BTG Pactual",
        product_type=ProductType.CDB,
        index_type=IndexType.CDI,
        rate=110,
        maturity=date.today() + timedelta(days=365 * 2),
        min_investment=1000.0,
        liquidity=Liquidity.AT_MATURITY,
        fgc_eligible=True,
        tax_exempt=False,
        rating="AAA",
    )
    base.update(overrides)
    return Offer(**base)
