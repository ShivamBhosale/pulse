"""Pulse command-line interface."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from pulse.auth import AuthError, TokenStore, missing_scopes, run_consent_flow
from pulse.client import AccountNotLinked, HealthApiError, HealthClient
from pulse.config import Settings, get_settings
from pulse.datatypes import REGISTRY
from pulse.db import make_engine, make_session_factory, migrate, session_scope
from pulse.fileio import ensure_private_dir
from pulse.logsetup import setup_logging
from pulse.probe import Coverage, FixtureWriter, Status, run_probe
from pulse.runtime import make_client
from pulse.scrub import Scrubber
from pulse.sync.engine import SyncBusy, SyncEngine, SyncReport

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
    return make_client(s)


def _engine(s: Settings) -> SyncEngine:
    engine = make_engine(s.db_path)
    migrate(engine)
    return SyncEngine(make_session_factory(engine), _client(s), s.zone, lock_path=s.lock_path)


def _print_report(report: SyncReport) -> None:
    if not report.auth_ok:
        console.print(f"[red]Auth failed: {report.auth_error}[/red] Run `pulse auth`.")
    for r in report.results:
        mark = "[green]ok[/]" if r.ok else f"[red]failed[/] {r.error}"
        console.print(f"  {r.stream:<18} {mark} {r.rows if r.ok and r.rows else ''}")
    console.print(f"{report.requests} API requests")


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
def sync(
    stream: Annotated[
        list[str] | None, typer.Option("--stream", "-s", help="Only these streams")
    ] = None,
) -> None:
    """Run one incremental sync now (re-fetches the last 3 days)."""
    s = _bootstrap()
    try:
        with console.status("syncing…"):
            report = _engine(s).run_sync(only=stream)
    except SyncBusy as exc:
        console.print(f"[yellow]{exc}[/yellow]")
        raise typer.Exit(1) from exc
    _print_report(report)
    raise typer.Exit(0 if report.ok else 1)


@app.command()
def backfill(
    since: Annotated[
        datetime | None,
        typer.Option(formats=["%Y-%m-%d"], help="Oldest day to fetch (default: discover)"),
    ] = None,
    restart: Annotated[bool, typer.Option(help="Ignore saved progress")] = False,
    stream: Annotated[
        list[str] | None,
        typer.Option("--stream", "-s", help="Refill only these streams (needs --since)"),
    ] = None,
) -> None:
    """Fetch history, newest first. Safe to interrupt; re-run to resume."""
    from rich.progress import BarColumn, Progress, TextColumn, TimeElapsedColumn

    s = _bootstrap()
    eng = _engine(s)
    if stream:
        from pulse.sync.streams import STREAMS_BY_NAME

        unknown = [x for x in stream if x not in STREAMS_BY_NAME]
        if unknown or since is None:
            problem = (
                f"Unknown stream(s): {', '.join(unknown)}"
                if unknown
                else "--since is required with --stream"
            )
            console.print(f"[red]{problem}. Streams: {', '.join(STREAMS_BY_NAME)}[/red]")
            raise typer.Exit(1)
        with console.status("refilling…") as st:
            report = eng.refill(
                stream,
                since.date(),
                progress=lambda name, lo, hi: st.update(f"refilling {name} {lo}…{hi}"),
            )
        _print_report(report)
        raise typer.Exit(0 if report.ok else 1)
    floor = since.date() if since else None
    if floor is None:
        with console.status("discovering earliest data…"):
            floor = eng.discover_earliest()
        if floor is None:
            console.print("[yellow]No data found.[/yellow]")
            return
        console.print(f"Earliest data: [bold]{floor}[/bold]")
    plan = eng.backfill_plan(floor, restart)
    if plan is None or plan[0] >= plan[1]:
        console.print("[green]Backfill already complete.[/green] Use --restart to redo it.")
        return
    total_days = (plan[1] - plan[0]).days
    console.print(f"Backfilling {plan[0]} → {plan[1]} ({total_days} days)")
    with Progress(
        TextColumn("{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total} days"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("starting", total=total_days)

        def on_progress(stream: str, lo: date, hi: date) -> None:
            progress.update(
                task, description=f"{stream:<18} {lo}…{hi}", completed=(plan[1] - hi).days
            )

        try:
            report = eng.run_backfill(floor, restart=False, progress=on_progress)
        except SyncBusy as exc:
            console.print(f"[yellow]{exc}[/yellow]")
            raise typer.Exit(1) from exc
        progress.update(task, completed=total_days)
    _print_report(report)
    raise typer.Exit(0 if report.ok else 1)


passcode_app = typer.Typer(help="Optional 4-6 digit passcode for the web UI")
app.add_typer(passcode_app, name="passcode")


@passcode_app.command("set")
def passcode_set() -> None:
    """Set (or change) the passcode. Logs out every device."""
    from pulse import prefs, security

    s = _bootstrap()
    code = typer.prompt("New passcode (4-6 digits)", hide_input=True)
    if not (code.isdigit() and 4 <= len(code) <= 6):
        console.print("[red]Passcode must be 4-6 digits.[/red]")
        raise typer.Exit(1)
    if typer.prompt("Repeat", hide_input=True) != code:
        console.print("[red]Passcodes don't match.[/red]")
        raise typer.Exit(1)
    engine = make_engine(s.db_path)
    migrate(engine)
    with session_scope(make_session_factory(engine)) as db:
        prefs.put(db, "passcode_hash", security.hash_passcode(code))
    console.print("[green]Passcode set.[/green]")


@passcode_app.command("clear")
def passcode_clear() -> None:
    """Remove the passcode (UI open to anyone who can reach the server)."""
    from pulse import prefs

    s = _bootstrap()
    engine = make_engine(s.db_path)
    migrate(engine)
    with session_scope(make_session_factory(engine)) as db:
        prefs.put(db, "passcode_hash", None)
    console.print("Passcode cleared.")


@app.command()
def backup(
    list_: Annotated[bool, typer.Option("--list", help="List backups instead")] = False,
) -> None:
    """Back up the database now (online, safe while the server runs), then rotate."""
    from pulse.backup import BackupRunner, list_backups

    s = _bootstrap()
    if list_:
        files = list_backups(s.backups_path)
        if not files:
            console.print(f"No backups in {s.backups_path}")
        for f in files:
            console.print(f"{f.path.name}  {f.size_bytes / 1e6:6.1f} MB")
        return
    engine = make_engine(s.db_path)
    migrate(engine)
    runner = BackupRunner(make_session_factory(engine), s.db_path, s.backups_path, s.zone)
    made = runner.run()
    if made is None:
        console.print("[red]Backup failed or already running; see data/logs/pulse.log[/red]")
        raise typer.Exit(1)
    console.print(f"[green]Wrote {made.path}[/green] ({made.size_bytes / 1e6:.1f} MB)")


@app.command()
def restore(
    file: Annotated[Path, typer.Argument(help="Backup file (.db.gz or .db)")],
    yes: Annotated[bool, typer.Option("--yes", help="Don't ask for confirmation")] = False,
) -> None:
    """Replace the database with a backup. Stop the server first (docker compose stop)."""
    from pulse.backup import BackupError, restore_backup

    s = _bootstrap()
    if not yes and not typer.confirm(
        f"Replace {s.db_path} with {file.name}? The current database is kept as a copy."
    ):
        raise typer.Exit(1)
    try:
        previous = restore_backup(
            file, s.db_path, server_lock=s.server_lock_path, sync_lock=s.lock_path
        )
    except BackupError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc
    console.print(f"[green]Restored {file.name}.[/green] Previous database kept at {previous}")


@app.command()
def openapi(
    out: Annotated[Path, typer.Option(help="Where to write the spec")] = Path("openapi.json"),
) -> None:
    """Write the OpenAPI spec (used to generate frontend and Android clients)."""
    import json

    from pulse.api.app import create_app
    from pulse.db import make_engine as _mk

    spec = create_app(get_settings(), engine=_mk(None), start_scheduler=False).openapi()
    out.write_text(json.dumps(spec, indent=2) + "\n")
    console.print(f"Wrote {out}")


@app.command()
def serve() -> None:
    """Run the web server (API + PWA + scheduler)."""
    import uvicorn

    s = _bootstrap()
    uvicorn.run(
        "pulse.api.app:create_app",
        factory=True,
        host=s.serve_host,
        port=s.serve_port,
        proxy_headers=False,
        log_config=None,
    )


if __name__ == "__main__":
    app()
