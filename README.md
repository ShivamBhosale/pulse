# Pulse

Pulse is a self-hosted, single-user dashboard for your Fitbit data, read from the
**Google Health API v4**. It runs on your own server at no cost. It uses no cloud hosting and
no AI calls, and your health data stays on the server.

> **Status: Phase 5 — data health page, on top of the dashboard, summary, backups, tags & notes.**
> Pages: Today, Sleep, Heart & recovery, Activity (with workout detail), Trends & explore, Records & streaks and Settings. It is an installable PWA, and readiness is a personal heuristic.

## Quick start

1. Follow **[docs/SETUP.md](docs/SETUP.md)**. It covers the Google Cloud project, the consent
   screen, the Desktop OAuth client and the SSH tunnel.
2. Then run:

   ```bash
   cp .env.example .env && chmod 600 .env        # fill in client id/secret
   mkdir -p data fixtures && chmod 700 data fixtures
   docker compose build
   docker compose run --rm -p 127.0.0.1:8765:8765 pulse auth   # with ssh -L 8765 tunnel
   docker compose run --rm pulse probe                          # optional: coverage report
   docker compose run --rm pulse backfill                       # all history, resumable
   docker compose up -d                                         # UI + API + 15-min sync on :8000
   ```

`restart: unless-stopped` brings the container back after a reboot, provided the Docker daemon
is enabled (`systemctl enable docker`).

