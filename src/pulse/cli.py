"""Pulse command-line interface."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from pulse.auth import AuthError, CredentialManager, TokenStore, missing_scopes, run_consent_flow
from pulse.client import AccountNotLinked, HealthApiError, HealthClient
from pulse.config import Settings, get_settings
from pulse.datatypes import REGISTRY
from pulse.fileio import ensure_private_dir
from pulse.logsetup import setup_logging
from pulse.probe import Coverage, FixtureWriter, Status, run_probe
from pulse.scrub import Scrubber

app = typer.Typer(no_args_is_help=True, add_completion=False, help="Pulse health dashboard")
console = Console()

NOT_LINKED_HELP = (
    "This Google account is not linked to Google Health yet. Sign in to the Google Health "
    "app on your phone with the same Google account, then run `pulse auth` again."
)


def _bootstrap() -> Settings:
    s = get_settings()
    ensure_private_dir(s.data_dir)
    setup_logging(s.log_dir, extra_secrets=(s.google_client_secret.get_secret_value(),))
    return s


def _client(s: Settings) -> HealthClient:
    creds = CredentialManager(TokenStore(s.token_path))
    return HealthClient(
        lambda force: creds.access_token(force_refresh=force),
        base_url=s.api_base,
        min_interval=s.min_request_interval,
    )


def _mask(value: str) -> str:
    return f"…{value[-4:]}" if len(value) > 4 else "…"


@app.command()
def auth(
    port: Annotated[int | None, typer.Option(help="Loopback port for the OAuth redirect")] = None,
) -> None:
    """Authorize Pulse (read-only scopes) and store the refresh token."""
    s = _bootstrap()
    port = port or s.oauth_port
    console.print(
        f"[bold]Pulse OAuth[/bold]. On a headless server, first run on your laptop:\n"
        f"  [cyan]ssh -N -L {port}:127.0.0.1:{port} <server>[/cyan]\n"
    )
    try:
        creds = run_consent_flow(s, port, console.print)
    except AuthError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc
    store = TokenStore(s.token_path)
    store.save(creds)
    if missing := missing_scopes(creds):
        console.print("[yellow]Some scopes were not granted (unticked on the consent screen):")
        for scope in missing:
            console.print(f"  - {scope}")
        console.print("Data in those categories will be unavailable. Re-run to grant them.[/]")
    try:
        with _client(s) as client:
            ident = client.get_identity()
    except AccountNotLinked as exc:
        console.print(f"[red]{NOT_LINKED_HELP}[/red]")
        raise typer.Exit(2) from exc
    except HealthApiError as exc:
        console.print(f"[red]Token saved, but the identity check failed: {exc}[/red]")
        raise typer.Exit(1) from exc
    console.print(
        f"[green]Authorized[/green] as healthUserId {_mask(str(ident.get('healthUserId', '')))}."
        f" Token stored at {s.token_path} (0600)."
    )


def _fmt(t: datetime | date | None, s: Settings) -> str:
    if t is None:
        return "-"
    if isinstance(t, datetime):
        return t.astimezone(s.zone).strftime("%Y-%m-%d %H:%M")
    return t.isoformat()


def _render(results: list[Coverage], s: Settings) -> Table:
    table = Table(title="Google Health coverage", header_style="bold", show_lines=False)
    for col in ("type", "status", "points", f"first ({s.tz})", "last", "sample values"):
        table.add_column(col, no_wrap=col != "sample values")
    colors = {Status.OK: "green", Status.EMPTY: "yellow", Status.ERROR: "red"}
    for c in results:
        status = c.status.value if c.status is not Status.ERROR else f"error {c.error}"
        pts = f"{c.points}{'+' if c.truncated else ''}" if c.points else "0"
        table.add_row(
            c.data_type,
            f"[{colors[c.status]}]{status}[/]",
            pts,
            _fmt(c.first, s),
            _fmt(c.last, s),
            "\n".join(c.samples) or "-",
        )
    return table


@app.command()
def probe(
    days: Annotated[int, typer.Option(help="Civil days to look back")] = 7,
    max_pages: Annotated[int, typer.Option(help="Page cap per type (heart-rate is dense)")] = 3,
    types: Annotated[
        list[str] | None, typer.Option("--type", "-t", help="Limit to these data types")
    ] = None,
    save: Annotated[bool, typer.Option(help="Write raw + scrubbed fixtures")] = True,
) -> None:
    """Fetch identity/profile/settings and the last N days of every data type."""
    s = _bootstrap()
    unknown = [t for t in types or [] if t not in REGISTRY]
    if unknown:
        console.print(f"[red]Unknown data types: {', '.join(unknown)}[/red]")
        raise typer.Exit(1)
    selected = [REGISTRY[t] for t in types] if types else list(REGISTRY.values())
    writer = (
        FixtureWriter(s.fixtures_dir, Scrubber.from_salt_file(s.scrub_salt_path)) if save else None
    )
    try:
        with _client(s) as client, console.status("probing…") as status:
            account, results = run_probe(
                client,
                selected,
                s.zone,
                days,
                max_pages,
                writer,
                on_progress=lambda name: status.update(f"probing {name}…"),
            )
            n_requests = client.request_count
    except AuthError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc

    ident = account.get("identity", {})
    if "error" in ident:
        console.print(f"[red]identity: {ident['error']}[/red]")
        if "ACCOUNT_NOT_LINKED" in str(ident["error"]) or "FAILED_PRECONDITION" in str(
            ident["error"]
        ):
            console.print(f"[red]{NOT_LINKED_HELP}[/red]")
    settings = account.get("settings", {})
    if "timeZone" in settings:
        console.print(
            f"Account time zone: [bold]{settings['timeZone']}[/bold]  "
            f"distance: {settings.get('distanceUnit', '?')}  "
            f"weight: {settings.get('weightUnit', '?')}"
        )
        if settings["timeZone"] != s.tz:
            console.print(
                f"[yellow]Note: PULSE_TZ is {s.tz}; account says {settings['timeZone']}.[/]"
            )
    console.print(_render(results, s))
    ok = sum(c.status is Status.OK for c in results)
    console.print(f"{ok}/{len(results)} types have data · {n_requests} API requests")
    if writer:
        console.print(f"Fixtures: {s.fixtures_dir}/raw (private) and {s.fixtures_dir}/scrubbed")
    if any(c.truncated for c in results):
        console.print("[dim]'+' = more pages exist beyond --max-pages[/dim]")


@app.command()
def serve() -> None:
    """Run the web server."""
    import uvicorn

    s = _bootstrap()
    uvicorn.run("pulse.api.app:app", host=s.serve_host, port=s.serve_port, proxy_headers=False)


if __name__ == "__main__":
    app()
