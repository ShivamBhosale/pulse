"""Runtime configuration loaded from environment / .env (prefix ``PULSE_``)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

API_BASE = "https://health.googleapis.com/v4"
SCOPE_PREFIX = "https://www.googleapis.com/auth/googlehealth."
SCOPES: tuple[str, ...] = tuple(
    SCOPE_PREFIX + s
    for s in (
        "activity_and_fitness.readonly",
        "health_metrics_and_measurements.readonly",
        "sleep.readonly",
        "profile.readonly",
        "settings.readonly",
    )
)


class Goals(BaseSettings):
    """Defaults only; phase 1 moves these into a DB-backed settings table."""

    sleep_minutes: int = 8 * 60
    steps: int = 10_000
    azm_weekly: int = 150


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PULSE_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    google_client_id: str = ""
    google_client_secret: SecretStr = SecretStr("")

    data_dir: Path = Path("./data")
    fixtures_dir: Path = Path("./fixtures")
    tz: str = "America/Toronto"
    units: str = "metric"

    api_base: str = API_BASE
    oauth_port: int = 8765
    # 127.0.0.1 on bare metal; docker-compose sets 0.0.0.0 so the published port reaches it.
    oauth_bind_addr: str = "127.0.0.1"

    serve_host: str = "0.0.0.0"  # noqa: S104 - reached over Tailscale; see README
    serve_port: int = 8000

    # Minimum seconds between API requests (rate limits are not published).
    min_request_interval: float = 0.5

    # Built frontend (Docker copies it to /app/static; local dev uses frontend/dist).
    static_dir: Path = Path("frontend/dist")
    scheduler_enabled: bool = True
    sync_interval_min: int = 15

    # Nightly database backup (local time, HH:MM). PULSE_BACKUP_DIR can point at another disk
    # (mount it into the container); default is data/backups.
    backup_enabled: bool = True
    backup_time: str = Field(default="03:30", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    backup_dir: Path | None = None

    goals: Goals = Field(default_factory=Goals)

    @property
    def zone(self) -> ZoneInfo:
        return ZoneInfo(self.tz)

    @property
    def token_path(self) -> Path:
        return self.data_dir / "token.json"

    @property
    def log_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "pulse.db"

    @property
    def lock_path(self) -> Path:
        return self.data_dir / "sync.lock"

    @property
    def backups_path(self) -> Path:
        return self.backup_dir or self.data_dir / "backups"

    @property
    def server_lock_path(self) -> Path:
        return self.data_dir / "server.lock"

    @property
    def secret_key_path(self) -> Path:
        return self.data_dir / "secret_key"

    @property
    def scrub_salt_path(self) -> Path:
        return self.data_dir / "scrub_salt"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
