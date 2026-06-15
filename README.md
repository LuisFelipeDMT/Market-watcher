# Market Watcher

A backend service that tracks the **renda fixa (fixed income) offers available
on XP Brazil's platform** — primary shelf **and** the **mid-day secondary
market** — and continuously surfaces good buy-and-hold opportunities.

It refreshes offers on an interval (default **every 10 seconds**), pulls live
**reference data** (rates, yield curve, credit spreads, Focus expectations),
and scores every paper for **risk-adjusted net yield to maturity**,
**secondary-market cheapness**, **duration/macro risk**, and **FGC /
diversification fit** given your current holdings — then **highlights** the
ones worth buying, with a recommended position size.

> Status: working engine. Runs out of the box against a realistic **mock** feed
> + an offline reference-data snapshot. The **XP scraper** (offers + positions)
> is scaffolded and pluggable; the public reference feeds (BCB / Tesouro /
> ANBIMA) work live with automatic fallback to the snapshot.

---

## How it works

```
 offers (mock | xp) ─┐
 market data ────────┼─► tracker loop (10s) ─► engine v2 ─► API / WebSocket
 portfolio/positions ┘   refresh + broadcast   per-offer     /opportunities
                                                analytics     /opportunities/secondary
```

- **Sources** (`app/sources/`) — offers behind one interface
  (`fetch_offers`, `fetch_positions`): `mock` (primary + secondary + a demo
  portfolio, no creds) or `xp` (Playwright scraper scaffold).
- **Market data** (`app/market/`) — `MarketContext` from free public sources
  with per-component fallback to an offline snapshot: **BCB** SGS (CDI/Selic/
  IPCA) + Olinda Focus expectations, **Tesouro Direto** (risk-free curve),
  **ANBIMA** (credit spreads).
- **Portfolio** (`app/portfolio/`) — current holdings, FGC exposure **per
  conglomerate**, the R$1M/4y global cap, and non-FGC issuer/sector
  concentration; `sizing` recommends how much to buy.
