from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from crewsafe.api.main import create_app
from crewsafe.config import Settings


def make_settings(tmp_path, **overrides) -> Settings:
    return Settings(run_pollers=False, backfill_hours=1, photo_dir=str(tmp_path / "photos"), **overrides)


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
