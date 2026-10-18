"""Postgres repository (STORAGE=postgres). Tables are in `schema.sql`.

Not exercised by the test suite, which uses the in-memory repository. Run it
against a real Postgres database before relying on it.
"""

from __future__ import annotations

import json
from datetime import datetime

from ..contracts.api import HazardAlert, IndexPoint, LightningHold, SiteSubscription
from ..contracts.events import CleanConditions, HazardScore
from .models import Decision, DeviceRecord, SiteRecord, StoredReport, UserRecord

SITE_COLUMNS = "id, name, county, latitude, longitude, capacity_mw, coastal, near_river, elevation_ft, wildlife_habitat"


class PostgresRepository:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._pool = None

    async def connect(self) -> None:
        from psycopg.rows import dict_row
        from psycopg_pool import AsyncConnectionPool

        self._pool = AsyncConnectionPool(self._dsn, min_size=1, max_size=10, open=False,
                                         kwargs={"row_factory": dict_row})
        await self._pool.open()

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()

    async def _all(self, sql: str, *args) -> list[dict]:
        async with self._pool.connection() as conn:
            cur = await conn.execute(sql, args)
            return await cur.fetchall()

    async def _one(self, sql: str, *args) -> dict | None:
        rows = await self._all(sql, *args)
        return rows[0] if rows else None

    async def _exec(self, sql: str, *args) -> int:
        async with self._pool.connection() as conn:
            cur = await conn.execute(sql, args)
            return cur.rowcount

    async def is_empty(self) -> bool:
        return (await self._one("SELECT count(*) AS n FROM sites"))["n"] == 0

    # sites
    async def upsert_sites(self, sites: list[SiteRecord]) -> None:
        async with self._pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.executemany(
                    f"INSERT INTO sites ({SITE_COLUMNS}) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                    "ON CONFLICT (id) DO UPDATE SET name=EXCLUDED.name, county=EXCLUDED.county, "
                    "latitude=EXCLUDED.latitude, longitude=EXCLUDED.longitude, capacity_mw=EXCLUDED.capacity_mw, "
                    "coastal=EXCLUDED.coastal, near_river=EXCLUDED.near_river, elevation_ft=EXCLUDED.elevation_ft, "
                    "wildlife_habitat=EXCLUDED.wildlife_habitat",
                    [(s.id, s.name, s.county, s.latitude, s.longitude, s.capacity_mw, s.coastal, s.near_river,
                      s.elevation_ft, s.wildlife_habitat) for s in sites])

    async def list_sites(self) -> list[SiteRecord]:
        return [SiteRecord(**r) for r in await self._all(f"SELECT {SITE_COLUMNS} FROM sites ORDER BY id")]

    async def get_site(self, site_id: int) -> SiteRecord | None:
        row = await self._one(f"SELECT {SITE_COLUMNS} FROM sites WHERE id=%s", site_id)
        return SiteRecord(**row) if row else None

    # conditions
    async def save_conditions(self, c: CleanConditions) -> bool:
        return await self._exec(
            "INSERT INTO conditions (site_id, obs_time, source, data_stale, data) VALUES (%s,%s,%s,%s,%s) "
            "ON CONFLICT DO NOTHING",
            c.site_id, c.obs_time, c.source, c.data_stale, c.model_dump_json()) == 1

    async def latest_conditions(self, site_id: int) -> CleanConditions | None:
        row = await self._one("SELECT data FROM conditions WHERE site_id=%s ORDER BY obs_time DESC LIMIT 1", site_id)
        return CleanConditions(**row["data"]) if row else None

    async def all_latest_conditions(self) -> dict[int, CleanConditions]:
        rows = await self._all("SELECT DISTINCT ON (site_id) data FROM conditions ORDER BY site_id, obs_time DESC")
        return {r["data"]["site_id"]: CleanConditions(**r["data"]) for r in rows}

    async def conditions_since(self, site_id: int, since: datetime) -> list[CleanConditions]:
        rows = await self._all("SELECT data FROM conditions WHERE site_id=%s AND obs_time>=%s ORDER BY obs_time",
                               site_id, since)
        return [CleanConditions(**r["data"]) for r in rows]

    # scores
    async def save_score(self, s: HazardScore) -> None:
        await self._exec(
            "INSERT INTO scores (site_id, computed_at, hazard_index, model_version, data_stale, data) "
            "VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (site_id, computed_at) DO UPDATE SET "
            "hazard_index=EXCLUDED.hazard_index, model_version=EXCLUDED.model_version, "
            "data_stale=EXCLUDED.data_stale, data=EXCLUDED.data",
            s.site_id, s.computed_at, s.hazard_index, s.model_version, s.data_stale, s.model_dump_json())

    async def latest_score(self, site_id: int) -> HazardScore | None:
        row = await self._one("SELECT data FROM scores WHERE site_id=%s ORDER BY computed_at DESC LIMIT 1", site_id)
        return HazardScore(**row["data"]) if row else None

    async def latest_scores(self) -> dict[int, HazardScore]:
        rows = await self._all("SELECT DISTINCT ON (site_id) data FROM scores ORDER BY site_id, computed_at DESC")
        return {r["data"]["site_id"]: HazardScore(**r["data"]) for r in rows}

    async def score_history(self, site_id: int, since: datetime) -> list[IndexPoint]:
        rows = await self._all("SELECT computed_at, hazard_index FROM scores WHERE site_id=%s AND computed_at>=%s "
                               "ORDER BY computed_at", site_id, since)
        return [IndexPoint(time=r["computed_at"], value=r["hazard_index"]) for r in rows]

    async def all_score_history(self, since: datetime) -> dict[int, list[IndexPoint]]:
        rows = await self._all("SELECT site_id, computed_at, hazard_index FROM scores WHERE computed_at>=%s "
                               "ORDER BY site_id, computed_at", since)
        history: dict[int, list[IndexPoint]] = {}
        for r in rows:
            history.setdefault(r["site_id"], []).append(IndexPoint(time=r["computed_at"], value=r["hazard_index"]))
        return history

    # alerts
    async def save_alert(self, a: HazardAlert) -> bool:
        return await self._exec(
            "INSERT INTO alerts (id, site_id, type, severity, title, message, issued_at, source) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
            a.id, a.site_id, a.type, a.severity, a.title, a.message, a.issued_at, a.source) == 1

    async def get_alert(self, alert_id: str) -> HazardAlert | None:
        row = await self._one("SELECT * FROM alerts WHERE id=%s", alert_id)
        return HazardAlert(**row) if row else None

    async def list_alerts(self, user_id: str, site_ids: list[int] | None, since: datetime | None,
                          limit: int) -> list[HazardAlert]:
        rows = await self._all(
            "SELECT a.*, (k.alert_id IS NOT NULL) AS acknowledged FROM alerts a "
            "LEFT JOIN alert_acks k ON k.alert_id=a.id AND k.user_id=%s "
            "WHERE (%s::int[] IS NULL OR a.site_id = ANY(%s::int[])) AND (%s::timestamptz IS NULL OR a.issued_at>=%s) "
            "ORDER BY a.issued_at DESC LIMIT %s",
            user_id, site_ids, site_ids, since, since, limit)
        return [HazardAlert(**r) for r in rows]

    async def acknowledge_alert(self, alert_id: str, user_id: str) -> bool:
        if not await self._one("SELECT 1 AS ok FROM alerts WHERE id=%s", alert_id):
            return False
        await self._exec("INSERT INTO alert_acks (alert_id, user_id) VALUES (%s,%s) ON CONFLICT DO NOTHING",
                         alert_id, user_id)
        return True

    async def last_alert_at(self, site_id: int, kind: str) -> datetime | None:
        row = await self._one("SELECT max(issued_at) AS t FROM alerts WHERE site_id=%s AND type=%s", site_id, kind)
        return row["t"] if row else None

    # holds
    async def upsert_hold(self, hold: LightningHold) -> None:
        await self._exec("INSERT INTO lightning_holds (site_id, data) VALUES (%s,%s) "
                         "ON CONFLICT (site_id) DO UPDATE SET data=EXCLUDED.data", hold.site_id, hold.model_dump_json())

    async def get_hold(self, site_id: int) -> LightningHold | None:
        row = await self._one("SELECT data FROM lightning_holds WHERE site_id=%s", site_id)
        return LightningHold(**row["data"]) if row else None

    async def delete_hold(self, site_id: int) -> None:
        await self._exec("DELETE FROM lightning_holds WHERE site_id=%s", site_id)

    async def list_holds(self) -> list[LightningHold]:
        return [LightningHold(**r["data"]) for r in await self._all("SELECT data FROM lightning_holds")]

    # reports
    async def save_report(self, r: StoredReport) -> bool:
        return await self._exec(
            "INSERT INTO reports (id, site_id, type, notes, reporter, created_at, latitude, longitude, photo_url) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
            r.id, r.site_id, r.type, r.notes, r.reporter, r.created_at, r.latitude, r.longitude, r.photo_url) == 1

    async def list_reports(self, site_ids: list[int] | None, since: datetime | None, limit: int) -> list[StoredReport]:
        rows = await self._all(
            "SELECT * FROM reports WHERE (%s::int[] IS NULL OR site_id = ANY(%s::int[])) "
            "AND (%s::timestamptz IS NULL OR created_at>=%s) ORDER BY created_at DESC LIMIT %s",
            site_ids, site_ids, since, since, limit)
        return [StoredReport(**r) for r in rows]

    # users, devices, subscriptions
    async def upsert_user(self, u: UserRecord) -> None:
        await self._exec("INSERT INTO users (username, display_name, password_hash, role) VALUES (%s,%s,%s,%s) "
                         "ON CONFLICT (username) DO UPDATE SET display_name=EXCLUDED.display_name, "
                         "password_hash=EXCLUDED.password_hash, role=EXCLUDED.role",
                         u.username, u.display_name, u.password_hash, u.role)

    async def get_user(self, username: str) -> UserRecord | None:
        row = await self._one("SELECT * FROM users WHERE username=%s", username)
        return UserRecord(**row) if row else None

    async def register_device(self, d: DeviceRecord) -> None:
        await self._exec("INSERT INTO devices (apns_token, user_id, platform, registered_at) VALUES (%s,%s,%s,%s) "
                         "ON CONFLICT (apns_token) DO UPDATE SET user_id=EXCLUDED.user_id, "
                         "registered_at=EXCLUDED.registered_at", d.apns_token, d.user_id, d.platform, d.registered_at)

    async def devices_for_users(self, user_ids: list[str]) -> list[DeviceRecord]:
        return [DeviceRecord(**r) for r in await self._all("SELECT * FROM devices WHERE user_id = ANY(%s)", user_ids)]

    async def save_subscription(self, user_id: str, sub: SiteSubscription) -> None:
        await self._exec("INSERT INTO subscriptions (user_id, data, site_ids) VALUES (%s,%s,%s) "
                         "ON CONFLICT (user_id) DO UPDATE SET data=EXCLUDED.data, site_ids=EXCLUDED.site_ids",
                         user_id, sub.model_dump_json(), sub.site_ids)

    async def get_subscription(self, user_id: str) -> SiteSubscription | None:
        row = await self._one("SELECT data FROM subscriptions WHERE user_id=%s", user_id)
        return SiteSubscription(**row["data"]) if row else None

    async def subscribers_for_site(self, site_id: int) -> list[str]:
        rows = await self._all("SELECT user_id FROM subscriptions WHERE %s = ANY(site_ids)", site_id)
        return [r["user_id"] for r in rows]

    # audit
    async def log_decision(self, d: Decision) -> None:
        await self._exec("INSERT INTO decision_log (created_at, site_id, kind, decision, reason, data) "
                         "VALUES (%s,%s,%s,%s,%s,%s)",
                         d.created_at, d.site_id, d.kind, d.decision, d.reason, json.dumps(d.data))

    async def list_decisions(self, site_id: int | None, limit: int) -> list[Decision]:
        rows = await self._all("SELECT * FROM decision_log WHERE (%s::int IS NULL OR site_id=%s) "
                               "ORDER BY created_at DESC, id DESC LIMIT %s", site_id, site_id, limit)
        return [Decision(**r) for r in rows]
