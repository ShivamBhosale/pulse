# Pulse setup: Google Cloud, OAuth, first probe

This takes about 15 minutes. You do it once. Everything here is free.

> Based on Google's docs as read on 2026-11-21: Google Health API *Setup*, *Scopes*,
> *Endpoints*, Google Identity *OAuth 2.0 for native apps* and *refresh token expiration*,
> and Cloud help *Manage App Audience*. The Cloud Console moves things around now and then.
> If a menu name here doesn't match what you see, look for the same concept nearby.

---

## 0. Prerequisites

- **Google Health app linked.** Sign in to the **Google Health** mobile app with the *same*
  Google account your Fitbit Air syncs to. Without this, every API call fails with
  `400 FAILED_PRECONDITION / ACCOUNT_NOT_LINKED`.
- **Server ready.** Your home server has Docker with the compose plugin, and you can SSH to it
  from your laptop.

## 1. Create a dedicated Google Cloud project

1. Go to <https://console.cloud.google.com/projectcreate>.
2. Name it, for example, `pulse-personal`. No organization is needed. No billing account is needed.
3. Use a **new** project for Pulse alone. Google has no sandbox for this API, and the
   Personal-mode choice in step 3 is permanent for a project.

## 2. Enable the Google Health API

1. With the new project selected, open
   <https://console.developers.google.com/apis/library/health.googleapis.com>.
2. Click **Enable**. The service name is `health.googleapis.com`.

## 3. Choose the publishing mode (this decides refresh-token lifetime)

| Mode | Refresh token lifetime | Consent experience | Fit for Pulse |
|---|---|---|---|
| **Testing** | **Expires 7 days after consent.** Google applies this to any scopes beyond name, email and profile, and the Health scopes are beyond them. | Only listed test users, up to 100 | ❌ Sync would break every week |
| **In production, unverified** | Doesn't expire on a timer. It is invalidated if revoked, or after **6 months unused**. The 15-minute sync prevents that. | One-time "Google hasn't verified this app" warning, which you click through. Lifetime cap of 100 users. | ✅ Works |
| **Personal mode** | No 7-day expiry. | No verification, no user cap, no unverified-app screen. **Only the project creator's account can authorize.** Other accounts get `client_user_mismatch`. | ✅✅ Best fit, if it accepts the Health scopes |

**Recommendation: try Personal mode first, and fall back to In production.**

Two caveats about Personal mode:
- Google documents it as a **one-time selection when configuring a new application**.
  You can't switch a project into it or out of it later.
- Google's page doesn't say whether Personal mode accepts the Google Health scopes. If consent
  fails, create another fresh project and use In production.

### 3a. Personal mode (try first)

1. Open <https://console.cloud.google.com/auth/overview/personal> with the new project selected.
2. Follow the prompts to configure the app as **Personal**. App name: `Pulse`. Support email: yours.
3. Continue to step 4. If step 6 later fails with a scope or audience error, go to 3b in a new project.

### 3b. In production (fallback)

