# Pulse

Pulse is a self-hosted, single-user dashboard for your Fitbit data, read from the
**Google Health API v4**. It runs on your own server at no cost. It uses no cloud hosting and
no AI calls, and your health data stays on the server.

> **Status: Phase 0, access and probe.**
>
> - Working: OAuth (`pulse auth`), a coverage probe (`pulse probe`), and a liveness endpoint.
> - Not yet built: the sync pipeline, database and UI. They arrive in Phases 1–2.

## Quick start

1. Follow **[docs/SETUP.md](docs/SETUP.md)**. It covers the Google Cloud project, the consent
   screen, the Desktop OAuth client and the SSH tunnel.
2. Then run:

   ```bash
   cp .env.example .env && chmod 600 .env        # fill in client id/secret
   mkdir -p data fixtures && chmod 700 data fixtures
   docker compose build
   docker compose run --rm -p 127.0.0.1:8765:8765 pulse auth   # with ssh -L 8765 tunnel
   docker compose run --rm pulse probe
   docker compose up -d                                         # web server on :8000
   curl http://localhost:8000/api/v1/health
   ```

`restart: unless-stopped` brings the container back after a reboot, provided the Docker daemon
is enabled (`systemctl enable docker`).

## Commands

| Command | What it does |
|---|---|
| `pulse auth [--port 8765]` | Runs the installed-app OAuth flow: loopback redirect, PKCE S256, five read-only scopes. Writes `data/token.json` (0600). |
| `pulse probe [--days 7] [-t TYPE ...] [--max-pages 3] [--no-save]` | Calls identity, profile and settings, then fetches the last N days of each data type. Prints a coverage table and writes fixtures. |
| `pulse serve` | Starts the FastAPI server. OpenAPI is at `/api/v1/openapi.json`. |

To run these locally without Docker: `uv sync`, then `uv run pulse …`.

## Architecture (Phase 0)

```
src/pulse/
  config.py     settings from env/.env (PULSE_*), scopes, goals, timezone
  auth.py       consent flow, TokenStore (atomic 0600 writes), CredentialManager (auto-refresh)
  client.py     httpx client: throttle, retries with jittered backoff + Retry-After,
                401 → refresh once, typed errors (AccountNotLinked, InvalidArgument, …), pagination
  datatypes.py  registry of the 24 data types (kind, value field, page size), AIP-160 filter builder,
                DST-safe civil-day windows
  probe.py      tries candidate filters per type, summarises coverage, writes fixtures
  scrub.py      HMAC-based deterministic ID scrubbing for fixtures
  logsetup.py   rotating log file with token/secret redaction
  api/app.py    FastAPI app (/api/v1/health)
```

API facts this code relies on come from the v4 docs, read 2026-11-21:

- **Base and methods.** The base URL is `https://health.googleapis.com/v4`.
  - `GET users/me/{identity,profile,settings}`
  - `GET users/me/dataTypes/{type}/dataPoints` (list)
  - `GET users/me/dataTypes/{type}/dataPoints:reconcile` (used for sleep)
  - `POST users/me/dataTypes/{type}/dataPoints:dailyRollUp`
- **Filters.** Data type names are snake_case inside a filter and kebab-case in the URL.
- **Page sizes.** Sleep and exercise pages cap at 25 points; other types cap at 10000.

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

The SQLite database will be `data/pulse.db` from Phase 1 onward.

## Backups

All state is in `data/`. Phase 0 has only the token and salt; a fresh `pulse auth` recreates
the token anyway.

From Phase 1, back up with SQLite's online backup, which is safe while the server runs:

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
```

Tests never call the live API. They use `httpx.MockTransport` and the JSON in `tests/fixtures/`.

## Network exposure

The server binds to `PULSE_BIND`, which defaults to `0.0.0.0`. To serve only on your tailnet,
set it to the server's Tailscale IP in `.env`. Phase 0 serves no health data; the optional
passcode screen arrives in Phase 1.
