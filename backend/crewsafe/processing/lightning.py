"""Lightning engine: the server-side stop-work timer.

Policy (same as the app): a strike within 10 miles starts a hold; every strike
inside the radius restarts the 30-minute all-clear countdown; the hold clears
when 30 minutes pass with no strike inside the radius.

raw.lightning -> lightning.site_strikes (strikes within 30 mi, for scoring and the app)
              -> lightning.holds (started / extended / cleared)
"""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from ..config import Settings
from ..contracts.api import LightningHold
from ..contracts.common import utcnow
from ..contracts.events import HoldEvent, RawLightningStrike, SiteStrike
from ..geo import direction_from, miles_between
from ..messaging import topics
from ..messaging.bus import MessageBus
from ..storage.models import SiteRecord
from ..storage.repository import Repository

log = logging.getLogger(__name__)

WATCH_RADIUS_MILES = 30.0


class LightningEngine:
    def __init__(self, bus: MessageBus, repo: Repository, settings: Settings) -> None:
        self.bus, self.repo = bus, repo
        self.radius = settings.stop_work_radius_miles
        self.all_clear = settings.all_clear_seconds
        self._sites: list[SiteRecord] | None = None

    def register(self) -> None:
        self.bus.subscribe([topics.RAW_LIGHTNING], "lightning", self.handle)

    async def _all_sites(self) -> list[SiteRecord]:
        if self._sites is None:
            self._sites = await self.repo.list_sites()
        return self._sites

    async def handle(self, topic: str, key: str | None, value: dict[str, Any]) -> None:
        strike = RawLightningStrike(**value)
        for site in await self._all_sites():
            # Cheap bounding box before the exact distance.
            if abs(site.latitude - strike.latitude) > 0.5 or abs(site.longitude - strike.longitude) > 0.6:
                continue
            miles = miles_between(site.latitude, site.longitude, strike.latitude, strike.longitude)
            if miles > WATCH_RADIUS_MILES:
                continue
            direction = direction_from(site.latitude, site.longitude, strike.latitude, strike.longitude)
            inside = miles <= self.radius
            await self.bus.publish(topics.LIGHTNING_SITE_STRIKES, SiteStrike(
                site_id=site.id, strike_id=strike.strike_id, distance_miles=round(miles, 1), direction=direction,
                occurred_at=strike.occurred_at, inside_stop_work_radius=inside), key=site.id)
            if inside:
                await self._apply_to_hold(site.id, strike, round(miles, 1), direction)

    async def _apply_to_hold(self, site_id: int, strike: RawLightningStrike, miles: float, direction: str) -> None:
        hold = await self.repo.get_hold(site_id)
        if hold and strike.occurred_at >= hold.last_strike_at + timedelta(seconds=hold.all_clear_interval):
            await self._clear(hold, hold.last_strike_at + timedelta(seconds=hold.all_clear_interval))
            hold = None
        if hold is None:
            hold = LightningHold(
                site_id=site_id, started_at=strike.occurred_at, last_strike_at=strike.occurred_at, strike_count=1,
                closest_miles=miles, last_distance_miles=miles, last_direction=direction,
                all_clear_interval=self.all_clear)
            event = "started"
        else:
            newer = strike.occurred_at >= hold.last_strike_at
            hold = hold.model_copy(update={
                "strike_count": hold.strike_count + 1,
                "closest_miles": min(hold.closest_miles, miles),
                "last_strike_at": max(hold.last_strike_at, strike.occurred_at),
                "last_distance_miles": miles if newer else hold.last_distance_miles,
                "last_direction": direction if newer else hold.last_direction,
            })
            event = "extended"
        await self.repo.upsert_hold(hold)
        await self.bus.publish(topics.LIGHTNING_HOLDS, HoldEvent(site_id=site_id, event=event, hold=hold,
                                                                  at=strike.occurred_at), key=site_id)

    async def _clear(self, hold: LightningHold, at) -> None:
        await self.repo.delete_hold(hold.site_id)
        await self.bus.publish(topics.LIGHTNING_HOLDS, HoldEvent(site_id=hold.site_id, event="cleared", hold=hold, at=at),
                               key=hold.site_id)

    async def expire_holds(self) -> int:
        now = utcnow()
        cleared = 0
        for hold in await self.repo.list_holds():
            ends_at = hold.last_strike_at + timedelta(seconds=hold.all_clear_interval)
            if now >= ends_at:
                await self._clear(hold, ends_at)
                cleared += 1
        return cleared

    async def run(self, every_seconds: float = 5.0) -> None:
        while True:
            await asyncio.sleep(every_seconds)
            try:
                await self.expire_holds()
            except Exception:
                log.exception("expiring holds failed")
