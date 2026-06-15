from app.analysis.opportunity import evaluate_offer, evaluate_offers
from app.models import IndexType, ProductType

from tests.conftest import make_offer


def test_attractive_safe_offer_is_opportunity(settings):
    # High % of CDI, AAA, FGC-covered, mid maturity.
    offer = make_offer(index_type=IndexType.CDI, rate=118, rating="AAA")
    opp = evaluate_offer(offer, settings)
    assert opp.is_opportunity
    assert opp.opportunity_score >= settings.opportunity_threshold


def test_negative_news_disqualifies(settings):
    # Banco Master carries a negative_news flag in the registry.
    offer = make_offer(issuer="Banco Master", index_type=IndexType.CDI, rate=130, rating="BBB")
    opp = evaluate_offer(offer, settings)
    assert not opp.is_opportunity
    assert any("news" in r.lower() for r in opp.reasons)


def test_low_yield_below_threshold(settings):
    offer = make_offer(index_type=IndexType.CDI, rate=85, rating="AAA")
    opp = evaluate_offer(offer, settings)
    assert not opp.is_opportunity


def test_evaluate_offers_sorted_desc(settings):
    offers = [
        make_offer(id="a", index_type=IndexType.CDI, rate=90),
        make_offer(id="b", index_type=IndexType.CDI, rate=120),
    ]
    ranked = evaluate_offers(offers, settings)
    scores = [o.opportunity_score for o in ranked]
    assert scores == sorted(scores, reverse=True)
