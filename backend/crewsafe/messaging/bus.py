"""Message bus interface with an in-memory implementation.

Services only see `MessageBus`, so the same code runs on the in-memory bus (one
process, no Kafka: the architecture's fallback mode) or on Kafka (`kafka_bus.py`).
Values are JSON-compatible dicts in both cases, so nothing works in memory that
would fail on Kafka.
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from . import topics

log = logging.getLogger(__name__)

Handler = Callable[[str, str | None, dict[str, Any]], Awaitable[None]]


def encode(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    return value.model_dump(mode="json") if isinstance(value, BaseModel) else value


class MessageBus(ABC):
    @abstractmethod
    async def publish(self, topic: str, value: BaseModel | dict[str, Any], key: str | int | None = None) -> None: ...

    @abstractmethod
    def subscribe(self, topic_names: list[str], group: str, handler: Handler, latest_only: bool = False) -> None:
        """Register before `start()`. Each group receives every message once.
        `latest_only` skips history (for consumers that only forward live events)."""

    @abstractmethod
    async def start(self) -> None: ...

    @abstractmethod
    async def stop(self) -> None: ...

    async def dead_letter(self, topic: str, value: dict[str, Any], error: str) -> None:
        log.warning("dead-letter from %s: %s", topic, error)
        await self.publish(topics.DEAD_LETTER, {"topic": topic, "error": error, "value": value})


@dataclass
class _Subscription:
    topics: set[str]
    group: str
    handler: Handler
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    task: asyncio.Task | None = None


class InMemoryBus(MessageBus):
    def __init__(self) -> None:
        self._subs: list[_Subscription] = []
        self._running = False

    async def publish(self, topic: str, value: BaseModel | dict[str, Any], key: str | int | None = None) -> None:
        message = (topic, None if key is None else str(key), encode(value))
        for sub in self._subs:
            if topic in sub.topics:
                sub.queue.put_nowait(message)

    def subscribe(self, topic_names: list[str], group: str, handler: Handler, latest_only: bool = False) -> None:
        sub = _Subscription(set(topic_names), group, handler)
        self._subs.append(sub)
        if self._running:
            sub.task = asyncio.create_task(self._worker(sub))

    async def start(self) -> None:
        self._running = True
        for sub in self._subs:
            if sub.task is None:
                sub.task = asyncio.create_task(self._worker(sub))

    async def stop(self) -> None:
        self._running = False
        for sub in self._subs:
            if sub.task:
                sub.task.cancel()
        await asyncio.gather(*(s.task for s in self._subs if s.task), return_exceptions=True)
        for sub in self._subs:
            sub.task = None

    async def drain(self) -> None:
        """Wait until every message, including ones published by handlers, is processed."""
        while any(s.queue.qsize() or s.queue._unfinished_tasks for s in self._subs):  # noqa: SLF001
            for sub in self._subs:
                await sub.queue.join()

    async def _worker(self, sub: _Subscription) -> None:
        while True:
            topic, key, value = await sub.queue.get()
            try:
                await sub.handler(topic, key, value)
            except Exception as exc:  # one bad message must not stop the consumer
                log.exception("%s failed on %s", sub.group, topic)
                if topic != topics.DEAD_LETTER:
                    await self.dead_letter(topic, value, f"{sub.group}: {exc!r}")
            finally:
                sub.queue.task_done()
