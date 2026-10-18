"""Push delivery. `LogPushSender` is the dummy: it records what would be sent.

For production, implement `PushSender` with APNs (token auth with the `.p8` key
from env vars, never from Git) and fall back to SMS (e.g. Twilio) when APNs
rejects a token or a stop-work alert isn't acknowledged in time.
"""

from __future__ import annotations

import logging
from typing import Protocol

from ...contracts.api import HazardAlert
from ...storage.models import DeviceRecord

log = logging.getLogger(__name__)


class PushSender(Protocol):
    async def send(self, device: DeviceRecord, alert: HazardAlert) -> bool: ...


class LogPushSender:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    async def send(self, device: DeviceRecord, alert: HazardAlert) -> bool:
        self.sent.append((device.apns_token, alert.id))
        log.info("push -> %s…: [%s] %s", device.apns_token[:8], alert.severity, alert.title)
        return True


def apns_payload(alert: HazardAlert) -> dict:
    """APNs body. Stop-work alerts are time-sensitive so they break through Focus."""
    return {
        "aps": {
            "alert": {"title": alert.title, "body": alert.message},
            "sound": "default",
            "interruption-level": "time-sensitive" if alert.severity == "stop_work" else "active",
            "thread-id": f"site-{alert.site_id}",
        },
        "alert_id": alert.id,
        "site_id": alert.site_id,
    }
