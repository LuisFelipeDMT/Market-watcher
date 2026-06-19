# Pending tasks

Split by what we can do **now** (build + test in this repo, no live XP) vs what
is **blocked** on live access / external credentials / the target host.
All boxes unchecked = not done. See `docs/*-plan.md` for design.

---

# ✅ Executable now (no live XP needed)

## Persistence + history (fully testable on fixtures/mock)
- [x] Time-series store (prices, curves, spreads, opportunities)
- [x] "Cheaper than its 30-day norm" signal
- [x] Spread/price evolution history endpoints
- [x] Backtesting harness for the cheapness/opportunity signal
- [x] Marcação-a-mercado on the mock portfolio → sell / early-exit alerts

## Analysis power-ups (fixtures-based; live feeds verified later)
- [x] "Deploy R$X" allocator (FGC caps + diversification)
- [x] Copom-aware duration windows (uses Focus data already in MarketContext)
- [x] Index-consistent IPCA cheapness (breakeven inflation vs comparable prefixado)
- [x] Institution-health framework + scoring (static/fixtures registry now)

## Assisted-purchase machinery (everything except the real order step)
- [x] Order-intent model + signing (ticker, qty, price, total)
- [x] Spending limits (per-order + daily) + tests
- [x] Idempotency keys (never double-buy) + tests
- [x] Executor skeleton behind a `MockExecutor` (simulated fills) + tests
- [x] Kill switch + state machine (armed/confirmed/executed/aborted)
- [x] Order audit entries + push receipt (reuse audit + push layers)
- [x] Ephemeral-credential handling (in-memory only, never persisted) + tests

## Push / 2FA delivery adapters (mocked-HTTP tests; real creds verified later)
- [x] `ntfy` notifier (self-hostable) for 2FA + alerts
- [x] Telegram bot notifier for 2FA + alerts
- [x] Wire the chosen notifier into the 2FA broker (replace the log notifier)
- [x] FCM sender path covered by mocked tests

## Data parsing hardening (recorded payloads, no live calls)
- [x] brapi response mapping tests against saved sample payloads
- [x] Equities research/CVM model + parser scaffolding (against saved samples)

## Android client (write now; compile/test off-sandbox in Android Studio)
- [x] Loading / empty / error states across screens
- [x] Pull-to-refresh + auto-refresh on the feed (auto-refresh + manual button)
- [ ] Notification deep-link to the 2FA tab (UI side)
- [ ] App theming, icon, name
- [ ] Biometric unlock (optional)
- [ ] `PushService` implementation (registration + notify) — code, not verified here

## Repo / process
- [x] `pip-audit` run + wire into CI (`scripts/audit.sh`) — 0 vulns after upgrades
- [x] Dependency hash-pinning (`requirements.lock` with hashes)
- [x] Add `cryptography` to requirements if Fernet session cipher is adopted

---

# ⛔ Pending live integration (blocked)

## Needs a live XP session
- [ ] XP `_login()` selectors against the live site
- [ ] XP `fetch_offers()` — primary offers table
- [ ] XP `fetch_offers()` — secondary table (PU, taxa de compra, qty)
- [ ] XP `fetch_positions()` → `Portfolio`
- [ ] Measure XP session lifetime / re-2FA cadence
- [ ] Real XP order placement (the executor's actual buy step)
- [ ] Test the full buy flow on tiny amounts / paper account
- [ ] Confirm read-only by attempting (and failing) a write at the boundary

## Needs external credentials / network to verify
- [ ] `EQUITY_SOURCE=brapi` live verification
- [ ] Live BCB SGS/Focus, Tesouro, ANBIMA end-to-end verification
- [ ] Real push delivery verification (FCM key / Telegram token / ntfy)
- [ ] Firebase `google-services.json` for the Android app
- [ ] Live XP/BTG research scrape + CVM DFP/ITR ingestion
- [ ] Live institution health feeds (BCB IF.data + news sentiment)

## Needs the target host (ops setup)
- [ ] Create `mw-collector` / `mw-analysis` users + dirs
- [ ] Seal XP password (`systemd-creds` / `age`); `SECRETS_PROVIDER=command`
- [ ] Shared `SNAPSHOT_KEY` on both zones; `SESSION_CIPHER=fernet|command`
- [ ] Install systemd units (`deploy/systemd/*`)
- [ ] nftables egress allowlist: resolve XP/B3 IPs + refresh timer
- [ ] VPN (Tailscale/WireGuard) + Caddy reverse proxy; set `DASHBOARD_TOKEN`
- [ ] Scheduled encrypted backups (cron) + Chromium patch cadence
- [ ] Android: build + sign + sideload/distribute APK

## Needs your decision
- [ ] PR vs direct-to-master workflow
- [ ] Optionally set `master` as the GitHub default branch
- [ ] Threat-model checklist sign-off before go-live
