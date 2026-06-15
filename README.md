# Market Watcher

A backend service that tracks the **renda fixa (fixed income) offers available
on XP Brazil's platform** and continuously surfaces good opportunities.

It refreshes the offer shelf on an interval (default **every 10 seconds**),
scores every paper for **risk** and **risk-adjusted yield**, screens out
issuers with **bad market-analysis signs**, and **highlights** the offers that
qualify as opportunities — exposed over a REST API and a live WebSocket feed.

> Status: working foundation. Runs out of the box against a realistic **mock**
> offer feed. The **XP web scraper** is scaffolded and pluggable — wire in your
> credentials and the page selectors to go live.

---

## How it works

```
 source (mock | xp)  ──►  tracker loop (every 10s)  ──►  analysis  ──►  API / WebSocket
   fetch_offers()            refresh + broadcast          risk + yield      /opportunities
                                                          + opportunity      /ws (live)
```

- **Sources** (`app/sources/`) — pluggable offer providers behind one
  interface (`OfferSource.fetch_offers`).
  - `mock` — a lifelike, slightly-fluctuating universe of papers (no creds).
  - `xp` — Playwright scraper of the XP web platform (scaffold; see below).
- **Analysis** (`app/analysis/`)
  - `yields` — normalizes heterogeneous rates (% of CDI, IPCA+ spread,
    prefixado, SELIC+) into a comparable **gross** and **net (after-IR)**
    annual yield, applying Brazil's regressive income-tax table and tax
    exemptions (LCI/LCA/CRI/CRA/incentivized debentures).
  - `risk` — a 0–100 **risk score** from issuer rating, institution health,
    product type, maturity, liquidity, and FGC coverage.
  - `institution` — market-analysis signals per issuer (rating, Basel index,
    BACEN intervention, adverse-news flag). The *"no bad signs"* gate.
  - `opportunity` — blends reward (net yield vs CDI) with risk into an
    **opportunity score**, disqualifies offers with bad institution signs or
    excessive risk, and ranks the rest.
- **Tracker** (`app/tracker/`) — the background refresh loop that keeps the
  latest snapshot, detects **newly-qualified** opportunities, and broadcasts to
  WebSocket subscribers.
- **API** (`app/api/`) — FastAPI REST + WebSocket endpoints.

### What counts as an opportunity?

An offer is **highlighted** when **all** hold:

1. **No bad institution signs** — not under BACEN intervention, no adverse
   news/sentiment flag.
2. **Acceptable risk** — risk score ≤ 60.
3. **Attractive risk-adjusted yield** — opportunity score ≥
   `OPPORTUNITY_THRESHOLD` (default 70), where the score rewards net yield
   relative to CDI and is discounted by the risk score.

Each opportunity carries human-readable `reasons` explaining the verdict.

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
| GET    | `/health`                     | Tracker status, source, refresh count, errors      |
| GET    | `/offers`                     | Raw offers in the latest snapshot                  |
| GET    | `/opportunities`              | Evaluated + ranked offers (filters below)          |
| GET    | `/opportunities/highlights`   | Only the currently flagged opportunities           |
| POST   | `/refresh`                    | Force an immediate refresh cycle                   |
| WS     | `/ws`                         | Live snapshot on every refresh cycle               |

`/opportunities` query params: `only_highlights` (bool), `min_score` (0–100),
`limit` (1–500).

## Configuration

All settings come from environment variables / `.env` (see `.env.example`).
Key ones:

| Variable                    | Default | Purpose                                    |
|-----------------------------|---------|--------------------------------------------|
| `OFFER_SOURCE`              | `mock`  | `mock` or `xp`                             |
| `REFRESH_INTERVAL_SECONDS`  | `10`    | Tracker refresh cadence                    |
| `OPPORTUNITY_THRESHOLD`     | `70`    | Min opportunity score to highlight         |
| `CDI_ANNUAL` / `SELIC_ANNUAL` / `IPCA_ANNUAL` | — | Benchmark rates used to normalize yields |
| `XP_USERNAME` / `XP_PASSWORD` / `XP_CPF` / `XP_TOTP_SECRET` | — | XP scraper credentials |

> The benchmark rates are currently static assumptions. Wiring them to a live
> feed is a natural next step so net-yield comparisons stay accurate.

## Going live with the XP source

XP Brazil exposes **no public API** for its renda fixa shelf, so the `xp`
source drives a headless browser (Playwright) against the site using your own
investor login.

```bash
pip install playwright && playwright install chromium
# set OFFER_SOURCE=xp and the XP_* credentials in .env
```

`app/sources/xp_scraper.py` has the structure in place; two methods need to be
completed against the live site (the selectors require an authenticated session
to inspect and change over time):

- `_login()` — fill the login form, handle the CPF step and TOTP/2FA.
- `fetch_offers()` — parse the offers table into `Offer` records.

Please respect XP's Terms of Service: only read data your own account can
already see, and keep the refresh interval reasonable.

## Tests

```bash
pytest
```

Covers yield normalization, risk scoring, opportunity detection, the tracker
refresh loop (incl. new-opportunity detection), and an API smoke test.

## Roadmap

- Complete the XP scraper selectors + session handling.
- Live benchmark rates (CDI/SELIC/IPCA) and a real news-sentiment / ratings
  feed for `institution`.
- Persistence + history so opportunities can be tracked over time.
- Alerting (push/webhook/email) when a new opportunity is highlighted.
- A web dashboard on top of the existing WebSocket feed.
```
