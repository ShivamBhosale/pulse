# Pulse

Pulse is a self-hosted, single-user dashboard for your Fitbit data, read from the
**Google Health API v4**. It runs on your own server at no cost. It uses no cloud hosting and
no AI calls, and your health data stays on the server.

> **Status: Phase 1 — sync pipeline, API, Today and Sleep pages (installable PWA).**
> Phase 2 (full dashboard, readiness, records) is next.

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

## Commands

| Command | What it does |
|---|---|
| `pulse auth [--port 8765]` | Runs the installed-app OAuth flow: loopback redirect, PKCE S256, five read-only scopes. Writes `data/token.json` (0600). |
| `pulse probe [--days 7] [-t TYPE ...] [--max-pages 3] [--no-save]` | Calls identity, profile and settings, then fetches the last N days of each data type. Prints a coverage table and writes fixtures. |
| `pulse backfill [--since YYYY-MM-DD] [--restart]` | Fetches history newest-first in 90-day chunks. It finds the earliest data itself, shows progress, and resumes where it stopped if interrupted. |
| `pulse sync [-s STREAM]` | Runs one incremental sync now. Each run re-fetches the last 3 days, because the device revises recent data. |
| `pulse passcode set` / `clear` | Sets or removes the optional 4–6 digit passcode for the web UI. Setting it logs out every device. |
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
  | `steps_15m` | 15-minute step rollup | 90 days |
  | `intraday_lists` | AZM, SpO2/HRV samples, sedentary periods, exercises | 30 days |
  | `sleep` | sleep sessions, via reconcile | 30 days |

- **Revisions and deletions.** A stream owns specific rows per civil date. Each fetch deletes those rows inside the window, then upserts the new ones, all in one transaction. Device revisions and upstream deletions therefore show up. Re-running a sync is idempotent.
- **Days follow the API's civil dates** in `PULSE_TZ` (America/Toronto). Instants are stored in UTC, and DST is handled.
- **`sync_state`** records per stream: high-water mark, last success, last error, and the backfill cursor. Token-refresh failures land in the `_auth` row. `/api/v1/status` reports them, and the UI shows a reconnect banner.
- **Errors.** 429 and 5xx responses are retried with jittered exponential backoff that respects `Retry-After`. Logs are JSON lines in `data/logs/pulse.log`, with tokens redacted.

### Code map
```
src/pulse/
  sync/{planner,parsers,streams,writer,engine}.py   pipeline (pure parsers + planner, unit-tested)
  models.py, db.py, migrations/                     schema (SQLAlchemy 2 + Alembic, auto-migrates at start)
  queries.py, derived.py, metrics.py                read side: baselines (28-day median/IQR), catalog
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

## Backups

All state is in `data/`. Back up with SQLite's online backup, which is safe while the server runs:

```bash
sqlite3 data/pulse.db ".backup 'backups/pulse-$(date +%F).db'"
```

Copy `backups/` and `.env` somewhere private. The token can always be re-issued with
`pulse auth`.

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
