"""Source interfaces. Add a real provider by implementing one of these and
selecting it in `sources/__init__.py`; nothing downstream changes."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from ...contracts.events import RawLightningStrike, RawNwsAlert, RawObservation
from ...storage.models import SiteRecord


class WeatherSource(Protocol):
    name: str

    async def fetch(self, sites: list[SiteRecord], at: datetime | None = None) -> list[RawObservation]:
        """Current conditions for every site. `at` is only honored by the dummy
        source (used to backfill history)."""


class AlertSource(Protocol):
    name: str

    async def fetch(self) -> list[RawNwsAlert]: ...


class LightningSource(Protocol):
    """Real-time strike feeds are commercial (Vaisala GLD360, Earth Networks,
    Xweather). Implement `fetch` against whichever feed is licensed."""
    name: str

    async def fetch(self) -> list[RawLightningStrike]: ...