- **Analysis** (`app/analysis/`)
  - `yields` — normalizes rates (% of CDI / IPCA+ / prefixado / SELIC+) to a
    comparable gross and **net YTM**, applying the regressive **IR** table
    (lower tax the longer you hold), **IOF** (<30 days), and tax exemptions.
  - `duration` — Macaulay/modified duration + DV01; post-fixed (CDI/SELIC)
    papers are treated as ~zero duration (they don't move with rates).
  - `cheapness` — offered YTM minus the **fair reference YTM** (risk-free curve
    + credit spread for the issuer's tier), in bps — the secondary edge.
  - `macro` — penalizes long-duration papers for rate/scenario risk, scaled by
    Focus rate-path uncertainty.
  - `credit` / `risk` — credit tiering and a 0–100 risk score (rating,
    institution health, product, maturity, **duration**, liquidity, FGC).
  - `opportunity` — engine v2 blending all of the above + position sizing.
- **Tracker** / **API** — refresh loop (offers every 10s, market data slower),
  newly-qualified detection, REST + WebSocket.

### What counts as an opportunity?

An offer is **highlighted** when **all** hold:

1. **No bad institution signs** — not under BACEN intervention, no adverse
   news/sentiment flag.
2. **Acceptable risk** — risk score ≤ 60.
3. **Attractive risk-adjusted score** ≥ `OPPORTUNITY_THRESHOLD` (default 70).
   The score = (reward from **net YTM vs CDI** + **secondary cheapness bonus**)
   × risk discount − **macro/duration penalty**.

Sizing/diversification problems (FGC cap reached, issuer/sector over-
concentration, paper "rich" vs reference) surface as **warnings**, not hard
cuts. Each opportunity carries `reasons`, `warnings`, and a `sizing`
recommendation.

---

## Financial mechanisms modelled

- **Secondary-market deságio** — papers resold under urgency / after marcação a
  mercado depreciation are flagged when their offered YTM beats the fair curve.
- **IR by holding length** — the regressive table (22.5%→15%) rewards longer
  buy-and-hold commitments; reflected directly in net YTM.
- **Duration & macro risk** — long-duration prefixado/IPCA papers are penalized
  for exposure to a change in the rate/inflation scenario; floaters aren't.
- **FGC limits** — exposure aggregated **per conglomerate** (≤ R$250k) and a
  global ≤ R$1M / 4y; sizing never recommends exceeding the remaining room.
- **Non-FGC diversification** — CRI/CRA/debentures get per-issuer and
  per-sector caps so a single default can't sink the portfolio.

> Note: MP 1.303 (which would have taxed LCI/LCA/CRI/CRA/incentivized
> debentures) was **rejected in Oct 2025**, so the exemptions and regressive IR
> table remain valid for 2026 — which is what the engine assumes.

---

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env        # defaults to the mock source — no credentials needed
uvicorn app.main:app --reload
```

Then:

```bash
curl localhost:8000/health
curl localhost:8000/opportunities/highlights      # the flagged opportunities
```

Open `http://localhost:8000/docs` for interactive API docs.

## API

| Method | Path                          | Description                                        |
|--------|-------------------------------|----------------------------------------------------|
| GET    | `/health`                     | Tracker status, offer + market source, errors      |
| GET    | `/offers`                     | Raw offers in the latest snapshot                  |
| GET    | `/opportunities`              | Evaluated + ranked offers (filters below)          |
| GET    | `/opportunities/highlights`   | Only the currently flagged opportunities           |
| GET    | `/opportunities/secondary`    | Secondary-market offers, ranked (the resale edge)  |
| GET    | `/market`                     | Reference data: rates, curve, spreads, Focus       |
| GET    | `/portfolio`                  | Current holdings used for FGC / sizing             |
| PUT    | `/portfolio`                  | Override holdings (recomputed next refresh)        |
| POST   | `/refresh`                    | Force an immediate refresh cycle                   |
| WS     | `/ws`                         | Live snapshot on every refresh cycle               |

`/opportunities` query params: `only_highlights` (bool), `min_score` (0–100),
`limit` (1–500). Each opportunity includes `net_ytm`, `cheapness_bps`,
`duration`, `macro_penalty`, `fgc_covered_now`, and `sizing`.

## Equities (renda variável: stocks + FIIs)

Alongside the renda fixa engine, a parallel **two-stage** watcher tracks
Brazilian stocks and FIIs (`app/equities/`): **fundamentals pick the company**
(quality + value + a margin-of-safety fair-value ensemble) and a **timing engine
picks the moment** — each name moves through a persisted state machine:

```
REJECTED ← red flag / low quality / unvaluable
WATCH    → good business, not cheap enough yet (wait for a lower price)
ARMED    → cheap enough on valuation, waiting for the technical entry
TRIGGERED→ in the buy zone AND timing says "now"  ← the buy alert
```

The fair value is an **ensemble** (Graham, Gordon dividend-discount, two-stage
DCF, peer-multiple; FIIs use dividend-yield and price-to-NAV anchors). The
required margin of safety tightens as Selic rises (shared `MarketContext`). The
timing score blends drawdown from the 52w high, RSI(14), moving-average position
and proximity to support.

| Method | Path                          | Description                                   |
|--------|-------------------------------|-----------------------------------------------|
| GET    | `/equities/health`            | Tracker status + per-state counts             |
| GET    | `/equities/opportunities`     | Ranked universe (`state`, `kind`, `min_score`)|
| GET    | `/equities/triggered`         | The "buy now" list (TRIGGERED only)           |
| GET    | `/equities/watchlist`         | WATCH + ARMED + TRIGGERED names                |
| GET    | `/equities/{ticker}`          | Full fundamental + valuation + technical view  |
| POST   | `/equities/refresh`           | Force an immediate equity refresh cycle        |
| WS     | `/equities/ws`                | Live equity snapshot on every refresh cycle    |

Default `EQUITY_SOURCE=fixtures` ships an offline universe so the engine runs
without network access; `EQUITY_SOURCE=brapi` overlays live brapi.dev quotes and
falls back to fixtures per-ticker. Design notes: `docs/equities-watcher-plan.md`.

## Configuration

All settings come from environment variables / `.env` (see `.env.example`).
Key ones:

| Variable                    | Default | Purpose                                    |
|-----------------------------|---------|--------------------------------------------|
| `OFFER_SOURCE`              | `mock`  | `mock` or `xp`                             |
| `EQUITY_SOURCE`             | `fixtures` | `fixtures` or `brapi` (equity universe)  |
| `STOCK_BASE_MOS` / `FII_BASE_MOS` | `0.15` / `0.08` | Base margin of safety demanded    |
| `EQUITY_QUALITY_MIN` / `EQUITY_ENTRY_MIN` | `55` / `50` | Pipeline stage gates       |
| `MARKET_SOURCE`             | `auto`  | `auto` / `live` / `fixtures` reference data |
| `REFRESH_INTERVAL_SECONDS`  | `10`    | Offer refresh cadence                      |
| `MARKET_REFRESH_SECONDS`    | `300`   | Reference-data refresh cadence             |
| `OPPORTUNITY_THRESHOLD`     | `70`    | Min opportunity score to highlight         |
| `MIN_CHEAPNESS_BPS`         | `30`    | Secondary cheapness threshold              |
| `MACRO_PENALTY_WEIGHT`      | `1.0`   | Long-duration penalty strength             |
| `FGC_PER_INSTITUTION` / `FGC_GLOBAL_4Y` | `250000` / `1000000` | FGC caps (BRL) |
| `MAX_ISSUER_CONCENTRATION` / `MAX_SECTOR_CONCENTRATION` | `0.05` / `0.20` | Non-FGC diversification caps |
| `CDI_ANNUAL` / `SELIC_ANNUAL` / `IPCA_ANNUAL` | — | Fallback benchmark rates |
| `XP_USERNAME` / `XP_PASSWORD` / `XP_CPF` / `XP_TOTP_SECRET` | — | XP scraper credentials |

## Reference data (free public sources)

`MARKET_SOURCE=auto` fetches each piece independently and falls back to the
offline snapshot (`app/market/fixtures.py`) for anything unreachable:

- **BCB SGS** — CDI/Selic/IPCA (`api.bcb.gov.br`).
- **BCB Olinda** — Focus expectations → macro uncertainty.
- **Tesouro Direto** — prefixado prices → risk-free curve.
- **ANBIMA** — secondary debenture taxas → credit-spread tiers.

A browser-like User-Agent is sent to avoid 403s from these endpoints.

## Going live with the XP source

XP Brazil exposes **no public API** for its renda fixa shelf, so the `xp`
source drives a headless browser (Playwright) against the site using your own
investor login.

```bash
pip install playwright && playwright install chromium
# set OFFER_SOURCE=xp and the XP_* credentials in .env
```

`app/sources/xp_scraper.py` has the structure in place; complete against the
live site (selectors require an authenticated session and change over time):

- `_login()` — fill the login form, handle the CPF step and TOTP/2FA.
- `fetch_offers()` — parse the primary **and** secondary offers tables.
- `fetch_positions()` — parse current holdings into a `Portfolio`.

Please respect XP's Terms of Service: only read data your own account can
already see, and keep the refresh interval reasonable.

## Tests

```bash
pytest
```

Covers yield normalization (IR/IOF), risk + duration scoring, cheapness,
opportunity detection, FGC room + non-FGC sizing, the tracker refresh loop, and
an API smoke test.

## Roadmap

- Complete the XP scraper selectors + session handling (offers + positions).
- A real news-sentiment / ratings feed for `institution` and ANBIMA credit
  curves for sharper per-tier spreads.
- Index-consistent (real vs nominal) cheapness for IPCA papers.
- Persistence + history so opportunities and curves can be tracked over time.
- Alerting (push/webhook/email) when a new cheap secondary opportunity appears.
- A web dashboard on top of the existing WebSocket feed.
