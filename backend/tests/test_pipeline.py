"""Pipeline services on the in-memory bus, without the API."""

from __future__ import annotations

import asyncio
from datetime import timedelta

from crewsafe.config import Settings
from crewsafe.contracts.common import utcnow
from crewsafe.contracts.events import RawLightningStrike, RawObservation
from crewsafe.geo import offset
from crewsafe.messaging import topics
from crewsafe.messaging.bus import InMemoryBus
from crewsafe.processing.features import FEATURE_COLUMNS, heat_index_f
from crewsafe.processing.lightning import LightningEngine
from crewsafe.processing.transformer import Transformer
from crewsafe.storage.memory import InMemoryRepository
from crewsafe.storage.models import SiteRecord

SITE = SiteRecord(id=664, name="John R Kelly", county="Alachua", latitude=29.6461, longitude=-82.3208, capacity_mw=141.6)


def run(coro):
    return asyncio.run(coro)


def collect(bus: InMemoryBus, topic: str) -> list[dict]:
    out: list[dict] = []

    async def handler(t, k, v):
        out.append(v)

    bus.subscribe([topic], f"test-{topic}", handler)
    return out


def test_heat_index_matches_nws_table():
    assert abs(heat_index_f(92, 60) - 105) <= 1.5
    assert abs(heat_index_f(80, 40) - 80) <= 1.5


def test_transformer_dead_letters_bad_payloads():
    async def scenario():
        bus, repo = InMemoryBus(), InMemoryRepository()
        await repo.upsert_sites([SITE])
        Transformer(bus, repo).register()
        dead, clean = collect(bus, topics.DEAD_LETTER), collect(bus, topics.CLEAN_CONDITIONS)
        await bus.start()
        await bus.publish(topics.RAW_WEATHER, RawObservation(source="open-meteo", site_id=664, fetched_at=utcnow(),
                                                             payload={"current": {}}))
        await bus.publish(topics.RAW_WEATHER, RawObservation(source="mystery", site_id=664, fetched_at=utcnow(),
                                                             payload={}))
        await bus.drain()
        await bus.stop()
        return dead, clean

    dead, clean = run(scenario())
    assert len(dead) == 2 and not clean


def test_lightning_hold_lifecycle():
    async def scenario():
        bus, repo = InMemoryBus(), InMemoryRepository()
        await repo.upsert_sites([SITE])
        LightningEngine(bus, repo, Settings()).register()
        holds = collect(bus, topics.LIGHTNING_HOLDS)
        await bus.start()
        start = utcnow() - timedelta(minutes=40)

        def strike(i, minutes, miles):
            lat, lon = offset(SITE.latitude, SITE.longitude, miles, 225)
            return RawLightningStrike(strike_id=f"s{i}", latitude=lat, longitude=lon,
                                      occurred_at=start + timedelta(minutes=minutes), source="test")

        for i, (minutes, miles) in enumerate([(0, 8), (5, 3), (6, 15)]):
            await bus.publish(topics.RAW_LIGHTNING, strike(i, minutes, miles))
        await bus.drain()
        hold = await repo.get_hold(664)
        await bus.publish(topics.RAW_LIGHTNING, strike(9, 37, 6))  # 32 min after the last close strike
        await bus.drain()
        await bus.stop()
        return holds, hold

    events, hold = run(scenario())
    assert [e["event"] for e in events] == ["started", "extended", "cleared", "started"]
    assert hold.strike_count == 2 and hold.closest_miles == 3.0 and hold.last_direction == "SW"


def test_feature_columns_are_unique():
    assert len(FEATURE_COLUMNS) == len(set(FEATURE_COLUMNS))
