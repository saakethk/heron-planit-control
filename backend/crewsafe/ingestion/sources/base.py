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
        """Current conditions for every site. `at` (a past time) is used to
        backfill history at startup."""


class AlertSource(Protocol):
    name: str

    async def fetch(self) -> list[RawNwsAlert]: ...


class LightningSource(Protocol):
    """`GlmLightningSource` reads NOAA's free GOES GLM flashes. Commercial
    strike feeds (Vaisala GLD360, Earth Networks, Xweather) plug in the same way."""
    name: str

    async def fetch(self) -> list[RawLightningStrike]: ...
