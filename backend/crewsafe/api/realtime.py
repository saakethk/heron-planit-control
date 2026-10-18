"""WebSocket hub: forwards pipeline output to connected apps.

Protocol (matches the app's WebSocketRealtimeService):
- app -> server: {"type": "subscribe", "payload": {"site_ids": [...],
                  "include_severe_statewide": true, "last_seq": 41}}
                 {"type": "ping"}
- server -> app: {"type": ..., "seq": n, "payload": {...}}

Every forwarded event gets a global, increasing `seq`. On reconnect the app sends
the last `seq` it saw; missed events are replayed from a ring buffer, or
`resync_required` is sent if they have fallen out of it (the app then reloads
over REST). Index updates are collected for 0.5 s and sent as one
`hazard_index_batch`, so rescoring 300 sites is one message, not 300.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from ..contracts.api import HazardAlert, HazardIndexUpdate, LightningStrike, SubscribePayload
from ..contracts.common import AlertSeverity
from ..contracts.events import CrewReportEvent, HazardScore, HoldEvent, SiteStrike
from ..messaging import topics
from ..messaging.bus import MessageBus

log = logging.getLogger(__name__)

SEVERE_INDEX = 8.0
BATCH_SECONDS = 0.5
BUFFER_SIZE = 2000


@dataclass
class Event:
    seq: int
    type: str
    payload: dict[str, Any]
    site_id: int | None
    severe: bool


@dataclass(eq=False)
class Client:
    socket: WebSocket
    site_ids: set[int] = field(default_factory=set)
    statewide: bool = True
    subscribed: bool = False
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def wants(self, event: Event) -> bool:
        if not self.subscribed:
            return False
        if event.site_id is None or event.site_id in self.site_ids:
            return True
        return self.statewide and event.severe


class RealtimeHub:
    def __init__(self) -> None:
        self.clients: set[Client] = set()
        self.seq = 0
        self.buffer: deque[Event] = deque(maxlen=BUFFER_SIZE)
        self._pending_scores: list[Event] = []
        self._flush_task: asyncio.Task | None = None

    def register(self, bus: MessageBus) -> None:
        # A unique group per API instance: every instance must see every event.
        bus.subscribe([topics.HAZARD_SCORES, topics.ALERTS_ISSUED, topics.LIGHTNING_SITE_STRIKES,
                       topics.LIGHTNING_HOLDS, topics.CREW_REPORTS], f"api-realtime-{uuid.uuid4().hex[:8]}",
                      self.handle, latest_only=True)

    # -- pipeline -> events ----------------------------------------------

    async def handle(self, topic: str, key: str | None, value: dict[str, Any]) -> None:
        if topic == topics.HAZARD_SCORES:
            score = HazardScore(**value)
            if score.backfill:
                return
            update = HazardIndexUpdate(site_id=score.site_id, hazard_index=score.hazard_index, factors=score.factors)
            event = self._record("hazard_index_updated", update.model_dump(mode="json"), score.site_id,
                                 score.hazard_index >= SEVERE_INDEX)
            self._pending_scores.append(event)
            if self._flush_task is None or self._flush_task.done():
                self._flush_task = asyncio.create_task(self._flush_scores_later())
        elif topic == topics.ALERTS_ISSUED:
            alert = HazardAlert(**value)
            await self._broadcast(self._record("alert", alert.model_dump(mode="json"), alert.site_id,
                                               alert.severity == AlertSeverity.stop_work))
        elif topic == topics.LIGHTNING_SITE_STRIKES:
            strike = SiteStrike(**value)
            payload = LightningStrike(site_id=strike.site_id, distance_miles=strike.distance_miles,
                                      occurred_at=strike.occurred_at, direction=strike.direction)
            await self._broadcast(self._record("lightning_strike", payload.model_dump(mode="json"), strike.site_id,
                                               strike.inside_stop_work_radius))
        elif topic == topics.LIGHTNING_HOLDS:
            hold_event = HoldEvent(**value)
            kind = "lightning_hold_cleared" if hold_event.event == "cleared" else "lightning_hold_updated"
            await self._broadcast(self._record(kind, hold_event.hold.model_dump(mode="json"), hold_event.site_id, True))
        elif topic == topics.CREW_REPORTS:
            report = CrewReportEvent(**value)
            payload = report.model_dump(mode="json", exclude={"latitude", "longitude"})
            await self._broadcast(self._record("report_created", payload, report.site_id, False))

    def _record(self, kind: str, payload: dict[str, Any], site_id: int | None, severe: bool) -> Event:
        self.seq += 1
        event = Event(self.seq, kind, payload, site_id, severe)
        self.buffer.append(event)
        return event

    async def _flush_scores_later(self) -> None:
        await asyncio.sleep(BATCH_SECONDS)
        events, self._pending_scores = self._pending_scores, []
        for client in list(self.clients):
            await self._send_scores(client, [e for e in events if client.wants(e)])

    async def _send_scores(self, client: Client, events: list[Event]) -> None:
        latest: dict[int, Event] = {}
        for event in events:
            latest[event.site_id] = event
        if not latest:
            return
        seq = max(e.seq for e in events)
        if len(latest) == 1:
            (event,) = latest.values()
            await self._send(client, {"type": "hazard_index_updated", "seq": seq, "payload": event.payload})
        else:
            await self._send(client, {"type": "hazard_index_batch", "seq": seq,
                                      "payload": {"updates": [e.payload for e in latest.values()]}})

    async def _broadcast(self, event: Event) -> None:
        for client in list(self.clients):
            if client.wants(event):
                await self._send(client, {"type": event.type, "seq": event.seq, "payload": event.payload})

    async def _send(self, client: Client, message: dict[str, Any]) -> None:
        try:
            async with client.lock:
                await client.socket.send_text(json.dumps(message))
        except Exception:
            self.clients.discard(client)

    # -- connection ------------------------------------------------------

    async def serve(self, socket: WebSocket) -> None:
        await socket.accept()
        client = Client(socket)
        self.clients.add(client)
        try:
            while True:
                try:
                    message = json.loads(await socket.receive_text())
                except ValueError:
                    await self._send(client, {"type": "error", "payload": {"detail": "invalid JSON"}})
                    continue
                kind = message.get("type")
                if kind == "subscribe":
                    await self._subscribe(client, SubscribePayload(**(message.get("payload") or {})))
                elif kind == "ping":
                    await self._send(client, {"type": "pong", "seq": self.seq})
                else:
                    await self._send(client, {"type": "error", "payload": {"detail": f"unknown type {kind!r}"}})
        except WebSocketDisconnect:
            pass
        finally:
            self.clients.discard(client)

    async def _subscribe(self, client: Client, sub: SubscribePayload) -> None:
        client.site_ids = set(sub.site_ids)
        client.statewide = sub.include_severe_statewide
        client.subscribed = True
        if sub.last_seq is not None and sub.last_seq < self.seq:
            await self._replay(client, sub.last_seq)
        # Sent last: its seq is the newest, so the app resumes from here next time.
        await self._send(client, {"type": "subscribed", "seq": self.seq,
                                  "payload": {"site_ids": sorted(client.site_ids),
                                              "include_severe_statewide": client.statewide}})

    async def _replay(self, client: Client, last_seq: int) -> None:
        oldest = self.buffer[0].seq if self.buffer else self.seq + 1
        if last_seq < oldest - 1:
            await self._send(client, {"type": "resync_required", "seq": self.seq,
                                      "payload": {"reason": "missed events are no longer buffered"}})
            return
        missed = [e for e in self.buffer if e.seq > last_seq and client.wants(e)]
        await self._send_scores(client, [e for e in missed if e.type == "hazard_index_updated"])
        for event in missed:
            if event.type != "hazard_index_updated":
                await self._send(client, {"type": event.type, "seq": event.seq, "payload": event.payload})
