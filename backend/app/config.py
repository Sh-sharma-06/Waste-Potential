
"""Environment-based application settings for Waste-Potential."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

# Load local development variables from the project root.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env", override=False)

_ENVIRONMENTS = frozenset({"development", "test", "production"})


@dataclass(frozen=True)
class Settings:
    app_name: str = "Waste-Potential API"
    environment: str = "development"
    run_store_max_runs: int = 1000

    def __post_init__(self) -> None:
        if self.environment not in _ENVIRONMENTS:
            raise ValueError(
                f"WP_ENVIRONMENT must be one of {sorted(_ENVIRONMENTS)}, "
                f"got {self.environment!r}"
            )
        if self.run_store_max_runs < 1:
            raise ValueError(
                f"WP_RUN_STORE_MAX_RUNS must be >= 1, "
                f"got {self.run_store_max_runs}"
            )


def _env_str(name: str, default: str) -> str:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip()


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from exc


def load_settings() -> Settings:
    """Build settings from the current environment."""
    defaults = Settings()
    return Settings(
        app_name=_env_str("WP_APP_NAME", defaults.app_name),
        environment=_env_str("WP_ENVIRONMENT", defaults.environment).lower(),
        run_store_max_runs=_env_int(
            "WP_RUN_STORE_MAX_RUNS", defaults.run_store_max_runs
        ),
    )


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance."""
    return load_settings()


# Gemini configuration. API keys are loaded on the backend only.
def get_setting(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


GEMINI_MODEL = get_setting("GEMINI_MODEL", "gemini-3.8-flash")
GEMINI_API_KEY_AUDIT = get_setting("GEMINI_API_KEY_AUDIT")
GEMINI_API_KEY_ADVISOR = get_setting("GEMINI_API_KEY_ADVISOR")
GEMINI_API_KEY_PARSER = get_setting("GEMINI_API_KEY_PARSER")
