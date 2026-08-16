"""Environment/configuration loading for ev-finder."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

DEFAULT_DB_PATH = "data/odds.db"


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


@dataclass(frozen=True)
class Settings:
    odds_api_key: str | None
    db_path: Path


def load_settings() -> Settings:
    """Load settings from environment variables / .env file.

    Does not require ODDS_API_KEY to be present -- callers that need it
    (e.g. the odds client) should validate via `require_odds_api_key`.
    """
    load_dotenv()
    return Settings(
        odds_api_key=os.getenv("ODDS_API_KEY") or None,
        db_path=Path(os.getenv("DB_PATH", DEFAULT_DB_PATH)),
    )


def require_odds_api_key(settings: Settings) -> str:
    if not settings.odds_api_key:
        raise ConfigError(
            "ODDS_API_KEY is not set. Copy .env.example to .env and add your "
            "free API key from https://the-odds-api.com/"
        )
    return settings.odds_api_key
