# Plan: Secure delivery — live data with brokerage access

> Status: **plan only.** Architecture/security design for going live against a
> real XP account. No secure-backend code written yet.

## Locked decisions
- **Access scope:** **read-only** — reads positions, balances and the offer
  shelf; never moves money or places orders.
- **Tenancy:** **single-user, self-hosted** — runs on infrastructure you
  control, only your credentials.
- **Credential model:** **password stored (sealed); 2FA via phone push.** The
  service stores only the password and runs unattended *between* logins; when XP
  requires a second factor it pushes an approval request to a phone app that
  holds the seed and relays the code back. The second factor never sits on the
  server.

## The core problem

An always-on box holds your XP **password** and a **live session**. That is the
crown jewel (the TOTP seed stays on your phone — see below). Separately, the
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

## Secrets at rest + the phone-push 2FA flow

Only the **password** is stored; the decryption key must be reachable at runtime,
so it is bound to *this host*, not a plaintext file:
- **Recommended:** seal the password to the TPM via `systemd-creds encrypt`
  (TPM2) or `age`/`sops` with a TPM/host key. The box auto-decrypts only on that
  hardware; the key never lives as a readable file.
- Decrypt into **locked memory** (`mlock`), never to disk, never to logs;
  disable core dumps; scrub on shutdown.
- The **TOTP seed never touches the server** — it lives only in the phone app's
  secure enclave. The password and key **never** appear in the repo, committed
  `.env`, or B's config.

**Second factor via phone push (attended only at login):**
```
Collector hits XP 2FA step
  → signed approval request pushed to the phone app (with time/trigger context)
  → user approves; app holds the seed, generates the code, returns it
  → Collector submits the code, caches the session securely, resumes unattended
```
- **Authenticate the reply, not just the push:** the approve+code must come back
  over mTLS or a signed/single-use challenge so it can't be forged or replayed;
  show *why/when/from where* to defeat approval-fatigue.
- **Maximize session reuse:** persist the session cookie (sealed, same as the
  password) and refresh gracefully, so re-2FA prompts are rare. First discovery
  task: measure XP's real session lifetime / re-challenge cadence.
- **Push channel, build-cost-ordered:** start by reusing a secure channel — ntfy
  (self-hosted), a Telegram bot, or Pushover — riding on the existing
  `app/alerts/` layer as an authenticated two-way sink; build a bespoke
  FCM/APNs app only if the polish is wanted.

> **Residual risk (state it plainly):** the password still lives on the box, so a
> host compromise means rotating it; but a fresh XP login also requires the
> phone, so the second factor is genuinely separate — a materially stronger
> posture than storing the seed. Approval-fatigue is the main human risk;
> mitigate with rich context and single-use, time-boxed approvals.

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

1. **Code split (no creds yet). [implemented]** Carved the repo into two zones:
   `app/collector/` (the `Collector` producers — mock + XP scraper — plus
   `fetch_positions`) and the analysis engine (everything else). The engine
   depends only on the `CollectorClient` interface, today satisfied by
   `InProcessCollectorClient` and later by a socket/snapshot-file remote client
   with no engine change. A test drives the tracker via a fake remote client to
   lock the seam.
2. **Sealed secrets. [implemented]** Pluggable secrets provider
   (`app/collector/secrets.py`): env (dev), `command` (TPM/age-sealed via
   `systemd-creds`/`age`), memory (tests); `SecretStr` + log redaction +
   best-effort `mlock`; password sourced from the provider (plaintext `.env`
   kept only as a warned dev fallback); the TOTP seed never touches the host.
   Encrypted session cache (`app/collector/session.py`) with pluggable cipher
   (none/fernet/command) and 0600 perms so re-logins/2FA prompts stay rare.
   *Operator setup* (TPM/age keys, sealing the blobs) is host-specific and
   documented in `.env.example`.
3. **Collector service. [implemented]** Standalone collector
   (`app/collector/server.py`, run-as-its-own-process) exposes read-only
   GET-only endpoints behind a bearer token over a Unix socket; the safer
   data-diode transport is signed snapshot files (`app/collector/snapshot.py`
   + `producer.py`). The analysis zone consumes either via
   `RemoteHttpCollectorClient` / `SnapshotFileCollectorClient`
   (`app/collector/remote.py`), selected by `COLLECTOR_TRANSPORT`. The
   **phone-push 2FA broker** (`app/collector/twofa.py`) issues time-boxed,
   single-use approval requests with a pluggable push notifier and an
   authenticated `/2fa/{id}/approve` return channel; encrypted session reuse
   keeps prompts rare. *Real push channel + XP selectors are integration-later.*
4. **Analysis consumes A. [implemented]** With `COLLECTOR_TRANSPORT=snapshot|http`
   the analysis service reaches the brokerage only through the remote client and
   needs **no** `XP_*` / secrets config. `tests/test_isolation.py` enforces it:
   importing the remote clients pulls in neither the secrets module nor the
   producer (checked in a clean subprocess), and a static scan asserts the
   analysis packages contain no credential references.
5. **Hardening. [implemented]** SSRF guard (`app/security/ssrf.py`, wired into
   the brapi fetch) blocks non-HTTP schemes and hosts resolving to
   private/loopback/link-local/metadata ranges. `deploy/` ships hardened systemd
   units for both zones, an nftables egress allowlist for the collector, a
   two-zone deployment guide, and `scripts/audit.sh` (pip-audit + committed-
   secret scan; hash-pinning documented).
6. **Observability + runbooks.** Audit log of A's actions (no secrets);
   **reuse the alerting layer** for security signals (login failures, new-device
   prompts, egress-allowlist denials); encrypted backups; credential-rotation
   and incident-response runbooks (kill switch).
7. **Remote access (optional).** VPN + authn in front of B's dashboard only.

## Mapping to the current codebase
- **Collector (A) [done in Phase 1]:** `app/collector/` —
  `sources/xp_scraper.py`, `fetch_positions`, and all `XP_*` settings — the only
  credential-bearing code; reached only via the `CollectorClient` boundary.
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
