"""Settings from environment variables (or an untracked `.env` file). See `.env.example`."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
# Local development only; set JWT_SECRET anywhere else.
DEV_JWT_SECRET = "dev-only-insecure-jwt-secret-change-me"


def _load_dotenv() -> None:
    env_file = BACKEND_DIR / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()


def _env(name: str, default: str) -> str:
    """Unset and empty both mean "use the default" (so a copied .env.example works)."""
    return os.environ.get(name) or default


def _flag(name: str, default: bool) -> bool:
    return _env(name, str(default)).lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    # "local": every service runs inside the API process on an in-memory bus.
    # "kafka": each service is its own process (`python -m crewsafe.run`) connected by Kafka.
    pipeline_mode: str = field(default_factory=lambda: _env("PIPELINE_MODE", "local"))
    # "memory" or "postgres"
    storage: str = field(default_factory=lambda: _env("STORAGE", "memory"))
    kafka_bootstrap: str = field(default_factory=lambda: _env("KAFKA_BOOTSTRAP", "localhost:9092"))
    # Required when STORAGE=postgres; set it in .env, never in code.
    database_url: str = field(default_factory=lambda: _env("DATABASE_URL", ""))

    # Data sources: "dummy" generates realistic fake data through the real pipeline.
    weather_source: str = field(default_factory=lambda: _env("WEATHER_SOURCE", "dummy"))  # dummy | open-meteo
    alert_source: str = field(default_factory=lambda: _env("ALERT_SOURCE", "dummy"))  # dummy | nws
    lightning_source: str = field(default_factory=lambda: _env("LIGHTNING_SOURCE", "dummy"))  # dummy | none
    nws_user_agent: str = field(
        default_factory=lambda: _env("NWS_USER_AGENT", "CrewSafe/0.1 (swamphacks; contact@example.com)"))

    # Poll intervals in seconds. Real sources update every 10-15 minutes; the dummy
    # sources run faster so the demo shows live changes.
    weather_interval: float = field(default_factory=lambda: float(_env("WEATHER_INTERVAL", "30")))
    alert_interval: float = field(default_factory=lambda: float(_env("ALERT_INTERVAL", "45")))
    lightning_interval: float = field(default_factory=lambda: float(_env("LIGHTNING_INTERVAL", "15")))
    # Hours of dummy history to backfill through the pipeline at startup (index chart).
    backfill_hours: int = field(default_factory=lambda: int(_env("BACKFILL_HOURS", "8")))

    # Model: "dummy" (formula stand-in) or "lightgbm" (loads MODEL_PATH).
    model_kind: str = field(default_factory=lambda: _env("MODEL_KIND", "dummy"))
    model_path: str = field(default_factory=lambda: _env("MODEL_PATH", str(BACKEND_DIR / "models" / "hazard_lgbm")))

    # Lightning policy (matches the app).
    stop_work_radius_miles: float = 10.0
    all_clear_seconds: float = field(default_factory=lambda: float(_env("ALL_CLEAR_SECONDS", "1800")))

    # Auth: off by default so the current app (which doesn't log in yet) works.
    auth_required: bool = field(default_factory=lambda: _flag("AUTH_REQUIRED", False))
    jwt_secret: str = field(default_factory=lambda: _env("JWT_SECRET", DEV_JWT_SECRET))
    jwt_ttl_seconds: int = 8 * 3600

    photo_dir: str = field(default_factory=lambda: _env("PHOTO_DIR", str(BACKEND_DIR / "data" / "photos")))
    sites_file: str = field(
        default_factory=lambda: _env("SITES_FILE", str(BACKEND_DIR / "crewsafe" / "storage" / "seed" / "florida_sites.json")))
    # Start the in-process pollers (local mode). Tests turn this off and drive the pipeline directly.
    run_pollers: bool = field(default_factory=lambda: _flag("RUN_POLLERS", True))


def get_settings() -> Settings:
    return Settings()
