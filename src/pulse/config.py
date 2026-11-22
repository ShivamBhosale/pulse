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
    def scrub_salt_path(self) -> Path:
        return self.data_dir / "scrub_salt"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