1. Open **Google Auth Platform → Branding** (<https://console.cloud.google.com/auth/branding>).
   Click **Get started**.
   - App name `Pulse`, user support email = yours.
   - **Audience: External.**
   - Contact email = yours. Accept the policy.
2. Open **Audience** (<https://console.cloud.google.com/auth/audience>).
   - Add yourself under **Test users**. This is harmless and needed while still in Testing.
   - Click **Publish app** and confirm. The status becomes **In production**.
   - Google may say verification is recommended. You can skip it, because only your account will
     ever authorize, and you stay far below the 100-user cap.

## 4. Declare the scopes

Open **Google Auth Platform → Data access** (<https://console.cloud.google.com/auth/scopes>).
Click **Add or remove scopes** and add exactly these five. Pulse is read-only; don't add any
`writeonly` scope.

```
https://www.googleapis.com/auth/googlehealth.activity_and_fitness.readonly
https://www.googleapis.com/auth/googlehealth.health_metrics_and_measurements.readonly
https://www.googleapis.com/auth/googlehealth.sleep.readonly
https://www.googleapis.com/auth/googlehealth.profile.readonly
https://www.googleapis.com/auth/googlehealth.settings.readonly
```

If they don't appear in the picker, paste them into **Manually add scopes**. Save.

## 5. Create a Desktop OAuth client

> Google's Health "quickstart" button creates a *Web server* client with a
> `https://www.google.com` redirect. **Don't use it.** Pulse is an installed app and needs a
> **Desktop** client, which supports the loopback redirect with PKCE.

1. Open **Google Auth Platform → Clients** (<https://console.cloud.google.com/auth/clients>).
   Click **Create client**.
2. Application type: **Desktop app**. Name: `pulse-cli`. Click **Create**.
3. Copy the **Client ID** and **Client secret**.
   - Google treats desktop secrets as not truly confidential, but Pulse still keeps the secret
     out of git and logs.
4. On the server:

   ```bash
   git clone <your repo> ~/pulse && cd ~/pulse
   cp .env.example .env && chmod 600 .env
   $EDITOR .env               # paste PULSE_GOOGLE_CLIENT_ID and PULSE_GOOGLE_CLIENT_SECRET
   mkdir -p data fixtures && chmod 700 data fixtures
   echo "PULSE_UID=$(id -u)" >> .env; echo "PULSE_GID=$(id -g)" >> .env
   docker compose build
   ```

## 6. Authorize: `pulse auth` over an SSH tunnel

Google redirects your browser to `http://127.0.0.1:8765/` after consent. That loopback
address has to reach the server, so tunnel it.

1. **Laptop, terminal 1.** Forward local port 8765 to the server's loopback:

   ```bash
   ssh -N -L 8765:127.0.0.1:8765 <you>@<server>
   ```

2. **Server, terminal 2.** The `127.0.0.1:` prefix keeps the port off your LAN:

   ```bash
   docker compose run --rm -p 127.0.0.1:8765:8765 pulse auth
   ```

3. Open the printed URL in your laptop browser and sign in with the linked Google account.
   - In **In production** mode you'll see *"Google hasn't verified this app"*.
     Click **Advanced → Go to Pulse (unsafe)**. That's expected for your own unverified app.
   - **Tick every checkbox** on the consent screen. If you leave one unticked, Pulse warns you
     and that data category stays unavailable.
4. The browser shows "Pulse is authorized". The terminal prints
   `Authorized as healthUserId …1234`.
5. Check the token's permissions with `ls -l data/token.json`. It should show `-rw-------`.

**How the flow works:** an installed-app flow with PKCE (S256) and a `state` check, requesting
`access_type=offline` and `prompt=consent` so a refresh token is always issued. All five scopes
are requested up front, because Google doesn't support incremental authorization for installed
apps.

**Re-running `pulse auth`** is safe. It replaces the token. Google keeps at most 100 refresh
tokens per account per client and silently drops the oldest.

**Revoking access:** go to <https://myaccount.google.com/permissions>, find Pulse, and remove
it. Then delete `data/token.json`.

## 7. Probe your data

```bash
docker compose run --rm pulse probe            # last 7 days, all 24 types
docker compose run --rm pulse probe -t sleep -t heart-rate --days 2
```

The probe output contains:
- Your account time zone and units, from `users/me/settings`.
- A coverage table: type, status (`ok` / `empty` / `error <code>`), number of points
  (`+` means more pages exist beyond `--max-pages`), first and last timestamp in
  your time zone, and sample values.
- `fixtures/raw/*.json`: exact responses, mode 0600, never committed.
- `fixtures/scrubbed/*.json`: the same with user, data point and client IDs replaced by HMAC
  placeholders. The salt is in `data/scrub_salt`. Also git-ignored by default.
- `fixtures/*/coverage.json`: the table in machine-readable form, including **which filter
  syntax the API accepted** for each type.

Send me the table, or `fixtures/scrubbed/coverage.json`.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `ACCOUNT_NOT_LINKED` | Sign in to the Google Health mobile app with this account, then retry. |
| Browser can't reach `127.0.0.1:8765` | The SSH tunnel isn't running, or the port is busy. Use `pulse auth --port 8790` and tunnel 8790. |
| `redirect_uri_mismatch` | The client isn't the **Desktop app** type. Create a Desktop client (step 5). |
| `access_denied` / `org_internal` / scope errors at consent | The consent screen is misconfigured. Check that steps 3–4 are complete. If Personal mode refuses Health scopes, use 3b in a new project. |
| Works for a week, then `Token refresh failed` | The app is still in **Testing**. Publish it (3b) and re-run `pulse auth`. |
| `client_user_mismatch` | Personal mode only allows the account that created the project. |
| Many types `error 400 INVALID_ARGUMENT` | The filter syntax differs from the docs. Send me `coverage.json`, which records every attempt. |
