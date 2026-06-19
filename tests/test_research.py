"""Tests for the fundamentals + research parsers (sample-based)."""

from __future__ import annotations

from app.equities.sources.research import parse_fundamentals, parse_research

# A Fundamentus/Status-Invest-style sample (percent ratios, percent yields).
_SAMPLE = {
    "pl": 8.5,
    "pvp": 1.4,
    "roe": 18.0,
    "roic": 15.0,
    "marg_liquida": 22.0,
    "div_liq_ebitda": 0.8,
    "liq_corrente": 1.6,
    "dy": 6.5,  # percent
    "lpa": 4.2,
    "vpa": 25.0,
}


def test_parse_fundamentals_maps_and_converts():
    f = parse_fundamentals(_SAMPLE)
    assert f.pl == 8.5 and f.pvp == 1.4
    assert f.roe == 18.0 and f.roic == 15.0
    assert f.net_margin == 22.0
    assert f.net_debt_ebitda == 0.8
    assert f.eps == 4.2 and f.bvps == 25.0
    assert f.dy == 0.065  # percent → fraction


def test_parse_fundamentals_tolerates_missing():
    f = parse_fundamentals({"p_l": 10.0, "p_vp": 2.0})
    assert f.pl == 10.0 and f.pvp == 2.0
    assert f.roe is None and f.dy is None


def test_parse_research():
    note = parse_research({
        "ticker": "petr4",
        "broker": "XP",
        "recommendation": "COMPRA",
        "preco_alvo": 45.5,
        "resumo": "Fluxo de caixa forte e dividendos.",
        "data": "2026-06-15",
    })
    assert note.ticker == "PETR4"
    assert note.broker == "XP"
    assert note.recommendation == "COMPRA"
    assert note.target_price == 45.5
    assert note.thesis.startswith("Fluxo")
    assert note.as_of == "2026-06-15"