**While the server is running, run CLI commands inside its container** with `docker compose exec pulse pulse <command>`, for example `docker compose exec pulse pulse sync` or `docker compose exec pulse pulse backfill -s steps_15m --since 2025-01-01`. This keeps every SQLite writer in one container. During development on macOS (Colima's file share), a backfill running in a second `docker compose run` container lost its last few commits while the server was up. The bind mount on a Linux server is native, but `exec` is the safe habit either way. `pulse auth` and the first backfill can use `docker compose run` before `up -d`.

## Commands

| Command | What it does |
|---|---|
| `pulse auth [--port 8765]` | Runs the installed-app OAuth flow: loopback redirect, PKCE S256, five read-only scopes. Writes `data/token.json` (0600). |
| `pulse probe [--days 7] [-t TYPE ...] [--max-pages 3] [--no-save]` | Calls identity, profile and settings, then fetches the last N days of each data type. Prints a coverage table and writes fixtures. |
| `pulse backfill [--since YYYY-MM-DD] [--restart]` | Fetches history newest-first in 90-day chunks. It finds the earliest data itself, shows progress, and resumes where it stopped if interrupted. |
| `pulse sync [-s STREAM]` | Runs one incremental sync now. Each run re-fetches the last 3 days, because the device revises recent data. |
| `pulse passcode set` / `clear` | Sets or removes the optional 4–6 digit passcode for the web UI. Setting it logs out every device. |
| `pulse backup [--list]` | Backs up the database now. Uses SQLite's online backup, so it's safe while the server runs. Checks integrity, gzips the copy, then rotates old backups. `--list` shows existing backups. |
| `pulse restore FILE [--yes]` | Replaces the database with a backup, keeping the current one as `pulse.db.pre-restore-<time>`. It refuses while the server or a sync is running. |
| `pulse openapi [--out FILE]` | Writes the OpenAPI spec. The frontend types are generated from it, and so will the future Android client be. |
| `pulse serve` | Starts the API, the PWA and the 15-minute scheduler. OpenAPI is at `/api/v1/openapi.json`, docs at `/api/v1/docs`. |

To run these locally without Docker: `uv sync`, then `uv run pulse …`.

## Architecture

```
Google Health API v4 ──(httpx, throttled, backoff)──► sync streams ──► SQLite (WAL) ──► FastAPI /api/v1 ──► React PWA
                         every 15 min (APScheduler)    replace-in-window       │                 (served by FastAPI)
                         + pulse backfill/sync          upserts                 └─ queries.py aggregates in SQL
```

### Sync design
- **Totals come from rollups.** Steps, distance and calories arrive from three sources: the band, the phone and Health Connect. Summing listed points would double-count, so `dailyRollUp` and `rollUp` give merged totals (see `docs/COVERAGE.md`).
- **Streams** are defined in `src/pulse/sync/streams.py`:

  | Stream | What it fetches | Chunk size |
  |---|---|---|
  | `daily_rollups_90` | daily totals | 90 days |
  | `daily_rollups_14` | HR, total kcal, kcal per zone, active minutes | 14 days |
  | `daily_lists` | resting HR, HRV, SpO2, skin temperature, zone bounds | 90 days |
  | `hr_minute` | 1-minute heart-rate rollup | 7 days |
  | `steps_15m` | 15-minute step rollup | 60 days (DST-safe under the 90-day physical limit) |
  | `intraday_lists` | AZM, SpO2/HRV samples, sedentary periods, exercises | 30 days |
  | `sleep` | sleep sessions, via reconcile | 30 days |

- **Revisions and deletions.** A stream owns specific rows per civil date. Each fetch deletes those rows inside the window, then upserts the new ones, all in one transaction. Device revisions and upstream deletions therefore show up. Re-running a sync is idempotent.
- **Days follow the API's civil dates** in `PULSE_TZ` (America/Toronto). Instants are stored in UTC, and DST is handled.
- **`sync_state`** records per stream: high-water mark, last success, last error, and the backfill cursor. Token-refresh failures land in the `_auth` row. `/api/v1/status` reports them, and the UI shows a reconnect banner.
- **Errors.** 429 and 5xx responses are retried with jittered exponential backoff that respects `Retry-After`. Logs are JSON lines in `data/logs/pulse.log` (`jq . data/logs/pulse.log`), with tokens redacted.

### Derived metrics (Phase 2)
`src/pulse/derived.py` is pure and unit-tested. `src/pulse/derive.py` recomputes **all history** after every sync, backfill or re-sync, and whenever you save goals or readiness weights. That takes about 100 ms for two years of data. Results are stored as ordinary rows in `daily_metrics`, so the charts, Explore, the year calendar and the records all treat them like any other metric. Sync streams never touch these keys.

| Key | Definition |
|---|---|
| `readiness` | 0–100. A weighted mean of four parts; default weights are HRV 35, RHR 25, Sleep 25, Strain 15, editable in Settings. **HRV** and **resting HR** (inverted) score 50 at your 28-day median, excluding today, and reach 0 or 100 at 1.5 × IQR away; the spread has a floor of 5% of the median. **Sleep** is last night's main sleep ÷ goal, capped at 100. **Strain** is yesterday's AZM compared with its own 28-day median, inverted and capped at 70, so rest days don't inflate the score. Missing parts are dropped and the remaining weights rescaled. A score needs at least two parts, one of them HRV or sleep. It is a personal heuristic, **not a medical measure**, and the UI shows the formula. |
| `strain` | Daily AZM-weighted minutes. Fitbit already counts cardio and peak minutes double. |
| `load_ratio` | Mean strain over 7 days ÷ mean strain over 28 days. Needs 21 days of history. |
| `sleep_debt_min` | Σ max(0, goal − main sleep) over the last 7 nights. Missing nights are skipped. |
| `bedtime_sd_min`, `waketime_sd_min` | Standard deviation over 14 days, needing at least 5 nights. Times are wrapped onto a −6h…18h scale around midnight, so 23:30 and 00:30 count as an hour apart. |
| `azm_week` | AZM total from Monday up to that day, compared against the weekly goal. |
| `calories_bmr` | Total calories minus active calories. The band reports no BMR, so this is labelled "Resting (est.)". |
| `sedentary_longest_min` | Longest single sedentary period of the day (SQL over the raw intervals). |

**Records** are computed on request from SQL series. Personal bests use the earliest day on ties. The lowest resting HR uses a 7-day mean, so a single bad reading can't set it.

**Streaks** count steps and sleep per day, and AZM per week. Today and the current week are in progress: they extend a streak but never break it. A day with no data breaks a streak.

### Daily summary (Phase 3)
`src/pulse/summary.py` writes a short note for any day. It uses fixed template rules and **no AI**, so the same data always gives the same text. `queries.day_facts` gathers the facts: readiness and what drove it, sleep against your goal and your sleep debt, a shifted bedtime, unusual vitals, weekly AZM progress, steps so far against your usual pace, streaks at stake, new personal bests, and training load.

Each rule returns a sentence or nothing. Sentences are ranked by priority, and at most 4 are shown under a one-line headline. Today's summary uses "so far" wording; earlier days use the past tense (`GET /api/v1/summary?date=`).

The wording compares you with your own baselines and never diagnoses. A vital is only mentioned when the difference is real: it must be well outside your usual range, or a bit outside it two days running, and above a minimum size (for example 2 bpm for resting HR). The summary is computed on request in about 5 ms, so it always matches re-synced data and changed goals.

### Tags & notes (Phase 4)
- **Journal.** Today → Journal lets you tag a day (Yesterday is one tap away) and write a note of up to 2,000 characters. Notes save automatically.
- **Your data only.** The `tags`, `day_tags` and `day_notes` tables are filled only by you. Sync never touches them, and backups include them.
- **Tags.** There are 8 defaults: Alcohol, Late meal, Late caffeine and Screen late are evening tags; Sick, Travel, Stress and Rest day are day tags. Add, rename and archive tags in Settings. Tags are never deleted, so their history stays.
- **Which day a tag affects.** You tag the day something happened. Overnight metrics (sleep, HRV, resting HR, SpO₂, skin temperature, readiness) belong to the day you wake up. An *evening* tag on Tuesday is therefore compared with Wednesday's overnight metrics; everything else compares the same day. "Same day" and "Next day" override this per comparison.
- **Comparison.** Trends → Tags compares tagged days with untagged days for any metric (`GET /api/v1/explore/tag-effect`). It shows each group's median, the difference, and that difference measured against your usual spread (IQR).
  - Significance comes from a **permutation test**: 5,000 shuffles from a fixed seed, so results are deterministic.
  - The verdict reads "Clear difference" (p < 0.05 with at least 5 tagged days), "Possible difference" (p < 0.2), "No clear difference" or "Not enough tagged days" (fewer than 3).
  - Days tagged Sick are left out of every other tag's comparison group.
  - `GET /explore/tag-effects` ranks every tag against one metric.
- **Elsewhere.** Trends charts can mark a tag's days, and every tooltip shows that day's tags and note. The Sleep page shows the evening-before tags. The summary says "Tagged last night: …".

### Data health (Phase 5)
The **Data** page (in the More menu on a phone) answers three questions.

- **Is my data fresh?** The *band* line shows the newest heart-rate minute that reached Google. If it's hours old, the phone app hasn't synced the band. The page also shows when Pulse last synced and the newest day for each daily signal. Sleep counts as fresh while last night's sleep is in.
- **Which days are missing?** A coverage grid has one row per signal (wear, daily steps, intraday steps, sleep, HRV, resting HR, SpO₂, skin temperature) and one column per day, over 30 days, 90 days or 1 year.
  - Wear is shaded by how much of the day the band recorded heart rate. Under 50% counts as *mostly off*.
  - Missing days are outlined. Days before a signal ever had data aren't counted, and today counts as in progress.
- **Can I fix it?** Click a day to see its wear timeline, with breaks of an hour or more listed, and each signal's status. Then **re-sync** that day, or any gap from the list. Re-sync re-fetches just those streams for just that range (`POST /api/v1/resync` with `since`, `until` and `streams`; at most 400 days).
  - If a gap stays after a re-sync, Google doesn't have that data either; usually the band wasn't worn.

Endpoints: `GET /api/v1/data-health/freshness`, `/data-health/coverage?from&to` (at most 800 days) and `/data-health/day?date`. The maths lives in `coverage.py`: DST-aware day lengths, runs of missing days, wear gaps and freshness.

### Backups
- **Nightly backup.** Runs at `PULSE_BACKUP_TIME` (03:30 local by default) and writes `data/backups/pulse-YYYY-MM-DD-HHMM.db.gz`. Files are mode 0600 in a 0700 directory and are never served over HTTP. Your current database (about 110 MB) compresses to about 14 MB.
- **Rotation.** Keeps the newest backup of each of the last **7 days, 4 weeks and 6 months**, and never deletes the newest backup.
- **Status.** Settings → Backups shows the last run and has a **Back up now** button (`POST /api/v1/backup`).
- **Another disk.** Set `PULSE_BACKUP_DIR` and mount that disk; see the commented lines in `docker-compose.yml`.
- **Restore.** Run `docker compose stop`, then `docker compose run --rm pulse restore /data/backups/<file>`, then `docker compose up -d`. The server holds a lock, so a restore refuses to run while the server is up.
- Backups contain all your health data. Copy them somewhere private, such as a second disk or an encrypted drive. They are useless without that care.

### API (`/api/v1`, OpenAPI at `/api/v1/openapi.json`)
| Endpoint | Purpose |
|---|---|
| `GET /today`, `/status`, `/sleep`, `/sleep/trend`, `/intraday/heart-rate` | Phase 1 views |
| `GET /metrics/{m}?from&to&granularity&band` | One metric (day, week or month, aggregated in SQL). `band=true` adds the rolling 28-day median and IQR. |
| `GET /series?metrics=a&metrics=b…` | Several metrics in one request (stacked charts) |
| `GET /metrics/{m}/weekday` | Averages by day of week |
| `GET /explore/correlate?a&b` | Paired daily values, Pearson r, n and a strength label |
| `GET /activity/heatmap` | Average steps by hour of day × weekday (DST-aware) |
| `GET /exercises`, `/exercises/{id}` | Workouts. Detail includes the HR curve and time in each zone. |
| `GET /records` | Personal bests and streaks |
| `GET /summary?date=` | Rule-based daily summary. It's also included in `/today`. |
| `GET/POST /tags`, `PATCH /tags/{key}` | Tags: create, rename, change kind, archive |
| `GET/PUT /journal/{date}`, `GET /journal?from&to` | A day's tags and note, or every day with entries in a range |
| `GET /explore/tag-effect`, `/explore/tag-effects` | Tagged vs untagged days: permutation test with a plain-language verdict |
| `GET/PUT /settings`, `PUT /settings/passcode` | Goals, units, readiness weights and passcode |
| `GET /data-health/freshness`, `/coverage`, `/day` | Data freshness, missing days per signal, a single day's wear and gaps |
| `POST /sync`, `/backfill`, `/resync`, `/backup` | Start background jobs. `/resync` takes `since`, `until` and `streams`. Returns 409 while another job runs. |

Pages hide any metric your device has never reported, using `/status.metrics`. On a Fitbit Air that means floors, VO2 max and weight.

### Code map
```
src/pulse/
  sync/{planner,parsers,streams,writer,engine}.py   pipeline (pure parsers + planner, unit-tested)
  models.py, db.py, migrations/                     schema (SQLAlchemy 2 + Alembic, auto-migrates at start)
  queries.py, metrics.py                            read side (SQL aggregation), metric catalog
  derived.py, derive.py                             derived metrics: pure maths + recompute job
  summary.py                                        rule-based daily summary (pure, templates)
  backup.py                                         online backup, rotation, restore, runner
  journal.py                                        tags & notes (validation, CRUD, queries)
  coverage.py                                       data-health maths (gaps, wear, freshness)
  api/{app,routes,schemas}.py                       FastAPI, passcode gate, SPA serving, OpenAPI
  scheduler.py, security.py, prefs.py, cli.py
frontend/                                           Vite + React + TS, TanStack Query, Tailwind, ECharts, PWA
```

### Data model
| Table | Contents |
|---|---|
| `raw_points` | Every listed or reconciled point, exactly as returned. Unique on `(data_type, point_key)`. |
| `daily_metrics` | Long format: `(civil_date, metric, value, unit)`. |
| `intraday_hr` | Heart rate per minute: avg, min, max. |
| `intraday_steps` | Steps per 15 minutes. |
| `intraday_samples` | SpO2 and HRV samples taken during sleep. |
| `hr_zone_bounds` | Heart-rate zone boundaries per day. |
| `sleep_sessions`, `sleep_stages` | Sleep sessions and their stages. |
| `exercises` | Workouts. Band and Health Connect duplicates are merged. |
| `sync_state` | Per-stream sync bookkeeping. |
| `settings` | Goals, units and the passcode hash. |
| `tags`, `day_tags`, `day_notes` | Your tags and notes (migration 0002). Sync never writes to these. |

These tables are enough to build a future template-based daily summary without schema changes.

## Where things live

| Path | Contents | Permissions | In git? |
|---|---|---|---|
| `.env` | OAuth client ID and secret, settings | 0600, set by you | **No** |
| `data/token.json` | refresh and access token | 0600, enforced | **No** |
| `data/scrub_salt` | HMAC salt for fixture scrubbing | 0600 | **No** |
| `data/logs/pulse.log` | rotating log, 5 × 5 MB; tokens and secrets redacted | dir 0700 | **No** |
| `fixtures/raw/` | unscrubbed API responses from `probe` | 0600 | **No** |
| `fixtures/scrubbed/` | ID-scrubbed responses; health values remain | 0600 | **No** (opt in if your remote is private) |
| `tests/fixtures/` | small synthetic responses in the documented shapes | — | Yes |
| `data/pulse.db` (+ `-wal`, `-shm`) | all synced health data | — | **No** |
| `data/secret_key` | HMAC key for passcode session cookies | 0600 | **No** |
| `data/backups/` | nightly gzipped database backups (all health data) | dir 0700, files 0600 | **No** |

## Backups

Backups are automatic: see *Backups* under Architecture. For an ad-hoc copy, `docker compose exec pulse pulse backup` writes one immediately. Also keep `.env` somewhere private. The token can always be re-issued with `pulse auth`.

## Running without Docker (systemd)

```bash
sudo useradd --system --home /opt/pulse --shell /usr/sbin/nologin pulse
sudo git clone <repo> /opt/pulse && cd /opt/pulse
sudo -u pulse uv sync --no-dev --frozen     # needs uv; installs Python 3.12 into .venv
(cd frontend && npm ci && npm run build)    # needs Node 22+; PULSE_STATIC_DIR=/opt/pulse/frontend/dist
sudo cp .env.example .env && sudo chmod 600 .env && sudo chown pulse: .env   # edit it
sudo -u pulse mkdir -p data fixtures
sudo -u pulse .venv/bin/pulse auth          # with ssh -L 8765 tunnel
sudo cp deploy/pulse.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now pulse
```

## Development

```bash
uv sync
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run mypy
cd frontend && npm ci && npm run typecheck && npm run lint && npm run build
npm run dev                      # Vite on :5173, proxies /api to `uv run pulse serve` on :8000
uv run pulse openapi --out frontend/openapi.json && npm run gen:api   # after API changes
```

## Installing the PWA
On your Pixel, open `http://<server-tailscale-name>:8000` in Chrome, then choose **⋮ → Add to Home screen → Install**.

Chrome only allows installing a service worker on a secure origin: HTTPS or localhost. Over plain-HTTP Tailscale, run `tailscale serve --bg 8000` on the server and open the `https://<server>.<tailnet>.ts.net` URL. Tailscale provisions the certificate, and the page stays private to your tailnet.

Tests never call the live API. They use `httpx.MockTransport` and the JSON in `tests/fixtures/`.

## Network exposure

The server binds to `PULSE_BIND`, which defaults to `0.0.0.0`. To serve only on your tailnet, set it to the server's Tailscale IP in `.env`, or to `127.0.0.1` when you use `tailscale serve`.

Pulse has no user accounts. You can add `pulse passcode set` for a lock screen. The passcode is stored as an scrypt hash, sessions use an HMAC-signed HttpOnly cookie, and failed attempts are limited to 5 per minute.
