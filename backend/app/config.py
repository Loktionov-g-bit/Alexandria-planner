from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All settings come from environment variables with the PLANNER_ prefix."""

    model_config = SettingsConfigDict(env_prefix="PLANNER_", env_file=None)

    database_url: str = "postgresql+asyncpg://planner:planner@db:5432/planner"
    # Public base URL, e.g. https://planner.example.com or https://nas.local/planner
    base_url: str = "http://localhost:8000"
    # Proxies whose X-Forwarded-* headers are trusted ("*" = any, fine when only the proxy can reach the app)
    forwarded_allow_ips: str = "*"
    data_dir: Path = Path("/data")
    static_dir: Path = Path(__file__).resolve().parent.parent / "static"

    session_days: int = 14
    session_idle_hours: int = 72
    login_max_attempts: int = 5          # failures before a temporary lock
    login_lock_minutes: int = 15
    password_min_length: int = 10

    scheduler_minutes: int = 10          # 0 = off (tests)

    channel: str = "stable"              # stable | beta (update channel this container serves)
    # stable only: where the beta container listens; beta users' requests are forwarded there
    beta_url: str | None = None
    # background work (scheduler, notifications, Telegram, digests). Off on beta: one Telegram token, one poller
    worker: bool = True
    backup_keep: int = 10                # pre-migration backups kept in /data/backups

    @property
    def cookie_secure(self) -> bool:
        return self.base_url.startswith("https://")

    @property
    def root_path(self) -> str:
        from urllib.parse import urlparse

        return urlparse(self.base_url).path.rstrip("/")


@lru_cache
def get_settings() -> Settings:
    return Settings()
