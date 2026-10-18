"""Settings from environment variables (or an untracked `.env` file). See `.env.example`."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = BACKEND_DIR.parent
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


def _real() -> bool:
    """DATA_SOURCE=real (default) uses live feeds and the pipeline's trained model;
    DATA_SOURCE=dummy uses the simulated world (offline demos, tests)."""
    return _env("DATA_SOURCE", "real") == "real"


def _by_mode(name: str, real: str, dummy: str) -> str:
    return _env(name, real if _real() else dummy)


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

    # Data sources. Real: Open-Meteo weather, NWS alerts, NOAA GOES GLM lightning.
    # "dummy" generates realistic fake data through the same pipeline.
    weather_source: str = field(default_factory=lambda: _by_mode("WEATHER_SOURCE", "open-meteo", "dummy"))
    alert_source: str = field(default_factory=lambda: _by_mode("ALERT_SOURCE", "nws", "dummy"))
    lightning_source: str = field(default_factory=lambda: _by_mode("LIGHTNING_SOURCE", "glm", "dummy"))  # glm | dummy | none
    nws_user_agent: str = field(
        default_factory=lambda: _env("NWS_USER_AGENT", "CrewSafe/0.1 (swamphacks; contact@example.com)"))
    # Optional paid Open-Meteo key; without it the free tier allows ~10,000 location-calls a day.
    open_meteo_api_key: str = field(default_factory=lambda: _env("OPEN_METEO_API_KEY", ""))
    # Sites closer than this share one Open-Meteo location (223 locations for 346 plants at 0.1°,
    # about the resolution of Open-Meteo's models).
    weather_grid_deg: float = field(default_factory=lambda: float(_env("WEATHER_GRID_DEG", "0.1")))
    # NOAA's public GOES-East bucket (GOES-19 since 2025).
    glm_bucket: str = field(default_factory=lambda: _env("GLM_BUCKET", "noaa-goes19"))

    # Poll intervals in seconds. The dummy sources run faster so the demo shows live changes.
    # Real defaults keep Open-Meteo's free tier under ~10,000 calls a day; lightning (GLM)
    # and NWS alerts are the minute-by-minute feeds.
    weather_interval: float = field(default_factory=lambda: float(_by_mode("WEATHER_INTERVAL", "2700", "30")))
    # Daily aggregates and soil layers the model reads change slowly; also refreshed at the UTC day rollover.
    model_inputs_interval: float = field(default_factory=lambda: float(_env("MODEL_INPUTS_INTERVAL", "21600")))
    alert_interval: float = field(default_factory=lambda: float(_by_mode("ALERT_INTERVAL", "120", "45")))
    lightning_interval: float = field(default_factory=lambda: float(_by_mode("LIGHTNING_INTERVAL", "60", "15")))
    # Hours of history to backfill through the pipeline at startup (index chart).
    backfill_hours: int = field(default_factory=lambda: int(_env("BACKFILL_HOURS", "8")))
    # Fabricated demo alerts and crew reports; only meaningful with the dummy world.
    seed_demo_history: bool = field(default_factory=lambda: _flag("SEED_DEMO_HISTORY", not _real()))

    # The data/ML pipeline at the repo root: site registry, FEMA flood zones, trained model.
    pipeline_dir: str = field(default_factory=lambda: _env("PIPELINE_DIR", str(REPO_DIR / "pipeline")))
    # Model: "pipeline" (the pipeline's trained classifier), "dummy" (formula stand-in), or "lightgbm".
    model_kind: str = field(default_factory=lambda: _by_mode("MODEL_KIND", "pipeline", "dummy"))
    model_path: str = field(default_factory=lambda: _env("MODEL_PATH", ""))

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
