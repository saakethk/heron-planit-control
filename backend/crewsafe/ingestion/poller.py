"""Poller service: fetch each source on its own interval and publish raw payloads.

A failing source is logged and retried next interval; the transformer flags
the affected sites as stale once their last reading gets old.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime

from ..config import Settings
from ..messaging import topics
from ..messaging.bus import MessageBus
from ..storage.repository import Repository
from .sources.base import AlertSource, LightningSource, WeatherSource

log = logging.getLogger(__name__)


class Poller:
    def __init__(self, bus: MessageBus, repo: Repository, settings: Settings, weather: WeatherSource,
                 alerts: AlertSource, lightning: LightningSource | None) -> None:
        self.bus, self.repo, self.settings = bus, repo, settings
        self.weather, self.alerts, self.lightning = weather, alerts, lightning

    async def poll_weather(self, at: datetime | None = None) -> int:
        sites = await self.repo.list_sites()
        observations = await self.weather.fetch(sites, at)
        for obs in observations:
            await self.bus.publish(topics.RAW_WEATHER, obs, key=obs.site_id)
        return len(observations)

    async def poll_alerts(self) -> int:
        alerts = await self.alerts.fetch()
        for alert in alerts:
            await self.bus.publish(topics.RAW_NWS_ALERTS, alert, key=alert.alert_id)
        return len(alerts)

    async def poll_lightning(self) -> int:
        if not self.lightning:
            return 0
        strikes = await self.lightning.fetch()
        for strike in strikes:
            await self.bus.publish(topics.RAW_LIGHTNING, strike, key=strike.strike_id)
        return len(strikes)

    async def run(self) -> None:
        await asyncio.gather(
            self._every(self.settings.weather_interval, self.poll_weather, "weather"),
            self._every(self.settings.alert_interval, self.poll_alerts, "alerts"),
            self._every(self.settings.lightning_interval, self.poll_lightning, "lightning"),
        )

    @staticmethod
    async def _every(seconds: float, job: Callable[[], Awaitable[int]], name: str) -> None:
        while True:
            await asyncio.sleep(seconds)
            try:
                count = await job()
                log.debug("polled %s: %d messages", name, count)
            except Exception:
                log.exception("poll %s failed", name)
