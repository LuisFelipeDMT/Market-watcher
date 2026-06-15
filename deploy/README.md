# Deployment — two isolated zones (self-hosted, read-only)

This deploys the watcher as **two services on one box** so the untrusted
internet scraper has no path to the brokerage credentials. See
`docs/secure-delivery-plan.md` for the full rationale.

```
mw-collector (trusted)            mw-analysis (untrusted)
 holds creds, reads XP    ──►      opportunity/equities/alerts
 egress: XP/B3 only      signed    broad egress, behind VPN
 writes signed snapshots  files    reads snapshots (read-only)
```

## 1. Users & layout
```bash
sudo useradd --system --home /opt/market-watcher mw-collector
sudo useradd --system --home /opt/market-watcher mw-analysis
sudo install -d -o mw-collector -g mw-collector /opt/market-watcher/data/snapshots
sudo install -d -o mw-collector -g mw-collector /opt/market-watcher/run
```
Snapshots dir: writable by `mw-collector`, read-only for `mw-analysis`.

## 2. Two env files (never share secrets across the boundary)
- `.env.collector` — `OFFER_SOURCE=xp`, `SECRETS_PROVIDER=command`,
  `SESSION_CIPHER=fernet|command`, `SNAPSHOT_KEY=<shared>`, sealed-secret cmds.
- `.env.analysis` — **no `XP_*`, no secrets.** `COLLECTOR_TRANSPORT=snapshot`,
  `SNAPSHOT_DIR=/opt/market-watcher/data/snapshots`, `SNAPSHOT_KEY=<shared>`.

The only value both share is `SNAPSHOT_KEY` (HMAC integrity of the snapshots).

## 3. Sealing the password (no plaintext on disk)
TPM-bound with systemd-creds:
```bash
echo -n 'your-xp-password' | systemd-creds encrypt --name=xp_password - \
    /opt/market-watcher/secrets/xp_password.cred
# .env.collector:
#   SECRETS_PROVIDER=command
#   SECRETS_DECRYPT_CMD=systemd-creds decrypt --name={key} {dir}/{key}.cred -
#   SECRETS_SEALED_DIR=/opt/market-watcher/secrets
```
The TOTP seed is **not** sealed here — it stays on your phone (2FA approval).

## 4. Services
```bash
sudo cp deploy/systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now mw-collector mw-analysis
```
`collector.service` runs the snapshot producer; `analysis.service` runs the API
bound to localhost. Both are heavily sandboxed (see the unit files).

## 5. Egress allowlist (defence in depth)
Restrict the collector's outbound traffic to XP/B3 + DNS only:
```bash
sudo nft -f deploy/nftables.conf   # set COLLECTOR_UID and the resolved IPs first
```

## 6. Remote access to the dashboard
Keep the analysis API on `127.0.0.1` and reach it over a VPN
(Tailscale/WireGuard); enable `DASHBOARD_TOKEN` for app-level auth. Never expose
it directly to the internet.

## 7. Audit & updates
```bash
bash scripts/audit.sh        # pip-audit + committed-secret scan
```
Pin dependencies with hashes (`pip-compile --generate-hashes`) and patch
Chromium regularly (largest attack surface in the collector).
