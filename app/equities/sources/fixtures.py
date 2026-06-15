"""Offline equity universe — the dev default and the live fallback.

A compact but lifelike set of Brazilian stocks and FIIs with fundamentals and
synthetically shaped price histories, so the two-stage engine produces a mix of
TRIGGERED / ARMED / WATCH / REJECTED states without any network access (and
tests stay deterministic).
"""

from __future__ import annotations

import math

from app.equities.models import AssetKind, FiiMetrics, Fundamentals, Stock
from app.equities.sources.base import EquitySnapshot, EquitySource

# Typical sector P/L multiples used by the peer-multiple valuation.
_PEER_MULTIPLES: dict[str, float] = {
    "Bancos": 8.0,
    "Petróleo": 6.0,
    "Mineração": 6.0,
    "Bens Industriais": 20.0,
    "Bebidas": 18.0,
    "Varejo": 16.0,
    "Saúde": 22.0,
    "Energia": 8.0,
}

# Stocks: ticker, name, sector, price, eps, bvps, dps, fcf_ps, roe%, roic%,
# gross_m%, ebit_m%, net_m%, net_debt/ebitda, current_ratio, rev_cagr%,
# eps_cagr%, earnings_consistency(0..1), shares_cagr%, payout(0..1), profile.
_STOCKS: list[tuple] = [
    ("PETR4", "Petrobras PN", "Petróleo", 38.0, 9.0, 30.0, 5.5, 11.0,
     28, 22, 48, 40, 26, 0.8, 1.3, 6, 5, 0.8, -1.0, 0.60, "oversold"),
    ("BBAS3", "Banco do Brasil ON", "Bancos", 27.0, 7.2, 40.0, 3.2, 7.0,
     20, 18, 0, 0, 30, 0.0, 1.4, 8, 6, 1.0, 0.0, 0.45, "oversold"),
    ("VALE3", "Vale ON", "Mineração", 55.0, 8.5, 38.0, 4.5, 9.0,
     22, 18, 45, 38, 24, 0.5, 1.6, 5, 4, 0.8, -0.5, 0.53, "neutral"),
    ("ITUB4", "Itaú Unibanco PN", "Bancos", 32.0, 3.8, 22.0, 1.6, 4.0,
     20, 18, 0, 0, 28, 0.0, 1.5, 9, 8, 1.0, 0.0, 0.45, "neutral"),
    ("CMIG4", "Cemig PN", "Energia", 11.0, 1.8, 7.0, 1.2, 1.6,
     24, 18, 35, 28, 18, 1.2, 1.3, 7, 5, 0.8, 0.0, 0.66, "extended"),
    ("ABEV3", "Ambev ON", "Bebidas", 13.0, 1.1, 7.0, 0.9, 1.2,
     17, 16, 50, 32, 20, -0.4, 1.4, 6, 5, 1.0, 0.0, 0.80, "neutral"),
    ("WEGE3", "WEG ON", "Bens Industriais", 52.0, 1.4, 6.0, 0.5, 1.5,
     30, 28, 33, 22, 17, -0.2, 2.2, 18, 15, 1.0, 0.0, 0.40, "extended"),
    ("RADL3", "Raia Drogasil ON", "Saúde", 26.0, 0.7, 4.0, 0.2, 0.6,
     17, 14, 30, 8, 5, 0.9, 1.6, 16, 14, 1.0, 1.5, 0.30, "extended"),
    ("MGLU3", "Magazine Luiza ON", "Varejo", 11.0, -0.2, 1.5, 0.0, -0.1,
     -8, -4, 28, -2, -5, 3.5, 0.9, 4, -20, 0.2, 6.0, 0.0, "oversold"),
]

# FIIs: ticker, name, segment, price, dps(TTM), nav_per_share, vacancy(0..1),
# n_assets, management_fee(0..1), profile.
_FIIS: list[tuple] = [
    ("KNRI11", "Kinea Renda Imobiliária", "híbrido", 140.0, 13.0, 168.0,
     0.06, 20, 0.010, "oversold"),
    ("HGLG11", "CSHG Logística", "logística", 158.0, 13.0, 165.0,
     0.04, 18, 0.008, "neutral"),
    ("XPML11", "XP Malls", "shoppings", 105.0, 8.5, 110.0,
     0.05, 15, 0.010, "neutral"),
    ("MXRF11", "Maxi Renda", "papel", 10.2, 1.0, 10.0,
     0.00, 40, 0.010, "neutral"),
    ("VISC11", "Vinci Shopping Centers", "shoppings", 110.0, 7.0, 100.0,
     0.07, 12, 0.012, "extended"),
]


