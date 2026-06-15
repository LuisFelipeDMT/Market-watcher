"""Market-analysis signals about issuing institutions.

This is the "no bad signs about the institution" input to the opportunity
definition. For now it's a static registry; a real deployment would refresh
these from ratings agencies, the Banco Central (Basel index, interventions),
and a news-sentiment feed.
"""

from __future__ import annotations

from app.models import InstitutionHealth

# Known issuers and their current health signals.
_REGISTRY: dict[str, InstitutionHealth] = {
    "Banco BTG Pactual": InstitutionHealth(
        issuer="Banco BTG Pactual", rating="AAA", basel_index=15.8
    ),
    "Banco Master": InstitutionHealth(
        issuer="Banco Master",
        rating="BBB",
        basel_index=11.2,
        negative_news=True,
        notes=["Rapid asset growth funded by high-rate CDBs; monitor closely."],
    ),
    "Banco Daycoval": InstitutionHealth(
        issuer="Banco Daycoval", rating="AA", basel_index=14.1
    ),
    "Banco ABC Brasil": InstitutionHealth(
        issuer="Banco ABC Brasil", rating="AA+", basel_index=15.0
    ),
    "Banco Inter": InstitutionHealth(
        issuer="Banco Inter", rating="A+", basel_index=13.0
    ),
    "Banco do Brasil": InstitutionHealth(
        issuer="Banco do Brasil", rating="AAA", basel_index=16.5
    ),
    "Itau Unibanco": InstitutionHealth(
        issuer="Itau Unibanco", rating="AAA", basel_index=16.9
    ),
    "Tesouro Nacional": InstitutionHealth(
        issuer="Tesouro Nacional", rating="AAA"
    ),
    "Vale S.A.": InstitutionHealth(issuer="Vale S.A.", rating="AAA"),
    "Energisa": InstitutionHealth(issuer="Energisa", rating="AA"),
    "Rumo Logistica": InstitutionHealth(issuer="Rumo Logistica", rating="AA-"),
    "MRV Engenharia": InstitutionHealth(issuer="MRV Engenharia", rating="A"),
    "Banco Pine": InstitutionHealth(
        issuer="Banco Pine", rating="BBB-", basel_index=12.4
    ),
    "Banco Sofisa": InstitutionHealth(
        issuer="Banco Sofisa", rating="A", basel_index=14.5
    ),
}


def get_institution_health(issuer: str, fallback_rating: str | None = None) -> InstitutionHealth:
    """Return health signals for an issuer.

    Unknown issuers get a conservative neutral profile using the offer's own
    rating (if any) so they are still scoreable.
    """
    known = _REGISTRY.get(issuer)
    if known is not None:
        return known
    return InstitutionHealth(
        issuer=issuer,
        rating=fallback_rating,
        notes=["Issuer not in market-analysis registry; treated as neutral."],
    )
