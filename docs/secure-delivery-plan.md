# Plan: Secure delivery — live data with brokerage access

> Status: **plan only.** Architecture/security design for going live against a
> real XP account. No secure-backend code written yet.

## Locked decisions
- **Access scope:** **read-only** — reads positions, balances and the offer
  shelf; never moves money or places orders.
- **Tenancy:** **single-user, self-hosted** — runs on infrastructure you
  control, only your credentials.
- **Credential model:** **stored encrypted credentials, unattended** — the
  service logs into XP 24/7 by itself.

## The core problem

"Unattended + stored credentials" means a box holds your XP **password and TOTP
seed** and keeps a live session. That is the crown jewel. Separately, the
watcher must ingest the **untrusted internet** (research sites, brapi, ANBIMA,
BCB, headless-browser scraping) — exactly the surface most likely to be
compromised (parser bugs, malicious pages, SSRF, dependency supply-chain).

> **Design principle:** the component that can ingest untrusted data must have
> **no path** to the bank credentials. A compromise of the scraper/analysis
> side must not be able to read the password, the TOTP seed, or the live
> session. This is the user's instinct, made concrete below.

### Why not a browser extension
A browser extension/session-capture avoids storing the password, but (a) needs
constant manual re-auth (the UX cost you flagged), and (b) runs the
account-reading code inside the browser — the same process exposed to web
content. Rejected in favour of an isolated backend collector. (Session-capture
stays a possible future fallback if unattended login proves fragile.)

## Architecture: two isolated trust zones

```
        ┌─────────────────────── TRUSTED ZONE ───────────────────────┐
        │  Collector / Vault service  (own OS user, sandboxed)        │
        │  • holds encrypted XP creds (sealed to this host)           │
        │  • Playwright login + session, reads positions/offers       │
        │  • EGRESS ALLOWLIST: *.xpi.com.br / B3 only                 │
        │  • NO untrusted parsing, NO LLM, NO third-party scraping    │
        │  • exposes ONLY a read API (typed, sanitized models)        │
        └───────────────▲─────────────────────────────────────────────┘
                        │  one-way: sanitized Offer/Portfolio snapshots
                        │  (unix socket + token, or signed snapshot files)
        ┌───────────────┴─────────────────── UNTRUSTED ZONE ─────────┐
        │  Analysis / Watcher service  (own OS user, sandboxed)       │
        │  • the current FastAPI app: opportunity + equities + alerts │
        │  • market data + research scraping (broad internet egress)  │
        │  • NO bank credentials, CANNOT log into XP                  │
        │  • dashboard/API behind auth + VPN                          │
        └─────────────────────────────────────────────────────────────┘
```

