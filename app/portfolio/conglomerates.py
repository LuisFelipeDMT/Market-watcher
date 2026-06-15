"""Issuer → financial conglomerate and issuer → sector maps.

The FGC counts all institutions in the same conglomerate as ONE for the R$250k
limit, so exposure must be aggregated by conglomerate, not by issuer name.
Sectors drive non-FGC diversification (avoid over-concentrating one industry).
"""

from __future__ import annotations

# Issuer (as seen on the platform) -> conglomerate key.
CONGLOMERATE: dict[str, str] = {
    "Banco BTG Pactual": "BTG",
    "Banco Master": "MASTER",
    "Banco Daycoval": "DAYCOVAL",
    "Banco ABC Brasil": "ABC",
    "Banco Inter": "INTER",
    "Banco do Brasil": "BB",
    "Itau Unibanco": "ITAU",
    "Banco Itau": "ITAU",
    "Banco Pine": "PINE",
    "Banco Sofisa": "SOFISA",
    "Tesouro Nacional": "SOBERANO",
}

# Issuer -> sector (for non-FGC credit diversification).
SECTOR: dict[str, str] = {
    "Vale S.A.": "Mining",
    "Energisa": "Utilities",
    "Rumo Logistica": "Logistics",
    "MRV Engenharia": "RealEstate",
    "Tesouro Nacional": "Sovereign",
}


def conglomerate_of(issuer: str) -> str:
    """Return the conglomerate key for an issuer (falls back to its own name)."""
    return CONGLOMERATE.get(issuer, issuer.upper().strip())


def sector_of(issuer: str) -> str:
    """Return the sector for an issuer (falls back to 'Other')."""
    return SECTOR.get(issuer, "Other")
