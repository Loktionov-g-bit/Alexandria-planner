from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All settings come from environment variables with the PLANNER_ prefix."""

    model_config = SettingsConfigDict(env_prefix="PLANNER_", env_file=None)

    database_url: str = "postgresql+asyncpg://planner:planner@db:5432/planner"
    # Public base URL, e.g. https://planner.example.com or https://nas.local/planner
    base_url: str = "http://localhost:8000"
    # Proxies whose X-Forwarded-* headers are trusted. Default: loopback and private networks, i.e. a reverse proxy
    # on the same host, in Docker or on the LAN. A client coming straight from the internet cannot fake its IP
    # (that would dodge the per-IP sign-in limit). Set the exact proxy address for the tightest setup; "*" trusts anyone.
    forwarded_allow_ips: str = "127.0.0.1,::1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,fc00::/7"
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
    api_docs: bool = False               # /api/docs and /api/openapi.json (off: no API map for strangers)
    # failed sign-ins (password or 2FA code) from one IP before it is paused; per-account locking works on top
    ip_max_failures: int = 20
    ip_window_minutes: int = 15

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
