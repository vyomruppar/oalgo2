"""Runtime configuration. All secrets come from environment variables (prefix OALGO_)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OALGO_", env_file=".env", extra="ignore")

    data_dir: Path = REPO_ROOT / "data"
    # SEC fair-access policy asks automated clients to identify themselves ("Name contact@example.com").
    # Set OALGO_SEC_USER_AGENT to your own contact string; without it www.sec.gov may refuse requests
    # and the platform falls back to data.sec.gov only.
    sec_user_agent: str = "oalgo2-research/0.1"
    http_user_agent: str = "oalgo2-research/0.1"
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    # Scan sizing (free providers are rate limited; the universe fills in incrementally)
    scan_max_symbols: int = 300
    price_history_years: int = 12
    yahoo_rps: float = 2.0
    sec_rps: float = 8.0

    # Scheduler
    scheduler_enabled: bool = True
    scan_cron_hour_utc: int = 22  # after the US close
    scan_cron_minute: int = 30

    # Headline sentiment: auto = FinBERT if the optional "ai" group is installed, else the word list
    sentiment_engine: str = "auto"   # auto | finbert | lexicon

    # Optional e-mail notifications
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    alert_email_to: str | None = None

    @property
    def db_url(self) -> str:
        return f"sqlite:///{self.data_dir / 'oalgo.sqlite'}"

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    @property
    def prices_dir(self) -> Path:
        return self.data_dir / "prices"

    @property
    def fundamentals_dir(self) -> Path:
        return self.data_dir / "fundamentals"

    @property
    def models_dir(self) -> Path:
        return self.data_dir / "models"

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.cache_dir, self.prices_dir, self.fundamentals_dir):
            d.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.ensure_dirs()
    return s