def _price_history(price: float, profile: str, seed: int, n: int = 260) -> list[float]:
    """Build a ~1y daily-close path whose shape matches ``profile``.

    - ``oversold``: rallied to a high then fell back to ``price`` (big drawdown,
      low RSI) — a timing TRIGGER candidate.
    - ``extended``: rose steadily into ``price`` near its 52w high (high RSI) —
      cheap on fundamentals but ARMED, waiting for a better entry.
    - ``neutral``: gently mean-reverting around ``price``.
    """
    if profile == "oversold":
        start_ratio, high_ratio, end_drift = 1.05, 1.40, "down"
    elif profile == "extended":
        start_ratio, high_ratio, end_drift = 0.70, 1.00, "up"
    else:
        start_ratio, high_ratio, end_drift = 0.92, 1.12, "flat"

    start = price * start_ratio
    high = price * high_ratio
    half = n // 2
    out: list[float] = []
    for i in range(n):
        if i <= half:  # ramp from start up to the 52w high
            base = start + (high - start) * (i / half)
        else:  # from the high toward the current price
            t = (i - half) / (n - half)
            if end_drift == "up":
                base = high * (1 - 0.001) + (price - high) * t
            else:
                base = high + (price - high) * t
        # tiny deterministic wiggle (kept small so RSI direction is preserved)
        wiggle = 1 + 0.003 * math.sin((i + seed) * 0.7)
        out.append(round(base * wiggle, 2))
    out[-1] = price  # anchor the latest close to the quoted price
    return out


class FixturesEquitySource(EquitySource):
    """Returns the static equity universe. Never touches the network."""

    name = "fixtures"
    peer_multiples = _PEER_MULTIPLES

    async def fetch_universe(self) -> list[EquitySnapshot]:
        snapshots: list[EquitySnapshot] = []

        for seed, row in enumerate(_STOCKS):
            (ticker, name, sector, price, eps, bvps, dps, fcf_ps, roe, roic,
             gross_m, ebit_m, net_m, nd_ebitda, current_ratio, rev_cagr,
             eps_cagr, consistency, shares_cagr, payout, profile) = row
            stock = Stock(
                ticker=ticker,
                name=name,
                asset_kind=AssetKind.STOCK,
                sector=sector,
                price=price,
                price_history=_price_history(price, profile, seed),
            )
            fundamentals = Fundamentals(
                eps=eps,
                bvps=bvps,
                dps=dps,
                fcf_per_share=fcf_ps,
                roe=roe,
                roic=roic,
                gross_margin=gross_m,
                ebit_margin=ebit_m,
                net_margin=net_m,
                net_debt_ebitda=nd_ebitda,
                current_ratio=current_ratio,
                revenue_cagr_5y=rev_cagr,
                earnings_cagr_5y=eps_cagr,
                earnings_consistency=consistency,
                shares_cagr_5y=shares_cagr,
                payout=payout,
                pl=round(price / eps, 2) if eps else None,
                pvp=round(price / bvps, 2) if bvps else None,
                dy=round(dps / price, 4) if price else None,
                fcf_yield=round(fcf_ps / price, 4) if price else None,
            )
            snapshots.append(EquitySnapshot(stock=stock, fundamentals=fundamentals))

        for seed, row in enumerate(_FIIS):
            (ticker, name, segment, price, dps, nav, vacancy, n_assets,
             fee, profile) = row
            stock = Stock(
                ticker=ticker,
                name=name,
                asset_kind=AssetKind.FII,
                sector=segment,
                price=price,
                price_history=_price_history(price, profile, seed + 100),
            )
            fii = FiiMetrics(
                dps=dps,
                nav_per_share=nav,
                p_vp=round(price / nav, 3) if nav else None,
                dy=round(dps / price, 4) if price else None,
                vacancy=vacancy,
                segment=segment,
                n_assets=n_assets,
                management_fee=fee,
            )
            snapshots.append(EquitySnapshot(stock=stock, fii=fii))

        return snapshots
