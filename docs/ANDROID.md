# Pulse for Android

A small native app for your Pixel, plus a home-screen widget. It talks only to **your** Pulse server, over Tailscale, and needs no Play Store or Google account.

| Screen | What it shows |
|---|---|
| **Today** (native) | The daily summary, the 6 tiles (readiness with its breakdown, sleep, resting HR, HRV, steps, AZM), and a quick journal (tags and note for today or yesterday). Pull down to sync now. |
| **Sleep** (native) | Night stats, a stage chart (hypnogram), time per stage, and evening-before tags. Step back and forward between nights. |
| **More** | Heart, Activity, Trends, Records, Data health and Settings open the web app in a Chrome tab. Also: add the widget, and change server. |
| **Widget** | Readiness, steps against your goal, last night's sleep, and weekly AZM. Refreshes every 30 minutes, only with network and never when the battery is low, and also whenever you open the app. |

## 1. Make Pulse reachable from your phone (Tailscale)

1. Install **Tailscale** on the machine running Pulse and on your Pixel, and sign both into the same tailnet.
2. On the Pulse machine, give it an HTTPS address. This is recommended, and it also makes the web app installable:

   ```bash
   tailscale serve --bg 8000
   tailscale serve status        # shows https://<machine>.<tailnet>.ts.net
   ```

   The simpler alternative is the machine's `http://100.x.y.z:8000` address. It's still encrypted, because Tailscale tunnels all traffic through WireGuard.

The app accepts **https://** for any address. It accepts plain **http://** only for Tailscale addresses (`100.64.0.0/10`, `*.ts.net`) and for localhost or the emulator, and refuses anything else.

## 2. Build the APK (on the laptop)

Requirements: Android Studio, for its bundled JDK and the Android SDK.

```bash
export JAVA_HOME="/Applications/Android Studio.app/Contents/jbr/Contents/Home"
scripts/android-keystore.sh          # once: creates a signing key (git-ignored, mode 600)
cd android
./gradlew testDebugUnitTest lintDebug assembleRelease
# → android/app/build/outputs/apk/release/app-release.apk
```

**Back up `android/keystore/` and `android/keystore.properties`.** Android only installs an update if it's signed with the same key.

The API client is **generated at build time** from `frontend/openapi.json`, the same spec the web app uses, so the app always matches the server. After changing the API, run:

```bash
uv run pulse openapi --out frontend/openapi.json     # regenerate the spec
uv run python scripts/android_fixtures.py            # refresh Android test fixtures (synthetic data)
```

## 3. Install on the Pixel

1. On the phone, turn on **Developer options**: go to Settings → About phone and tap **Build number** 7 times. Then go to Settings → System → Developer options → **USB debugging** (or **Wireless debugging**).
2. Connect by USB and accept the "Allow USB debugging" prompt on the phone. Then run:

   ```bash
   ~/Library/Android/sdk/platform-tools/adb install -r android/app/build/outputs/apk/release/app-release.apk
   ```

   To connect without a cable: Developer options → Wireless debugging → *Pair device with pairing code*, then `adb pair <ip:port>` and `adb connect <ip:port>`.
3. Open **Pulse**, enter your server address, and tap **Connect**. If you set a passcode, enter it.
4. Add the widget: More → **Add widget to home screen**.

## Privacy and battery

- Data only goes between the app and your server. There's no analytics, crash reporting, ads or Google sign-in, and nothing goes to cloud backup: `allowBackup=false`, with every domain excluded from device transfer.
- The app stores only the server URL, the passcode session cookie (HMAC-signed by the server) and the last widget snapshot, all in app-private storage.
- There are no foreground services and no wake locks. The only background work is one WorkManager job every 30 minutes, which needs a network connection and a battery that isn't low.

## Development notes

- Tests: `./gradlew testDebugUnitTest` covers the URL policy, formatting and widget mapping. It also decodes fixtures dumped from the server's synthetic test data and runs the repository against MockWebServer: locked, offline and sync polling.
- The emulator reaches a laptop server at `http://10.0.2.2:8000`.
- The OpenAPI 3.1 generator doesn't support "array of nullable numbers" (for example `steps_curve.today`). The Gradle build reads the spec and patches exactly those element types to be nullable after generation; see `app/build.gradle.kts`.
