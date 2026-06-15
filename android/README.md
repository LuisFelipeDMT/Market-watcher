# Market Watcher — Android app (scaffold)

Native Kotlin + Jetpack Compose client for the **mobile gateway** in the
analysis service (`/mobile/*`). It does the three consumption jobs:

1. **Proposal viewer** — the unified ranked feed (renda fixa + equities), with
   the decision context (fair value, margin of safety, why now). You buy
   manually in XP for now.
2. **Push** — registers its FCM token and shows alerts (new opportunities,
   TRIGGERED names, 2FA, security) as notifications.
3. **2FA approval** — lists pending login requests and relays the code your
   authenticator shows, so the unattended watcher can re-login.

> **Status: scaffold.** This is a starting point to open in Android Studio; it
> is not built or tested by the Python repo's CI. Versions in the Gradle files
> may need bumping for your toolchain.

## Build
1. Open `android/` in Android Studio (Giraffe+), let it sync Gradle.
2. Add your Firebase `app/google-services.json` (for push). Without it, the app
   still runs; only push is disabled.
3. Set the backend in-app (Settings): **base URL** (your dashboard over the VPN,
   e.g. `https://market-watcher.your-tailnet.ts.net/`) and **dashboard token**
   (`DASHBOARD_TOKEN`). The token is stored in `EncryptedSharedPreferences`.
4. Run on a device on the same VPN/tailnet.

## Security notes
- The app holds only the **dashboard token**, never the collector token or XP
  password. It talks solely to the analysis gateway.
- 2FA: your authenticator (this app or another) shows the code; you approve a
  specific, time-boxed request — never a blind "approve".
- The future assisted-purchase flow will collect the XP password + token
  **per order** in a dedicated screen and never persist them (see
  `docs/consumption-and-mobile-plan.md`).

## Layout
```
app/src/main/java/com/marketwatcher/app/
  MainActivity.kt        Compose nav (Proposals / 2FA / Settings)
  data/Api.kt            Retrofit interface + DTOs (mirror /mobile/*)
  data/ApiClient.kt      Retrofit builder + bearer-token interceptor
  data/AppSettings.kt    encrypted base-url + token storage
  ui/ProposalsScreen.kt  ranked feed + detail
  ui/TwoFactorScreen.kt  pending approvals + submit code
  push/PushService.kt    FirebaseMessagingService (register + notify)
```
