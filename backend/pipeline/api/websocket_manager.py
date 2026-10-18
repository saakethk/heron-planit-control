"""WebSocket Connection Manager for PlanIT Control.

Handles:
1. Global broadcast channel (/ws/hazards)
2. Per-site filtered channels (/ws/sites/{plant_id})
3. Thread-safe subscriber loop that consumes events from EventStreamPublisher
   and broadcasts them asynchronously to active WebSocket clients.
"""

import asyncio
from collections import defaultdict
import json
import threading
from typing import Any, Dict, List, Set


class WebSocketConnectionManager:
    """Manages active WebSockets and multiplexes events across channels."""

    def __init__(self):
        # Global subscribers: set of WebSocket objects
        self.active_connections: Set[Any] = set()
        # Per-site subscribers: plant_id -> set of WebSocket objects
        self.site_connections: Dict[int, Set[Any]] = defaultdict(set)
        self.lock = threading.Lock()

    async def connect_global(self, websocket: Any):
        await websocket.accept()
        with self.lock:
            self.active_connections.add(websocket)

    def disconnect_global(self, websocket: Any):
        with self.lock:
            self.active_connections.discard(websocket)

    async def connect_site(self, plant_id: int, websocket: Any):
        await websocket.accept()
        with self.lock:
            self.site_connections[plant_id].add(websocket)

    def disconnect_site(self, plant_id: int, websocket: Any):
        with self.lock:
            self.site_connections[plant_id].discard(websocket)
            if not self.site_connections[plant_id]:
                del self.site_connections[plant_id]

    async def broadcast_event(self, event_data: Dict[str, Any]):
        """Dispatches an event to all global subscribers and matching site subscribers."""
        msg_str = json.dumps(event_data) if isinstance(event_data, dict) else str(event_data)
        plant_id = event_data.get("plant_id") if isinstance(event_data, dict) else None

        # 1. Send to global broadcast connections
        dead_global = []
        with self.lock:
            global_targets = list(self.active_connections)
        for ws in global_targets:
            try:
                await ws.send_text(msg_str)
            except Exception:
                dead_global.append(ws)

        if dead_global:
            with self.lock:
                for ws in dead_global:
                    self.active_connections.discard(ws)

        # 2. Send to site-specific connections if applicable
        if plant_id is not None:
            dead_site = []
            with self.lock:
                site_targets = list(self.site_connections.get(plant_id, set()))
            for ws in site_targets:
                try:
                    await ws.send_text(msg_str)
                except Exception:
                    dead_site.append(ws)

            if dead_site:
                with self.lock:
                    for ws in dead_site:
                        self.site_connections[plant_id].discard(ws)


ws_manager = WebSocketConnectionManager()
