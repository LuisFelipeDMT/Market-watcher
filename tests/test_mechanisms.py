"""Tests for the new financial mechanisms: duration, cheapness, IR/IOF, FGC."""

from datetime import date, timedelta

from app.analysis.cheapness import cheapness_bps, interpolate_curve
from app.analysis.credit import credit_tier
from app.analysis.duration import compute_duration
from app.analysis.institution import get_institution_health
from app.analysis.yields import income_tax_rate, iof_factor, net_ytm
from app.models import (
    Holding,
    IndexType,
    MarketKind,
    Portfolio,
    ProductType,
)
from app.portfolio.service import PortfolioService
from app.portfolio.sizing import recommend_size

from tests.conftest import make_offer


# --- duration --------------------------------------------------------------

def test_floating_paper_has_near_zero_duration(context):
    offer = make_offer(index_type=IndexType.CDI, rate=110)
    d = compute_duration(offer, context)
    assert d.modified < 0.5  # post-fixed barely reacts to rates


def test_prefixed_long_paper_has_high_duration(context):
    short = make_offer(index_type=IndexType.PRE, rate=12,
                       maturity=date.today() + timedelta(days=365))
    long = make_offer(index_type=IndexType.PRE, rate=12,
                      maturity=date.today() + timedelta(days=365 * 8))
    assert compute_duration(long, context).modified > \
        compute_duration(short, context).modified


# --- IR / IOF --------------------------------------------------------------

def test_regressive_ir_decreases_with_term():
    assert income_tax_rate(100) > income_tax_rate(800)


def test_iof_only_first_30_days():
    assert iof_factor(5) > 0
    assert iof_factor(30) == 0
    assert iof_factor(400) == 0


def test_net_ytm_uses_secondary_offered_yield(context):
    base = make_offer(index_type=IndexType.IPCA, rate=6.0, tax_exempt=True)
    cheap = base.model_copy(update={"market": MarketKind.SECONDARY,
                                    "offered_ytm": 9.0, "rate": 9.0})
    assert net_ytm(cheap, context) > net_ytm(base, context)


# --- cheapness -------------------------------------------------------------

def test_interpolate_curve_midpoint():
    curve = {"1": 10.0, "3": 12.0}
    assert interpolate_curve(curve, 2) == 11.0


def test_secondary_above_reference_is_cheap(context):
    # IPCA debenture offered well above its fair spread -> positive cheapness.
    offer = make_offer(
        issuer="Vale S.A.", product_type=ProductType.DEBENTURE,
        index_type=IndexType.IPCA, rate=9.5, offered_ytm=9.5,
        market=MarketKind.SECONDARY, fgc_eligible=False, tax_exempt=True,
        rating="AAA",
    )
    health = get_institution_health(offer.issuer, offer.rating)
    assert cheapness_bps(offer, context, health) > 0


def test_credit_tier_mapping():
    aaa = make_offer(rating="AAA")
    assert credit_tier(aaa, get_institution_health("X", "AAA")) == "AAA"
    tesouro = make_offer(product_type=ProductType.TESOURO, rating="AAA")
    assert credit_tier(tesouro, get_institution_health("Tesouro Nacional")) == "SOVEREIGN"


# --- FGC + sizing ----------------------------------------------------------

def test_fgc_room_per_conglomerate(settings):
    pf = Portfolio(holdings=[
        Holding(issuer="Banco BTG Pactual", conglomerate="BTG",
                product_type=ProductType.CDB, amount=200_000, fgc_eligible=True),
    ])
    svc = PortfolioService(settings, pf)
    assert svc.fgc_room("Banco BTG Pactual") == 50_000.0  # 250k - 200k


def test_sizing_respects_fgc_cap(settings):
    pf = Portfolio(holdings=[
        Holding(issuer="Banco Master", conglomerate="MASTER",
                product_type=ProductType.CDB, amount=250_000, fgc_eligible=True),
    ])
    svc = PortfolioService(settings, pf)
    offer = make_offer(issuer="Banco Master", fgc_eligible=True,
                       product_type=ProductType.CDB)
    sizing = recommend_size(offer, svc, settings)
    assert sizing.max_recommended == 0.0  # cap already used


def test_sizing_caps_non_fgc_issuer(settings):
    svc = PortfolioService(settings)  # empty -> default_portfolio_value
    offer = make_offer(issuer="Vale S.A.", product_type=ProductType.DEBENTURE,
                       fgc_eligible=False, min_investment=1000)
    sizing = recommend_size(offer, svc, settings)
    # 5% of default 100k = 5k cap.
    assert 0 < sizing.max_recommended <= 5_000.0
    assert sizing.fgc_room is None
