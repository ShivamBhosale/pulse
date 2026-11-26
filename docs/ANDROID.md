# Pulse for Android (standalone)

Pulse runs **entirely on your phone**. It reads the data your Fitbit app already writes to **Health Connect**, stores it in a private on-phone database, and calculates every score itself. There's no server, no Google sign-in, no internet permission and no cloud backup.

| Tab | What's there |
|---|---|
| **Today** | Daily summary (fixed rules, no AI), 6 tiles (readiness with its breakdown, sleep, resting HR, HRV, steps so far, active zone minutes so far), quick journal. Pull down to re-read Health Connect. |
| **Sleep** | Night stats, stage chart, time per stage, evening-before tags, previous and next night. |
| **Health** | Resting HR, HRV, breathing rate, blood oxygen and skin temperature against your personal 28-day range, over 30 days, 90 days or a year. |
| **Trends** | Any metric over 30 days, 90 days or a year, and how two metrics move together. |
| **More** | Records and streaks; Data and sync (freshness, coverage, re-import); Settings (goals, birth year, units, readiness weights); add the widget. |

## Where the data comes from

| Health Connect record | Written by | Pulse uses it for |
|---|---|---|
| Steps, distance, calories, floors | Fitbit app | daily totals (Health Connect removes duplicates between sources), steps per 15 minutes |
| Heart rate | Fitbit app | per-minute heart rate, sleeping HR, **active zone minutes** (calculated: see below) |
| Resting HR, HRV, breathing rate, skin temperature | Fitbit app | nightly values, assigned to the wake date |
| Sleep (with stages) | Fitbit app | sessions, stages, bed and wake times, efficiency, interruptions |
| Blood oxygen | Google Health app | nightly average, low and high |
| Exercise | Fitbit and Google Health apps | workouts (the same workout from both apps counts once) |

**Active zone minutes** have no Health Connect record, so Pulse calculates them from per-minute heart rate. It uses heart-rate-reserve zones (the method Fitbit documents): fat burn is 40–59% of reserve, cardio 60–84%, peak 85% and above. Maximum HR is 208 − 0.7 × age. Cardio and peak minutes count double. Set your **birth year** in Settings; until then Pulse assumes age 30.

**Syncing.** On first launch Pulse imports your most recent 30 days, which takes about 3 minutes. Older history then continues in the background, about 3½ minutes per month, and the import resumes if interrupted. After that, every refresh re-reads the last 3 days: when the app opens, on pull-to-refresh, and every 30 minutes for the widget (never when the battery is low).

## Build and install

```bash
export JAVA_HOME="/Applications/Android Studio.app/Contents/jbr/Contents/Home"
scripts/android-keystore.sh          # once: signing key (git-ignored); back it up
cd android
./gradlew testDebugUnitTest lintDebug assembleRelease
~/Library/Android/sdk/platform-tools/adb install -r app/build/outputs/apk/release/app-release.apk
```

On first launch, tap **Connect Health Connect**, then **Allow all**. Turn on **past data** (history) and **background access** (widget), then tap **Allow**.

The maths is a direct port of the server's Python, and the Kotlin tests reuse the Python test cases. The phone and the server therefore give the same readiness, baselines and summary for the same data. The UI reuses the model classes generated from `frontend/openapi.json`.

## Privacy and battery

- No `INTERNET` permission at all: the app can't send data anywhere.
- Data lives in Health Connect and in Pulse's private database. It's excluded from cloud backup and device transfer, and uninstalling Pulse deletes it.
- Pulse only reads Health Connect; it never writes to it.
- The only background work is one WorkManager job every 30 minutes, which doesn't run when the battery is low. There are no wake locks and no foreground service.

## The server (optional)

The Python server and web dashboard in this repo still work and are maintained, but the app no longer needs them.
