from app.analysis.opportunity import evaluate_offer, evaluate_offers
from app.models import IndexType, MarketKind, ProductType

from tests.conftest import make_offer


def test_attractive_safe_offer_is_opportunity(context, service, settings):
    # High % of CDI, AAA, FGC-covered, mid maturity.
    offer = make_offer(index_type=IndexType.CDI, rate=118, rating="AAA")
    opp = evaluate_offer(offer, context, service, settings)
    assert opp.is_opportunity
    assert opp.opportunity_score >= settings.opportunity_threshold


def test_negative_news_disqualifies(context, service, settings):
    # Banco Master carries a negative_news flag in the registry.
    offer = make_offer(
        issuer="Banco Master", index_type=IndexType.CDI, rate=130, rating="BBB"
    )
    opp = evaluate_offer(offer, context, service, settings)
    assert not opp.is_opportunity
    assert any("news" in r.lower() for r in opp.reasons)


def test_low_yield_below_threshold(context, service, settings):
    offer = make_offer(index_type=IndexType.CDI, rate=85, rating="AAA")
    opp = evaluate_offer(offer, context, service, settings)
    assert not opp.is_opportunity


def test_cheap_secondary_scores_above_equivalent_primary(context, service, settings):
    # Same paper; the secondary one is offered at a higher YTM (cheap).
    primary = make_offer(
        id="p", issuer="Vale S.A.", product_type=ProductType.DEBENTURE,
        index_type=IndexType.IPCA, rate=6.8, rating="AAA", fgc_eligible=False,
        tax_exempt=True,
    )
    secondary = primary.model_copy(
        update={
            "id": "s",
            "market": MarketKind.SECONDARY,
            "offered_ytm": 8.6,
            "rate": 8.6,
        }
    )
    op = evaluate_offer(primary, context, service, settings)
    os = evaluate_offer(secondary, context, service, settings)
    assert os.cheapness_bps > op.cheapness_bps
    assert os.opportunity_score > op.opportunity_score


def test_evaluate_offers_sorted_desc(context, service, settings):
    offers = [
        make_offer(id="a", index_type=IndexType.CDI, rate=90),
        make_offer(id="b", index_type=IndexType.CDI, rate=120),
    ]
    ranked = evaluate_offers(offers, context, service, settings)
    scores = [o.opportunity_score for o in ranked]
    assert scores == sorted(scores, reverse=True)
