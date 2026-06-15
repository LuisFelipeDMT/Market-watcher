# Runbooks — operating the read-only watcher safely

Companion to `docs/secure-delivery-plan.md`. Single-user, self-hosted, read-only.

## Monitoring (what "healthy" looks like)
- `GET /health`, `GET /equities/health`, `GET /alerts/health` on the analysis
  service return `status: ok` and a recent `updated_at`.
- Collector audit trail (`data/audit.log`) shows periodic activity and no
  unexpected `2fa_requested` events (a prompt you didn't trigger = investigate).
- Security alerts (`AlertKind.SECURITY`) surface login failures / new-device
  prompts / egress denials through the same alert channels.

## Credential rotation (do this on any suspicion, and on a schedule)
1. Change the XP password in the XP app/site.
2. Re-seal it on the host:
   ```bash
   echo -n 'NEW-PASSWORD' | systemd-creds encrypt --name=xp_password - \
       /opt/market-watcher/secrets/xp_password.cred
   ```
3. Invalidate the cached session and restart the collector:
   ```bash
   rm -f /opt/market-watcher/data/xp_session.enc
   sudo systemctl restart mw-collector
   ```
4. Rotate `SNAPSHOT_KEY` (and `COLLECTOR_TOKEN` if using http) on **both** env
   files together, then restart both services.
5. Rotating the TOTP: re-enroll the authenticator on your **phone** only — the
   seed never exists on the host, so nothing to change there.

## Incident response (suspected compromise)
1. **Kill switch:** `sudo systemctl stop mw-collector mw-analysis`.
2. From a trusted device, change the XP password and revoke active sessions in
   the XP app; re-enroll 2FA.
3. Preserve `data/audit.log` and system logs; review for unexpected logins,
   2FA requests, or egress-allowlist denials.
4. Rebuild the host from a known-good image before bringing services back
   (the collector runs headless Chromium — assume the box, not just the app).
5. Re-seal secrets and rotate `SNAPSHOT_KEY`/tokens before restart.

Because access is **read-only**, the worst direct outcome is disclosure of your
positions plus the need to rotate the password — there is no transaction path.

## Backups (encrypted)
Back up only what you can't recreate: sealed secrets and config. Snapshots and
the watchlist are derived and can be regenerated.
```bash
bash scripts/backup.sh /opt/market-watcher /secure/backups   # age-encrypted
```
Restore: `age -d -i <key> backup.age | tar -x -C /`.

## Updates
- `bash scripts/audit.sh` regularly (pip-audit + committed-secret scan).
- Patch Chromium/Playwright promptly — the collector's largest attack surface.
- Keep dependencies hash-pinned (`pip-compile --generate-hashes`).
