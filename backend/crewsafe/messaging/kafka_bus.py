"""Kafka implementation of `MessageBus` (aiokafka). Used when PIPELINE_MODE=kafka.

At-least-once: offsets are committed only after the handler succeeds, so a crash
replays the message. Handlers must therefore be idempotent (they are: writes are
upserts keyed by site and time).
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from pydantic import BaseModel

from .bus import Handler, MessageBus, encode

log = logging.getLogger(__name__)


class KafkaBus(MessageBus):
    def __init__(self, bootstrap: str, client_id: str = "crewsafe") -> None:
        self._bootstrap = bootstrap
        self._client_id = client_id
        self._producer = None
        self._consumers: list[tuple[Any, Handler]] = []
        self._pending: list[tuple[list[str], str, Handler, bool]] = []
        self._tasks: list[asyncio.Task] = []

    async def publish(self, topic: str, value: BaseModel | dict[str, Any], key: str | int | None = None) -> None:
        assert self._producer is not None, "call start() first"
        await self._producer.send_and_wait(
            topic,
            json.dumps(encode(value)).encode(),
            key=None if key is None else str(key).encode(),
        )

    def subscribe(self, topic_names: list[str], group: str, handler: Handler, latest_only: bool = False) -> None:
        self._pending.append((topic_names, group, handler, latest_only))

    async def start(self) -> None:
        from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

        self._producer = AIOKafkaProducer(
            bootstrap_servers=self._bootstrap, client_id=self._client_id, acks="all", enable_idempotence=True)
        await self._producer.start()
        for topic_names, group, handler, latest_only in self._pending:
            consumer = AIOKafkaConsumer(
                *topic_names,
                bootstrap_servers=self._bootstrap,
                group_id=group,
                enable_auto_commit=False,
                auto_offset_reset="latest" if latest_only else "earliest",
            )
            await consumer.start()
            self._consumers.append((consumer, handler))
            self._tasks.append(asyncio.create_task(self._consume(consumer, group, handler)))

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        for consumer, _ in self._consumers:
            await consumer.stop()
        if self._producer:
            await self._producer.stop()

    async def _consume(self, consumer: Any, group: str, handler: Handler) -> None:
        async for record in consumer:
            key = record.key.decode() if record.key else None
            try:
                value = json.loads(record.value)
            except ValueError as exc:
                await self.dead_letter(record.topic, {"raw": record.value.decode(errors="replace")}, repr(exc))
                await consumer.commit()
                continue
            try:
                await handler(record.topic, key, value)
            except Exception as exc:
                log.exception("%s failed on %s", group, record.topic)
                await self.dead_letter(record.topic, value, f"{group}: {exc!r}")
            await consumer.commit()
