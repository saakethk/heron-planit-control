"""In-memory repository: the dummy store used in local mode and tests.

Data is lost on restart and the seed recreates it. Retention mirrors what the
Postgres tables would keep for the API (8 days of conditions, 1 day of scores).
"""

from __future__ import annotations

import bisect
from collections import defaultdict
from datetime import datetime, timedelta

from ..contracts.api import HazardAlert, IndexPoint, LightningHold, SiteSubscription
from ..contracts.events import CleanConditions, HazardScore
from .models import Decision, DeviceRecord, SiteRecord, StoredReport, UserRecord

CONDITIONS_RETENTION = timedelta(days=8)
SCORE_RETENTION = timedelta(days=1)


class InMemoryRepository:
    def __init__(self) -> None:
        self.sites: dict[int, SiteRecord] = {}
        self.conditions: dict[int, list[CleanConditions]] = defaultdict(list)  # sorted by obs_time
        self.scores: dict[int, list[HazardScore]] = defaultdict(list)  # sorted by computed_at
        self.alerts: dict[str, HazardAlert] = {}
        self.acks: set[tuple[str, str]] = set()
        self.holds: dict[int, LightningHold] = {}
        self.reports: dict[str, StoredReport] = {}
        self.users: dict[str, UserRecord] = {}
        self.devices: dict[str, DeviceRecord] = {}
        self.subscriptions: dict[str, SiteSubscription] = {}
        self.decisions: list[Decision] = []

    async def connect(self) -> None:
        pass

    async def close(self) -> None:
        pass

    async def is_empty(self) -> bool:
        return not self.sites

    # sites
    async def upsert_sites(self, sites: list[SiteRecord]) -> None:
        self.sites.update({s.id: s for s in sites})

    async def list_sites(self) -> list[SiteRecord]:
        return list(self.sites.values())

    async def get_site(self, site_id: int) -> SiteRecord | None:
        return self.sites.get(site_id)

    # conditions
    async def save_conditions(self, conditions: CleanConditions) -> bool:
        rows = self.conditions[conditions.site_id]
        times = [r.obs_time for r in rows]
        i = bisect.bisect_left(times, conditions.obs_time)
        if i < len(rows) and rows[i].obs_time == conditions.obs_time:
            return False
        rows.insert(i, conditions)
        cutoff = conditions.obs_time - CONDITIONS_RETENTION
        while rows and rows[0].obs_time < cutoff:
            rows.pop(0)
        return True

    async def latest_conditions(self, site_id: int) -> CleanConditions | None:
        rows = self.conditions.get(site_id)
        return rows[-1] if rows else None

    async def all_latest_conditions(self) -> dict[int, CleanConditions]:
        return {sid: rows[-1] for sid, rows in self.conditions.items() if rows}

    async def conditions_since(self, site_id: int, since: datetime) -> list[CleanConditions]:
        return [r for r in self.conditions.get(site_id, []) if r.obs_time >= since]

    # scores
    async def save_score(self, score: HazardScore) -> None:
        rows = self.scores[score.site_id]
        times = [r.computed_at for r in rows]
        i = bisect.bisect_left(times, score.computed_at)
        if i < len(rows) and rows[i].computed_at == score.computed_at:
            rows[i] = score
        else:
            rows.insert(i, score)
        cutoff = rows[-1].computed_at - SCORE_RETENTION
        while rows and rows[0].computed_at < cutoff:
            rows.pop(0)

    async def latest_score(self, site_id: int) -> HazardScore | None:
        rows = self.scores.get(site_id)
        return rows[-1] if rows else None

    async def latest_scores(self) -> dict[int, HazardScore]:
        return {sid: rows[-1] for sid, rows in self.scores.items() if rows}

    async def score_history(self, site_id: int, since: datetime) -> list[IndexPoint]:
        return [IndexPoint(time=s.computed_at, value=s.hazard_index)
                for s in self.scores.get(site_id, []) if s.computed_at >= since]

    async def all_score_history(self, since: datetime) -> dict[int, list[IndexPoint]]:
        return {sid: await self.score_history(sid, since) for sid in self.scores}

    # alerts
    async def save_alert(self, alert: HazardAlert) -> bool:
        if alert.id in self.alerts:
            return False
        self.alerts[alert.id] = alert.model_copy(update={"acknowledged": None})
        return True

    async def get_alert(self, alert_id: str) -> HazardAlert | None:
        return self.alerts.get(alert_id)

    async def list_alerts(self, user_id: str, site_ids: list[int] | None, since: datetime | None,
                          limit: int) -> list[HazardAlert]:
        wanted = set(site_ids) if site_ids is not None else None
        rows = [a for a in self.alerts.values()
                if (wanted is None or a.site_id in wanted) and (since is None or a.issued_at >= since)]
        rows.sort(key=lambda a: a.issued_at, reverse=True)
        return [a.model_copy(update={"acknowledged": (a.id, user_id) in self.acks}) for a in rows[:limit]]

    async def acknowledge_alert(self, alert_id: str, user_id: str) -> bool:
        if alert_id not in self.alerts:
            return False
        self.acks.add((alert_id, user_id))
        return True

    async def last_alert_at(self, site_id: int, kind: str) -> datetime | None:
        times = [a.issued_at for a in self.alerts.values() if a.site_id == site_id and a.type == kind]
        return max(times) if times else None

    # holds
    async def upsert_hold(self, hold: LightningHold) -> None:
        self.holds[hold.site_id] = hold

    async def get_hold(self, site_id: int) -> LightningHold | None:
        return self.holds.get(site_id)

    async def delete_hold(self, site_id: int) -> None:
        self.holds.pop(site_id, None)

    async def list_holds(self) -> list[LightningHold]:
        return list(self.holds.values())

    # reports
    async def save_report(self, report: StoredReport) -> bool:
        if report.id in self.reports:
            return False
        self.reports[report.id] = report
        return True

    async def list_reports(self, site_ids: list[int] | None, since: datetime | None, limit: int) -> list[StoredReport]:
        wanted = set(site_ids) if site_ids is not None else None
        rows = [r for r in self.reports.values()
                if (wanted is None or r.site_id in wanted) and (since is None or r.created_at >= since)]
        rows.sort(key=lambda r: r.created_at, reverse=True)
        return rows[:limit]

    # users, devices, subscriptions
    async def upsert_user(self, user: UserRecord) -> None:
        self.users[user.username] = user

    async def get_user(self, username: str) -> UserRecord | None:
        return self.users.get(username)

    async def register_device(self, device: DeviceRecord) -> None:
        self.devices[device.apns_token] = device

    async def devices_for_users(self, user_ids: list[str]) -> list[DeviceRecord]:
        wanted = set(user_ids)
        return [d for d in self.devices.values() if d.user_id in wanted]

    async def save_subscription(self, user_id: str, subscription: SiteSubscription) -> None:
        self.subscriptions[user_id] = subscription

    async def get_subscription(self, user_id: str) -> SiteSubscription | None:
        return self.subscriptions.get(user_id)

    async def subscribers_for_site(self, site_id: int) -> list[str]:
        return [uid for uid, sub in self.subscriptions.items() if site_id in sub.site_ids]

    # audit
    async def log_decision(self, decision: Decision) -> None:
        self.decisions.append(decision.model_copy(update={"id": len(self.decisions) + 1}))
        if len(self.decisions) > 5000:
            del self.decisions[:1000]

    async def list_decisions(self, site_id: int | None, limit: int) -> list[Decision]:
        rows = [d for d in self.decisions if site_id is None or d.site_id == site_id]
        return list(reversed(rows[-limit:]))
