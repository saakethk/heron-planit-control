"""Alert service: decides when something is worth interrupting a crew.

Inputs and rules
- lightning.holds:   hold started -> stop-work alert; extended -> stop-work reminder
                     (at most every 5 min per site); cleared -> advisory.
- clean.nws.alerts:  each NWS alert once per site (alert IDs are stable across polls).
- hazard.scores:     hysteresis (2 consecutive readings over threshold to fire, must
                     fall 1 point below it to re-arm) plus a per-hazard cooldown.
- crew.reports:      advisory to everyone following the site.

Every decision, including suppressions, goes to the decision log.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from ...contracts.api import HazardAlert
from ...contracts.common import AlertSeverity, HazardType, utcnow
from ...contracts.events import CrewReportEvent, HazardScore, HoldEvent, SiteNwsAlert
from ...messaging import topics
from ...messaging.bus import MessageBus
from ...storage.models import Decision
from ...storage.repository import Repository
from .delivery import PushSender

log = logging.getLogger(__name__)

# (fire threshold, consecutive readings, cooldown, title, guidance)
SCORE_RULES: dict[HazardType, tuple[float, int, timedelta, str, str]] = {
    HazardType.heat: (7.5, 2, timedelta(hours=3), "Extreme heat: mandatory rest cycles",
                      "15-minute shaded rest every 45 minutes. Water every 15-20 minutes."),
    HazardType.flood: (7.0, 2, timedelta(hours=3), "Flood risk rising",
                       "Check trench walls before entry and stay out of low vaults."),
    HazardType.soil_saturation: (7.0, 2, timedelta(hours=6), "Soil saturation high",
                                 "Shore excavations deeper than 5 ft."),
    HazardType.wildfire: (6.5, 2, timedelta(hours=6), "Wildfire risk elevated",
                          "No hot work near dry vegetation. Keep extinguishers on trucks."),
}
SEVERE_INDEX = 8.0
SEVERE_COOLDOWN = timedelta(hours=2)
HOLD_REMINDER_EVERY = timedelta(minutes=5)

NWS_TYPES = [("flood", HazardType.flood), ("tide", HazardType.flood), ("surge", HazardType.flood),
             ("heat", HazardType.heat), ("fire", HazardType.wildfire), ("thunderstorm", HazardType.lightning),
             ("special weather", HazardType.lightning), ("tornado", HazardType.other)]


def _ts(value) -> int:
    return int(value.timestamp())


class AlertService:
    def __init__(self, bus: MessageBus, repo: Repository, push: PushSender) -> None:
        self.bus, self.repo, self.push = bus, repo, push
        self._over: dict[tuple[int, str], int] = {}  # consecutive readings over threshold
        self._armed: dict[tuple[int, str], bool] = {}
        self._last_reminder: dict[int, Any] = {}

    def register(self) -> None:
        self.bus.subscribe([topics.HAZARD_SCORES, topics.CLEAN_NWS_ALERTS, topics.LIGHTNING_HOLDS, topics.CREW_REPORTS],
                           "alerts", self.handle)

    async def handle(self, topic: str, key: str | None, value: dict[str, Any]) -> None:
        if topic == topics.LIGHTNING_HOLDS:
            await self.on_hold(HoldEvent(**value))
        elif topic == topics.CLEAN_NWS_ALERTS:
            await self.on_nws(SiteNwsAlert(**value))
        elif topic == topics.HAZARD_SCORES:
            await self.on_score(HazardScore(**value))
        elif topic == topics.CREW_REPORTS:
            await self.on_report(CrewReportEvent(**value))

    # -- inputs -----------------------------------------------------------

    async def on_hold(self, e: HoldEvent) -> None:
        h = e.hold
        minutes = round(h.all_clear_interval / 60)
        if e.event == "started":
            await self.issue(HazardAlert(
                id=f"hold-{h.site_id}-{_ts(h.started_at)}", site_id=h.site_id, type=HazardType.lightning,
                severity=AlertSeverity.stop_work, title=f"Stop work: lightning {h.last_distance_miles:.1f} mi away",
                message=f"First strike within 10 mi ({h.last_direction}). Stop work and move to trucks or a building. "
                        f"All clear in {minutes}:00 if there are no more strikes.",
                issued_at=e.at, source="Lightning network"), reason="strike inside 10 mi started a hold")
            self._last_reminder[h.site_id] = e.at
        elif e.event == "extended":
            last = self._last_reminder.get(h.site_id)
            if last and e.at - last < HOLD_REMINDER_EVERY:
                await self.decide(h.site_id, "lightning", "suppressed", "hold reminder sent within 5 min",
                                  {"distance": h.last_distance_miles})
                return
            self._last_reminder[h.site_id] = e.at
            await self.issue(HazardAlert(
                id=f"hold-{h.site_id}-{_ts(h.last_strike_at)}", site_id=h.site_id, type=HazardType.lightning,
                severity=AlertSeverity.stop_work, title=f"Stop work: lightning {h.last_distance_miles:.1f} mi away",
                message=f"New strike {h.last_direction}. Stay sheltered. The all-clear timer restarted: {minutes}:00.",
                issued_at=e.at, source="Lightning network"), reason="strike inside 10 mi restarted the timer")
        elif e.event == "cleared":
            self._last_reminder.pop(h.site_id, None)
            await self.issue(HazardAlert(
                id=f"clear-{h.site_id}-{_ts(h.started_at)}", site_id=h.site_id, type=HazardType.lightning,
                severity=AlertSeverity.advisory, title="Lightning hold cleared",
                message=f"No strikes within 10 mi for {minutes} minutes. Work can resume.",
                issued_at=e.at, source="Lightning network"), reason="all-clear timer elapsed")

    async def on_nws(self, a: SiteNwsAlert) -> None:
        event = a.event.lower()
        hazard = next((h for word, h in NWS_TYPES if word in event), HazardType.other)
        severity = AlertSeverity.warning if a.severity in {"Extreme", "Severe"} or "warning" in event \
            else AlertSeverity.advisory
        await self.issue(HazardAlert(
            id=f"nws-{a.alert_id}-{a.site_id}", site_id=a.site_id, type=hazard, severity=severity, title=a.event,
            message=a.description or a.headline, issued_at=a.onset or utcnow(), source="NWS"),
            reason=f"NWS {a.event}")

    async def on_score(self, s: HazardScore) -> None:
        if s.backfill:
            return
        by_type = {f.type: f for f in s.factors}
        for hazard, (threshold, needed, cooldown, title, guidance) in SCORE_RULES.items():
            factor = by_type.get(hazard)
            score = factor.score if factor else 0.0
            key = (s.site_id, hazard.value)
            if score < threshold - 1.0:
                self._armed[key] = True
            if score < threshold:
                self._over[key] = 0
                continue
            self._over[key] = self._over.get(key, 0) + 1
            if self._over[key] < needed or not self._armed.get(key, True):
                continue
            last = await self.repo.last_alert_at(s.site_id, hazard.value)
            if last and s.computed_at - last < cooldown:
                await self.decide(s.site_id, hazard.value, "suppressed", "cooldown", {"score": score})
                continue
            self._armed[key] = False
            await self.issue(HazardAlert(
                id=f"model-{hazard.value}-{s.site_id}-{_ts(s.computed_at)}", site_id=s.site_id, type=hazard,
                severity=AlertSeverity.warning, title=title, message=f"{factor.detail}. {guidance}",
                issued_at=s.computed_at, source="Hazard model"),
                reason=f"{hazard.value} {score} >= {threshold} for {needed} readings")

        if s.hazard_index >= SEVERE_INDEX and s.factors:
            top = s.factors[0]
            last = await self.repo.last_alert_at(s.site_id, top.type)
            if not last or s.computed_at - last >= SEVERE_COOLDOWN:
                await self.issue(HazardAlert(
                    id=f"severe-{s.site_id}-{_ts(s.computed_at)}", site_id=s.site_id, type=top.type,
                    severity=AlertSeverity.warning, title=f"Hazard index severe: {s.hazard_index:.1f}",
                    message=f"Driven by {top.detail.lower()}. Review the site briefing before continuing work.",
                    issued_at=s.computed_at, source="Hazard model"), reason=f"index {s.hazard_index} >= {SEVERE_INDEX}")

    async def on_report(self, r: CrewReportEvent) -> None:
        if r.site_id is None:
            return
        label = r.type.replace("_", " ")
        await self.issue(HazardAlert(
            id=f"report-{r.id}", site_id=r.site_id, type=r.type, severity=AlertSeverity.advisory,
            title=f"Crew report: {label}", message=r.notes or f"{label.capitalize()} reported by {r.reporter}.",
            issued_at=r.created_at, source="Crew report"), reason=f"crew report by {r.reporter}")

    # -- output -----------------------------------------------------------

    async def issue(self, alert: HazardAlert, reason: str) -> None:
        if not await self.repo.save_alert(alert):
            return  # already issued (redelivered message)
        await self.bus.publish(topics.ALERTS_ISSUED, alert, key=alert.site_id)
        users = await self.repo.subscribers_for_site(alert.site_id)
        devices = await self.repo.devices_for_users(users) if users else []
        delivered = 0
        for device in devices:
            delivered += bool(await self.push.send(device, alert))
        await self.decide(alert.site_id, alert.type, "issued", reason,
                          {"alert_id": alert.id, "severity": alert.severity, "pushed_to": delivered})

    async def decide(self, site_id: int, kind: str, decision: str, reason: str, data: dict[str, Any]) -> None:
        await self.repo.log_decision(Decision(created_at=utcnow(), site_id=site_id, kind=str(kind),
                                              decision=decision, reason=reason, data=data))
