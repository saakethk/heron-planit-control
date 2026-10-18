from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from crewsafe.api.main import create_app
from crewsafe.config import Settings


def make_settings(tmp_path, **overrides) -> Settings:
    """The dummy world, whatever the environment says: tests stay offline and deterministic."""
    dummy = dict(weather_source="dummy", alert_source="dummy", lightning_source="dummy", model_kind="dummy",
                 seed_demo_history=True, weather_interval=30.0, alert_interval=45.0, lightning_interval=15.0)
    return Settings(run_pollers=False, backfill_hours=1, photo_dir=str(tmp_path / "photos"), **{**dummy, **overrides})


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(make_settings(tmp_path))) as c:
        yield c


def wait_for(check, timeout: float = 3.0):
    """Poll until `check()` returns something truthy (pipeline work is async)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = check()
        if result:
            return result
        time.sleep(0.05)
    raise AssertionError("condition not met in time")
