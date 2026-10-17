"""Environment-based application settings.

All variables use the ``WP_`` prefix:

  WP_APP_NAME             Title shown in OpenAPI docs (default "Waste-Potential API").
  WP_ENVIRONMENT          "development" | "test" | "production" (default "development").
  WP_RUN_STORE_MAX_RUNS   Max runs kept by the in-memory run store (default 1000).

Blank or whitespace-only values are treated as unset. Settings are read once
and cached; call ``get_settings.cache_clear()`` in tests after changing the
environment.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

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
                f"WP_RUN_STORE_MAX_RUNS must be >= 1, got {self.run_store_max_runs}"
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
    """Build Settings from the current environment (uncached)."""
    defaults = Settings()
    return Settings(
        app_name=_env_str("WP_APP_NAME", defaults.app_name),
        environment=_env_str("WP_ENVIRONMENT", defaults.environment).lower(),
        run_store_max_runs=_env_int("WP_RUN_STORE_MAX_RUNS", defaults.run_store_max_runs),
    )


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide Settings instance."""
    return load_settings()
