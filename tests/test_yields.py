from datetime import date, timedelta

from app.analysis.yields import gross_annual_yield, normalize_yield
from app.models import IndexType

from tests.conftest import make_offer


def test_cdi_gross_yield(settings):
    offer = make_offer(index_type=IndexType.CDI, rate=110)
    # 110% of CDI(10.65) = 11.715
    assert gross_annual_yield(offer, settings) == 11.715


def test_pre_gross_yield(settings):
    offer = make_offer(index_type=IndexType.PRE, rate=13.0)
    assert gross_annual_yield(offer, settings) == 13.0


def test_ipca_gross_yield(settings):
    offer = make_offer(index_type=IndexType.IPCA, rate=6.0)
    # IPCA(4.5) + 6.0 spread
    assert gross_annual_yield(offer, settings) == 10.5


def test_tax_exempt_net_equals_gross(settings):
    offer = make_offer(tax_exempt=True)
    gross, net, _ = normalize_yield(offer, settings)
    assert net == gross


def test_taxed_net_below_gross(settings):
    offer = make_offer(tax_exempt=False)
    gross, net, _ = normalize_yield(offer, settings)
    assert net < gross


def test_regressive_ir_longer_term_pays_less_tax(settings):
    short = make_offer(maturity=date.today() + timedelta(days=100))
    long = make_offer(maturity=date.today() + timedelta(days=800))
    _, short_net, _ = normalize_yield(short, settings)
    _, long_net, _ = normalize_yield(long, settings)
    assert long_net > short_net  # 15% IR beats 22.5% IR
