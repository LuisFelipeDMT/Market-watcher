from app.analysis.institution import get_institution_health
from app.analysis.risk import assess_risk
from app.models import InstitutionHealth, Liquidity, ProductType

from tests.conftest import make_offer


def test_tesouro_aaa_is_low_risk():
    offer = make_offer(
        issuer="Tesouro Nacional",
        product_type=ProductType.TESOURO,
        rating="AAA",
        fgc_eligible=False,
        liquidity=Liquidity.DAILY,
    )
    health = get_institution_health(offer.issuer, offer.rating)
    risk = assess_risk(offer, health)
    assert risk.score < 15


def test_intervention_maxes_institution_risk():
    offer = make_offer(issuer="Bad Bank", rating="AAA")
    health = InstitutionHealth(issuer="Bad Bank", under_intervention=True)
    risk = assess_risk(offer, health)
    assert risk.institution_factor > 0
    assert any("intervention" in f.lower() for f in risk.flags)


def test_fgc_reduces_risk():
    covered = make_offer(fgc_eligible=True)
    uncovered = make_offer(fgc_eligible=False)
    h = get_institution_health(covered.issuer, covered.rating)
    assert assess_risk(covered, h).score < assess_risk(uncovered, h).score


def test_low_rating_increases_risk():
    aaa = make_offer(issuer="X", rating="AAA")
    junk = make_offer(issuer="X", rating="B")
    h_aaa = get_institution_health("X", "AAA")
    h_junk = get_institution_health("X", "B")
    assert assess_risk(junk, h_junk).score > assess_risk(aaa, h_aaa).score
