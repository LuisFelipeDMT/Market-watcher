# Pending tasks

Granular checklist of what's **left**. Everything below is unchecked = not done.
Already built (for context): renda fixa engine, equities engine (stocks + FIIs),
alerting, secure-delivery phases 1–7 (mechanisms), mobile gateway, Android
scaffold. See the `docs/*-plan.md` files for design.

## 1. Live integrations (the two deferred seams)
- [ ] XP `_login()` selectors against the live site
- [ ] XP `fetch_offers()` — parse primary offers table
- [ ] XP `fetch_offers()` — parse secondary-market table (PU, taxa de compra, qty)
- [ ] XP `fetch_positions()` — parse holdings → `Portfolio`
- [ ] Measure XP session lifetime / re-2FA cadence (drives UX)
- [ ] Real 2FA push channel (replace the log notifier: ntfy / Telegram / FCM)
- [ ] `EQUITY_SOURCE=brapi` — verify live quotes/history mapping
- [ ] Verify live market data (BCB SGS/Focus, Tesouro, ANBIMA) end-to-end

## 2. Assisted purchase — write path (designed, not built)
- [ ] Order-intent model + signing (ticker, qty, price, total)
- [ ] Per-order confirmation UI showing exact ticker/qty/price/total
- [ ] Ephemeral-credential screen (password + token per order, never stored)
- [ ] Dedicated executor process (isolated, on-demand, own user)
- [ ] Spending limits (per-order + daily)
- [ ] Idempotency keys (never double-buy on retry)
- [ ] Order audit-log entry + push receipt
- [ ] XP order placement via the authenticated browser session
- [ ] Kill switch for the executor
- [ ] Test on tiny amounts before any real use

## 3. Persistence + history (power-up, fully testable here)
- [ ] Time-series store (prices, curves, spreads, opportunities)
- [ ] "Cheaper than its 30-day norm" signal
- [ ] Spread/price evolution history endpoints
- [ ] Backtesting harness for the cheapness/opportunity signal
- [ ] Marcação-a-mercado on holdings → sell / early-exit alerts

## 4. Other analysis power-ups
- [ ] "Deploy R$X" allocator (FGC caps + diversification constrained allocation)
- [ ] Copom-aware duration windows
- [ ] Live institution health (BCB IF.data + news sentiment)
- [ ] Index-consistent IPCA cheapness
- [ ] Equities phase 5–6: scrape XP/BTG research + analyst targets; CVM DFP/ITR

## 5. Android app (scaffold → shippable)
- [ ] Add Firebase `google-services.json` + enable FCM deps/plugin
- [ ] Implement `PushService` (onNewToken → register; onMessageReceived → notify)
- [ ] Register device on launch / token refresh (uses `AppSettings.deviceId`)
- [ ] Runtime `POST_NOTIFICATIONS` permission request
- [ ] Notification deep-link to the 2FA tab
- [ ] Loading / empty / error states across screens
- [ ] Pull-to-refresh + auto-refresh on the feed
- [ ] App theming, icon, name polish
- [ ] Biometric unlock (optional)
- [ ] Build + sign + sideload/distribute APK

## 6. Security / ops setup (host-specific, operator)
- [ ] Create `mw-collector` / `mw-analysis` users + dirs
- [ ] Seal XP password (`systemd-creds` / `age`); set `SECRETS_PROVIDER=command`
- [ ] Set shared `SNAPSHOT_KEY` on both zones
- [ ] `SESSION_CIPHER=fernet|command` (install `cryptography` or wire `age`)
- [ ] Install systemd units (`deploy/systemd/*`)
- [ ] nftables egress allowlist: resolve XP/B3 IPs + refresh timer
- [ ] VPN (Tailscale/WireGuard) + Caddy reverse proxy; set `DASHBOARD_TOKEN`
- [ ] Dependency hash-pinning (`pip-compile --generate-hashes`)
- [ ] `pip-audit` wired into CI (`scripts/audit.sh`)
- [ ] Chromium/Playwright patch cadence
- [ ] Scheduled encrypted backups (`scripts/backup.sh` via cron)

## 7. Pre-go-live verification
- [ ] Threat-model checklist sign-off
- [ ] Run on a funded-but-isolated / paper account first
- [ ] Confirm read-only by attempting (and failing) a write at the boundary

## 8. Repo / process
- [ ] Decide PR vs direct-to-master workflow (currently pushing to master)
- [ ] Optionally set `master` as the GitHub default branch
- [ ] Add `cryptography` to requirements if Fernet session cipher is adopted
