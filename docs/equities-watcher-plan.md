# Plan: Equities (renda variável) watcher — stocks + FIIs

> Status: **implemented** (initial cut). The two-stage engine, fixtures +
> brapi sources, valuation ensemble, timing state machine, persisted
> watchlist, `/equities/*` API and tests are live under `app/equities/`.
> This doc remains the design reference; phases 5–6 (research scraping, CVM)
> and the shared power-ups in the appendix are still future work.
> Companion to the existing renda fixa engine; reuses its architecture.

## Context

The renda fixa engine already does `sources → analysis → tracker(10s) →
opportunity engine → API/WS` with a `MarketContext`, fixtures fallback, and
`reasons`/`warnings`. The equities watcher follows the **same shape** but adds a
**two-stage** flow the user described:

1. **Fundamentals pick the company** (quality + value + intrinsic fair value).
2. **Price/timing picks the moment** — hold on a watchlist and only fire when
   the price enters the buy zone ("wait for the right moment to purchase").

### Locked decisions
- **Valuation philosophy:** Quality + Value + **Margin of Safety** (ensemble
  fair value).
- **Data tier:** all free + scraping (no paid keys).
- **Asset scope:** Brazilian **stocks (ações)** and **FIIs**.

## Data sources (free)

| Source | What | Notes |
|--------|------|-------|
| **brapi.dev** (free tier + token) | quotes, OHLCV history, dividends, BP/DRE/DFC, fundamental indicators, FIIs | primary; `fundamental=true&dividends=true` |
| **yfinance / Yahoo** (`TICKER.SA`) | history + **analyst target / consensus** (`targetMeanPrice`, `recommendationKey`) | rare free consensus signal; treat as one input |
| **Fundamentus / Status Invest** (scrape) | P/L, P/VP, ROE, ROIC, DY, margins, EV/EBITDA, net debt; FII P/VP, DY, vacância | via `pyfundamentus`/`fundamentus-api` patterns |
| **CVM Dados Abertos** (DFP/ITR) | authoritative balance sheet / income / cash flow (5y) | trust anchor; detect bad aggregator data |
| **XP / BTG research** (scrape per-ticker) | recommendation + target price + thesis text | personal use; `conteudos.xpi.com.br/acoes/<t>/`, `content.btgpactual.com/research/ativo/<t>` |
| **MarketContext** (existing) | Selic / Ibovespa regime | reused for the macro filter |

Every source gets a fixtures fallback so dev/tests run offline (same pattern as
`app/market/fixtures.py`).

## Architecture

New package `app/equities/` mirroring the bond side; **generalize the tracker**
to run multiple asset trackers on independent cadences (fundamentals refresh
daily; price/technical every 10s). Shared services (alerting, persistence,
`MarketContext`) are used by both.

```
app/equities/
  sources/        brapi.py, yfinance_src.py, fundamentus.py, cvm.py, research.py,
                  fixtures.py, base.py (EquitySource), __init__.py (factory)
  analysis/       quality.py, value.py, valuation.py (fair-value ensemble),
                  technical.py, timing.py (state machine), opportunity.py
  models.py       Stock, Fundamentals, Valuation, TechnicalSignals,
                  FiiMetrics, EquityOpportunity
  watchlist.py    persisted WATCH/ARMED/TRIGGERED state per ticker
app/tracker/      generalize to AssetTracker base + BondTracker + EquityTracker
app/api/          /equities/* routes
```

### Models (sketch)
- `Stock`: ticker, name, sector, asset_kind (STOCK|FII), price, market_cap,
  free_float, updated_at.
- `Fundamentals`: roe, roic, margins, net_debt_ebitda, current_ratio, dy,
  payout, fcf, 5y growth/consistency, shares_outstanding (dilution).
- `FiiMetrics`: p_vp, dy, vacancy, segment, n_assets, management_fee.
- `Valuation`: fair_value_low/mid/high, method_breakdown, margin_of_safety,
  buy_zone_price.
- `TechnicalSignals`: drawdown_52w, rsi, sma50/200, bollinger, support,
  volume_z, entry_score.
- `EquityOpportunity`: stock + fundamentals + valuation + technical +
  quality_score + value_score + entry_score + state + reasons + warnings.

## Stage 1 — Fundamental engine (which to own)

- **Quality score** (0–100): ROE/ROIC, gross/EBIT/net margins, net
  debt/EBITDA, current ratio, 5y earnings/revenue consistency & growth, FCF
  positivity, share-dilution check.
