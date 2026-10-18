"""Wires the layers together.

Local mode (default): one process runs pollers, transformer, lightning engine,
scoring, alerts, and the API on an in-memory bus with the in-memory repository.
This is the architecture's no-Kafka fallback, and what the demo uses.

Kafka mode: each service runs as its own process (`python -m crewsafe.run <service>`),
connected by Kafka and sharing Postgres. See crewsafe/run.py.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import timedelta

from .config import Settings
from .contracts.common import utcnow
from .ingestion.poller import Poller
from .ingestion.sources import create_sources
from .messaging.bus import InMemoryBus, MessageBus
from .processing.alerts.delivery import LogPushSender
from .processing.alerts.service import AlertService
from .processing.lightning import LightningEngine
from .processing.scoring.model import load_model
from .processing.scoring.service import ScoringService
from .processing.transformer import Transformer
from .storage import create_repository
from .storage.repository import Repository
from .storage.seed import seed

log = logging.getLogger(__name__)


def create_bus(settings: Settings, client_id: str = "crewsafe") -> MessageBus:
    if settings.pipeline_mode == "kafka":
        from .messaging.kafka_bus import KafkaBus
        return KafkaBus(settings.kafka_bootstrap, client_id)
    return InMemoryBus()


@dataclass
class Pipeline:
    settings: Settings
    bus: MessageBus
    repo: Repository
    transformer: Transformer
    lightning: LightningEngine
    scoring: ScoringService
    alerts: AlertService
    push: LogPushSender
    poller: Poller | None = None
    tasks: list[asyncio.Task] = field(default_factory=list)

    @property
    def model_version(self) -> str:
        return self.scoring.model.version

    async def drain(self) -> None:
        if isinstance(self.bus, InMemoryBus):
            await self.bus.drain()


def build_pipeline(settings: Settings, bus: MessageBus | None = None, repo: Repository | None = None) -> Pipeline:
    bus = bus or create_bus(settings)
    repo = repo or create_repository(settings)
    push = LogPushSender()
    return Pipeline(
        settings=settings, bus=bus, repo=repo,
        transformer=Transformer(bus, repo),
        lightning=LightningEngine(bus, repo, settings),
        scoring=ScoringService(bus, repo, load_model(settings)),
        alerts=AlertService(bus, repo, push),
        push=push,
    )


async def ensure_seeded(p: Pipeline) -> None:
    await p.repo.connect()
    if await p.repo.is_empty():
        log.info("seeding sites and demo history")
        await seed(p.repo, p.settings.sites_file)


async def attach_poller(p: Pipeline) -> Poller:
    weather, alerts, lightning = create_sources(p.settings, await p.repo.list_sites())
    p.poller = Poller(p.bus, p.repo, p.settings, weather, alerts, lightning)
    return p.poller


async def bootstrap(p: Pipeline) -> None:
    """First readings at startup. With the dummy source, also backfill today's
    history through the real pipeline so the index charts have a trend."""
    assert p.poller is not None
    now = utcnow()
    if p.settings.weather_source == "dummy" and p.settings.backfill_hours > 0:
        for step in range(p.settings.backfill_hours * 2, 0, -1):
            await p.poller.poll_weather(at=now - timedelta(minutes=30 * step))
            await p.drain()
    await p.poller.poll_weather()
    await p.drain()
    await p.poller.poll_lightning()
    await p.drain()
    await p.poller.poll_alerts()
    await p.drain()


async def _every(seconds: float, job, name: str) -> None:
    while True:
        await asyncio.sleep(seconds)
        try:
            await job()
        except Exception:
            log.exception("%s failed", name)


async def start_local(p: Pipeline) -> None:
    """Register every service on the in-memory bus, seed, bootstrap, then run the loops."""
    for service in (p.transformer, p.lightning, p.scoring, p.alerts):
        service.register()
    await ensure_seeded(p)
    await attach_poller(p)
    await p.bus.start()
    await bootstrap(p)
    if p.settings.run_pollers:
        p.tasks += [
            asyncio.create_task(p.poller.run()),
            asyncio.create_task(p.lightning.run()),
            asyncio.create_task(_every(300, p.transformer.flag_stale, "stale check")),
        ]


async def stop(p: Pipeline) -> None:
    for task in p.tasks:
        task.cancel()
    await asyncio.gather(*p.tasks, return_exceptions=True)
    await p.bus.stop()
    await p.repo.close()