- **Data flows one way, A → B**, as validated Pydantic models (`Offer`,
  `Portfolio`) — never raw HTML. The collector exposes **no** endpoint that
  accepts account-affecting commands (it's structurally read-only).
- **Preferred transport:** a Unix domain socket on the same host with a bearer
  token + strict request allowlist; or, for the strongest isolation, A writes
  **signed snapshot files** to a drop directory that B reads (no inbound to A at
  all — a software "data diode"). mTLS if A and B are on different hosts.

## Secrets at rest (the hardest part of "unattended")

Unattended login means the decryption key must be reachable at runtime — so it
must be bound to *this host*, not a plaintext file:
- **Recommended:** seal credentials to the TPM via `systemd-creds encrypt`
  (TPM2) or `age`/`sops` with a TPM/host key. The box auto-decrypts only on that
  hardware; the key never lives as a readable file.
- Decrypt into **locked memory** (`mlock`), never to disk, never to logs;
  disable core dumps; scrub on shutdown.
- Generate the TOTP code on demand from the sealed seed **inside A only**.
- Credentials and seeds **never** in the repo, `.env` (committed), or B's config.

> **Residual risk (state it plainly):** storing the TOTP seed collapses 2FA to a
> single factor on one machine. Sealing it to the TPM + isolating A mitigates
> but does not eliminate this. If XP supports a hardware security key, true
> unattended automation becomes impossible — an honest trade-off to revisit.

## Hardening

**Collector (A) — minimize blast radius:**
- Dedicated low-privilege OS user; systemd sandbox: `ProtectSystem=strict`,
  `ProtectHome`, `PrivateTmp`, `NoNewPrivileges`, `MemoryDenyWriteExecute`,
  empty `CapabilityBoundingSet`, `SystemCallFilter`, `RestrictAddressFamilies`.
- **Outbound firewall allowlist** (nftables) to XP/B3 only — if A is popped it
  still can't exfiltrate to an attacker host.
- Run headless Chromium in its own ephemeral sandbox/container (big surface,
  patch aggressively).
- No inbound except the single read interface; bound to localhost/unix socket.

**Analysis (B) — assume it will be attacked:**
- Broad egress but **zero secrets**. Treat all scraped data as hostile: hardened
  parsers, size/time limits, no `eval`. **SSRF guards** (validate URLs, block
  private/loopback/link-local ranges, no redirects into internal nets).
- Own OS user/container; dashboard bound to localhost or behind VPN
  (Tailscale/WireGuard) + authentication + TLS. Never publicly exposed.

**Both:**
- Dependency pinning with hashes (`uv`/`pip-tools` + `--require-hashes`);
  A keeps a **minimal** dependency set (ideally it doesn't import the analysis
  libraries at all). `pip-audit` + Dependabot in CI; secret scanning.
- Financial data at rest (positions, history) encrypted, strict file perms,
  minimal retention.

## Delivery phases (each independently shippable, no behaviour regressions)

1. **Code split (no creds yet).** Carve the repo into two deployables:
   `collector` (XP scraper + `fetch_positions`) and `analysis` (everything
   else). Define the shared read-only data contract; analysis consumes it via
   an injected client (today: in-process; later: socket/files).
2. **Sealed secrets.** Encrypted credential store (TPM-sealed); remove plaintext
   creds from `.env`; load via the sealed store with `mlock` + log scrubbing.
3. **Collector service.** Move XP login/session/reads behind A's read-only
   interface (unix socket + token / signed snapshot files); egress allowlist.
4. **Analysis consumes A.** B fetches positions/offers from A's interface; strip
   all `XP_*` config from B. Verify B has no code path to credentials.
5. **Hardening.** systemd sandbox units / container profiles, firewall rules,
   SSRF guards on the scrapers, dependency hash-pinning + `pip-audit`.
6. **Observability + runbooks.** Audit log of A's actions (no secrets);
   **reuse the alerting layer** for security signals (login failures, new-device
   prompts, egress-allowlist denials); encrypted backups; credential-rotation
   and incident-response runbooks (kill switch).
7. **Remote access (optional).** VPN + authn in front of B's dashboard only.

## Mapping to the current codebase
- **Becomes Collector (A):** `app/sources/xp_scraper.py`, `fetch_positions`, and
  all `XP_*` settings — the only credential-bearing code today.
- **Stays Analysis (B):** opportunity + equities + alerts engines, market data
  (`app/market/*`), brapi/research scraping — broad internet, no secrets.
- **Reused as-is:** the `app/alerts/` layer becomes the security-alert channel;
  the source/provider factory pattern already lets B swap an in-process source
  for a "remote collector client" with no engine changes.

## Verification (safety is the acceptance criterion)
- Threat-model checklist signed off before go-live.
- CI: secret scanning, `pip-audit`, and a test asserting **B has no import/config
  path to credentials**.
- Negative tests: B cannot invoke any account-affecting op on A; A rejects
  non-allowlisted egress; SSRF guards block private-range URLs.
- Pre-go-live: run on a **funded-but-isolated** account or paper first; confirm
  read-only by attempting (and failing) a write at the collector boundary.
- This is decision-support tooling with **read-only** brokerage access — **not**
  an order-execution system and not investment advice.