- **Value score** (0–100): P/L, P/VP, EV/EBITDA, DY, FCF yield — vs the stock's
  own history and sector peers.
- **Fair-value ensemble** (range, not a point):
  - Graham number; simple DCF (FCFE/owner-earnings); Gordon growth for dividend
    payers; **Bazin preço-teto** (dividend ÷ target DY); peer-multiple.
  - Aggregate → `fair_value_low/mid/high`; **MoS = (fair_mid − price)/fair_mid**.
- **FII track:** fair value from target-DY (`dividend ÷ target_dy`) and P/VP
  mean-reversion; quality from vacancy, segment diversification, P/VP vs
  history, management quality.
- **Red-flag gate** (mirrors the institution gate on bonds): excessive
  leverage, negative/erratic FCF, dilution, governance/auditor changes →
  disqualify or warn.

## Stage 2 — Timing engine (the right moment)

Per-ticker **state machine** persisted in `watchlist.py`:

```
WATCH ──(quality ok & MoS>req)──► ARMED ──(price in buy zone & technicals)──► TRIGGERED ─► alert
   ▲                                  │
   └──────(fundamentals degrade)──────┘
```

- **Buy zone:** `price ≤ fair_mid × (1 − required_MoS)`; `required_MoS`
  tightens when Selic is high (macro filter from `MarketContext`).
- **Entry signals (blended `entry_score`):** drawdown from 52w high, RSI
  oversold, price vs SMA50/200, Bollinger lower band, nearby support, volume
  spike / gap-down.
- The 10s `EquityTracker` only re-checks **ARMED** names against price every
  cycle (cheap); fundamentals refresh on the slow timer.

## Opportunity score & API

- `opportunity_score = f(quality, value, margin_of_safety) × entry_readiness`,
  with disqualifiers (red flags) and soft warnings (thin liquidity, stale
  fundamentals, target-price disagreement). Carries `reasons`/`warnings` like
  the bond side.
- **API:** `GET /equities/opportunities` (ranked, filters), `/equities/watchlist`
  (state machine), `/equities/{ticker}` (full fundamental + valuation +
  technical breakdown). Same WebSocket stream emits equity snapshots.

## Phases

1. Equity data layer (brapi + yfinance + Fundamentus) + fixtures fallback.
2. Fundamental + valuation engine (quality, value, fair-value ensemble, MoS) —
   stocks and FIIs.
3. Technical/timing engine + persisted state machine.
4. Generalized multi-asset tracker + `/equities/*` API.
5. Research scraping (XP/BTG) + analyst-target enrichment.
6. CVM DFP/ITR ingestion for authoritative fundamentals.

Each phase independently testable; app stays runnable on fixtures throughout.

## Verification approach
- Unit tests per module: quality/value scoring, each valuation method, MoS,
  technical indicators, state-machine transitions, FII metrics.
- Run `uvicorn` on fixtures and confirm `/equities/opportunities`,
  `/equities/watchlist`, `/equities/{ticker}`, and that an ARMED ticker flips to
  TRIGGERED when a fixture price drops into the buy zone.
- Live smoke (user machine): brapi/yfinance reachable; scrapers parse a few
  known tickers (PETR4, ITUB4, VALE3; a FII like HGLG11).

## Caveats / risks
- No free aggregated multi-broker target-price consensus exists; yfinance gives
  a partial Yahoo consensus, the rest is per-broker scraping — treat as one
  input, not gospel.
- Scraped research/fundamentals vary in quality and structure; CVM is the trust
  anchor. Respect each site's ToS (personal use).
- Backtests must avoid look-ahead/survivorship bias; this is a decision-support
  tool, **not investment advice**.

---

## Appendix — renda fixa power-ups (reused by both asset classes)

These were proposed alongside and are shared infrastructure:
1. **Alerting** on new cheap secondary offers / TRIGGERED stocks (push/webhook/
   Telegram) — biggest usefulness multiplier. **[implemented]** — `app/alerts/`
   with log + in-memory + webhook sinks, wired into both trackers and exposed at
   `/alerts`.
2. **Persistence + history** of curves, spreads, prices, opportunities →
   "cheaper than its 30-day norm", spread/price evolution, backtesting.
3. **Marcação-a-mercado on held bonds** → early-exit (sell) alerts.
4. **"Deploy R$X" allocator** → constrained allocation across opportunities
   respecting FGC caps + diversification.
5. **Copom-aware duration windows**; **live institution health** (BCB IF.data +
   news sentiment); **index-consistent IPCA cheapness**.
