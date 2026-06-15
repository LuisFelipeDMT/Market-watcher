# Plan: Consumption — phone app, push, 2FA, assisted purchase

> Status: **viewer + push + 2FA gateway implemented (backend); Android client
> scaffolded.** The assisted-purchase (write) path is **designed, not built**.

## Decisions
- **App:** native Android (Kotlin + Compose). Scaffold in `android/`.
- **Monitoring creds:** keep the TPM-sealed password; you tap your phone only
  for the occasional 2FA re-login.
- **Build order:** viewer + push + 2FA approval first (manual buy); assisted
  purchase later.

## The phone app's three jobs
1. **Proposal viewer** — one ranked feed (renda fixa flagged + equities
   TRIGGERED) with the decision context. You buy manually in XP for now.
2. **Push** — registers an FCM token; receives alerts (opportunities, TRIGGERED,
   2FA, security) as notifications.
3. **2FA approval** — lists pending login requests and relays the code.

## Backend gateway (implemented, in the analysis zone)
`app/mobile/` + `/mobile/*`, all behind `DASHBOARD_TOKEN`:
- `GET /mobile/proposals` / `/{id}` — unified `Proposal` feed.
- `POST|GET|DELETE /mobile/devices` — FCM device registry; `PushAlertSink`
  fans every alert out to registered phones.
- `GET /mobile/2fa/pending`, `POST /mobile/2fa/{id}/approve|deny` — forwarded to
  the collector's authenticated 2FA endpoints by a `TwoFactorGateway`
  (in-process for dev; HTTP forwarder for the split deployment).

The app holds only the **dashboard token** — never the collector token or the XP
password. It talks solely to the analysis gateway; the gateway forwards
approvals to the collector, preserving the trust boundary.

## Two credential models (recap)
| | Monitoring (read) | Buying (write, future) |
|---|---|---|
| Password | TPM-sealed, unattended | typed per order, never stored |
| 2FA token | occasional phone approval | typed per order |
| Runs while away? | yes | no — only on your explicit tap |

## Assisted purchase — design (NOT built; write access)

Buying is **write access**, deliberately scoped out until now. The ephemeral
model is the safe way in. Proposed design when we build it:

1. **Explicit initiation only.** You tap "buy" on a specific proposal in the
   app; nothing is ever auto-initiated.
2. **Dedicated executor**, separate from the read collector and even more
   locked down (its own process/user, on-demand, no long-running session).
3. **Ephemeral credentials.** The order screen collects the XP password + 2FA
   token *for that one order*; they are used once and discarded (held only in
   locked memory, never sealed to disk, never logged).
4. **Per-order confirmation.** A signed order intent shows exact
   ticker/quantity/price/total; you confirm; the executor places exactly that.
5. **Guardrails.** Per-order and daily **spending limits**; **idempotency keys**
   so a retry can never double-buy; full audit-log entry; immediate push receipt.
6. **Mechanism.** XP has no order API, so execution drives the authenticated
   browser session — fragile and ToS-sensitive; build carefully, test on tiny
   amounts, and keep a kill switch.

Phasing: (a) **order intent + confirmation UI returning a manual checklist**
(still no automation); (b) executor behind the ephemeral-credential screen with
limits + idempotency; (c) only then consider any "approve and it buys" comfort.

## Native app (scaffold, `android/`)
Compose screens (Proposals, 2FA), Retrofit client mirroring `/mobile/*`,
`EncryptedSharedPreferences` for base URL + dashboard token, FCM service stub.
Build in Android Studio; not exercised by the Python CI. See `android/README.md`.
