"""Dummy sources: a small simulated Florida that produces realistic raw payloads.

Weather payloads are shaped exactly like Open-Meteo responses, so they travel the
same transformer -> scoring -> alerts path real data will. Switching to real data
is a settings change (WEATHER_SOURCE=open-meteo), not a code change.

The nine demo sites follow the same story as the app's MockData (Gainesville
lightning hold, Port Everglades storms, Bayboro flooding, Orlando heat...).
Every other site gets stable values seeded by its plant ID.
"""

from __future__ import annotations

import math
import os
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from ...contracts.common import utcnow
from ...contracts.events import RawLightningStrike, RawNwsAlert, RawObservation
from ...geo import COMPASS_BEARING, offset
from ...processing.features import heat_index_f
from ...storage.models import SiteRecord

# Values at the demo hour (2 PM by default).
DEMO_SCENARIOS: dict[int, dict] = {
    664: dict(temp=92, heat_index=104, wind=11, rain_24h=0.8, rain_7d=2.2, soil=66, cape=2800, kbdi=280, storm=0.9),
    617: dict(temp=93, heat_index=108, wind=14, rain_24h=0.3, rain_7d=1.4, soil=58, cape=3000, kbdi=240, storm=0.9,
              tide=1.3),
    627: dict(temp=89, heat_index=101, wind=9, rain_24h=2.9, rain_7d=5.8, soil=94, cape=900, kbdi=60, storm=0.3,
              river=0.9),
    54466: dict(temp=96, heat_index=111, wind=6, rain_24h=0.0, rain_7d=0.3, soil=41, cape=2000, kbdi=430, storm=0.4),
    56518: dict(temp=92, heat_index=99, wind=7, rain_24h=0.2, rain_7d=1.6, soil=52, cape=1500, kbdi=300, storm=0.3),
    619: dict(temp=88, heat_index=97, wind=12, rain_24h=0.6, rain_7d=1.9, soil=61, cape=1300, kbdi=200, storm=0.3,
              tide=0.7),
    50875: dict(temp=90, heat_index=95, wind=8, rain_24h=1.1, rain_7d=3.0, soil=71, cape=800, kbdi=150, storm=0.2),
    136: dict(temp=91, heat_index=92, wind=10, rain_24h=0.0, rain_7d=0.2, soil=33, cape=600, kbdi=520, storm=0.1),
    64546: dict(temp=87, heat_index=90, wind=11, rain_24h=0.1, rain_7d=0.8, soil=45, cape=700, kbdi=180, storm=0.1),
}

# Storm cells already over the demo sites at startup: (site, miles, compass, heading, mph, strikes)
DEMO_CELLS = [
    (664, 6.1, "SW", 45.0, 12.0, [(-6 * 60, 6.8), (-140, 6.1)]),
    (617, 4.2, "NE", 225.0, 15.0, [(-9 * 60, 6.8), (-5 * 60, 3.1), (-106, 4.2)]),
]


def humidity_for(temp_f: float, target_heat_index: float) -> float:
    """Relative humidity that gives the target heat index at this temperature."""
    best, best_err = 50.0, float("inf")
    for rh in range(15, 99):
        err = abs(heat_index_f(temp_f, rh) - target_heat_index)
        if err < best_err:
            best, best_err = float(rh), err
    return best


def diurnal(local_hour: float) -> float:
    """0 at 3 AM, 1 at 3 PM."""
    return 0.5 * (1 + math.cos(2 * math.pi * (local_hour - 15) / 24))


@dataclass
class SiteClimate:
    site: SiteRecord
    max_temp: float
    peak_humidity: float
    wind: float
    rain_24h: float
    rain_7d: float
    soil: float
    cape: float
    kbdi: float
    storm: float  # 0-1, how stormy today is
    tide_ft: float = 0.0
    river_ft: float | None = None
    temp_drift: float = 0.0
    storm_drift: float = 0.0
    recent_rain: float = 0.0


@dataclass
class StormCell:
    latitude: float
    longitude: float
    heading: float
    mph: float
    strikes_per_min: float
    expires_at: datetime
    radius_miles: float = 2.5
    pending: list[tuple[datetime, float, float]] = field(default_factory=list)  # scripted strikes


class DummyWorld:
    def __init__(self, sites: list[SiteRecord], demo_hour: float | None = None, seed: int = 7) -> None:
        self.sites = {s.id: s for s in sites}
        self.rng = random.Random(seed)
        self.started = utcnow()
        env_hour = os.environ.get("DUMMY_DEMO_HOUR", "14")
        self.demo_hour = demo_hour if demo_hour is not None else (float(env_hour) if env_hour else None)
        self.climate = {s.id: self._climate(s) for s in sites}
        self.cells: list[StormCell] = []
        self._seed_cells()

    # -- climate ----------------------------------------------------------

    def _climate(self, site: SiteRecord) -> SiteClimate:
        scenario = DEMO_SCENARIOS.get(site.id)
        if scenario:
            return SiteClimate(
                site=site, max_temp=scenario["temp"] + 0.5,
                peak_humidity=humidity_for(scenario["temp"], scenario["heat_index"]),
                wind=scenario["wind"], rain_24h=scenario["rain_24h"], rain_7d=scenario["rain_7d"],
                soil=scenario["soil"], cape=scenario["cape"], kbdi=scenario["kbdi"], storm=scenario["storm"],
                tide_ft=scenario.get("tide", 0.0), river_ft=scenario.get("river"))
        rng = random.Random(site.id)
        south, panhandle = site.latitude < 27, site.longitude < -84
        max_temp = (91 if south else 88) + rng.randint(0, 6)
        heat_index = max_temp + rng.randint(2, 12)
        rain = round(rng.uniform(0, 2.2 if south else 1.4), 2)
        storm = rng.random() ** 3 * (1.0 if panhandle else 0.85)
        return SiteClimate(
            site=site, max_temp=max_temp, peak_humidity=humidity_for(max_temp, heat_index),
            wind=rng.randint(3, 16), rain_24h=rain, rain_7d=rain + rng.uniform(0, 3.5),
            soil=rng.randint(30, 88), cape=400 + storm * 2800,
            kbdi=rng.randint(350, 650) if panhandle else rng.randint(80, 520), storm=storm,
            tide_ft=rng.uniform(0, 0.8) if site.coastal else 0.0,
            river_ft=rng.uniform(-3, 0.4) if site.near_river else None)

    def local_hour(self, at: datetime) -> float:
        if self.demo_hour is None:
            return ((at.hour - 4) % 24) + at.minute / 60  # Florida, EDT
        return (self.demo_hour + (at - self.started).total_seconds() / 3600) % 24

    def drift(self) -> None:
        """Small random walk between polls so values move like real weather."""
        for c in self.climate.values():
            c.temp_drift = max(-2.5, min(2.5, c.temp_drift + self.rng.gauss(0, 0.25)))
            c.storm_drift = max(-0.15, min(0.15, c.storm_drift + self.rng.gauss(0, 0.02)))
            if self.rng.random() < (c.storm + c.storm_drift) * 0.08:
                c.recent_rain += round(self.rng.uniform(0.05, 0.4), 2)
            c.recent_rain = max(0.0, c.recent_rain * 0.97)

    # -- Open-Meteo shaped payload ---------------------------------------

    def observe(self, site_id: int, at: datetime) -> dict:
        c = self.climate[site_id]
        hour = self.local_hour(at)
        d = diurnal(hour)
        temp = c.max_temp - 15 * (1 - d) + c.temp_drift
        humidity = min(98.0, c.peak_humidity + 32 * (1 - d))
        storminess = max(0.0, min(1.0, c.storm + c.storm_drift))
        wind = max(1.0, c.wind + 4 * (d - 0.5) + self.rng.gauss(0, 1))
        precip_now = round(c.recent_rain * 0.2, 2)

        hour_start = at.replace(minute=0, second=0, microsecond=0)
        hourly_times = [hour_start + timedelta(hours=h) for h in range(-23, 25)]
        rain_24h = c.rain_24h + c.recent_rain
        # Past rain falls mostly overnight; the future gets afternoon showers on stormy days.
        weights = [1 + 3 * (1 - diurnal(self.local_hour(t))) for t in hourly_times[:24]]
        total = sum(weights)
        past_precip = [round(rain_24h * w / total, 3) for w in weights]
        future_precip = [round(storminess * 0.12 * diurnal(self.local_hour(t)), 3) for t in hourly_times[24:]]
        cape = [round(c.cape * (0.25 + 0.75 * diurnal(self.local_hour(t)))) for t in hourly_times]
        soil_m3 = round(min(100.0, c.soil + c.recent_rain * 4) / 100 * 0.45, 3)

        today = at.date()
        days = [today + timedelta(days=i) for i in range(-7, 2)]
        earlier = max(0.0, c.rain_7d - c.rain_24h)
        past_daily = [round(earlier / 6, 2)] * 6 + [round(rain_24h, 2)]
        tomorrow_storm = max(0.0, min(1.0, storminess + self.rng.uniform(-0.2, 0.15)))

        return {
            "latitude": c.site.latitude,
            "longitude": c.site.longitude,
            "current": {
                "time": at.strftime("%Y-%m-%dT%H:%M"),
                "temperature_2m": round(temp, 1),
                "relative_humidity_2m": round(humidity),
                "wind_speed_10m": round(wind, 1),
                "wind_gusts_10m": round(wind * 1.6, 1),
                "precipitation": precip_now,
            },
            "hourly": {
                "time": [t.strftime("%Y-%m-%dT%H:%M") for t in hourly_times],
                "precipitation": past_precip + future_precip,
                "cape": cape,
                "soil_moisture_0_to_1cm": [soil_m3] * len(hourly_times),
            },
            "daily": {
                "time": [day.isoformat() for day in days],
                "temperature_2m_max": [round(c.max_temp + self.rng.uniform(-2, 2), 1) for _ in days],
                "apparent_temperature_max": [round(heat_index_f(c.max_temp, c.peak_humidity) + self.rng.uniform(-2, 3))
                                             for _ in days],
                "precipitation_sum": past_daily + [round(storminess * 0.9, 2), round(tomorrow_storm * 1.1, 2)],
                "precipitation_probability_max": [round(storminess * 100)] * 8 + [round(tomorrow_storm * 100)],
                "wind_gusts_10m_max": [round(c.wind * 2.0, 1)] * len(days),
            },
            # Not from Open-Meteo: stand-ins for the drought index (Florida Forest
            # Service KBDI), USGS river gauges, and NOAA tides.
            "extras": {
                "kbdi": c.kbdi,
                "river_stage_ft_above_flood": c.river_ft,
                "tide_ft_above_mhhw": round(c.tide_ft, 2),
                "tomorrow_max_cape": round(c.cape * (0.6 + tomorrow_storm)),
            },
        }

    # -- lightning --------------------------------------------------------

    def _seed_cells(self) -> None:
        now = self.started
        for site_id, miles, direction, heading, mph, strikes in DEMO_CELLS:
            site = self.sites.get(site_id)
            if not site:
                continue
            lat, lon = offset(site.latitude, site.longitude, miles, COMPASS_BEARING[direction])
            cell = StormCell(lat, lon, heading, mph, strikes_per_min=0.45, expires_at=now + timedelta(minutes=40))
            for seconds_ago, dist in strikes:
                s_lat, s_lon = offset(site.latitude, site.longitude, dist, COMPASS_BEARING[direction])
                cell.pending.append((now + timedelta(seconds=seconds_ago), s_lat, s_lon))
            self.cells.append(cell)

    def _spawn_cells(self, now: datetime) -> None:
        if len(self.cells) >= 6 or self.rng.random() > 0.25:
            return
        candidates = [c for c in self.climate.values() if c.storm > 0.35]
        if not candidates:
            return
        c = self.rng.choices(candidates, weights=[x.storm for x in candidates])[0]
        lat, lon = offset(c.site.latitude, c.site.longitude, self.rng.uniform(8, 20), self.rng.uniform(0, 360))
        self.cells.append(StormCell(
            lat, lon, heading=self.rng.uniform(0, 360), mph=self.rng.uniform(8, 20),
            strikes_per_min=self.rng.uniform(0.2, 0.6), expires_at=now + timedelta(minutes=self.rng.uniform(20, 50))))

    def strikes(self, now: datetime, elapsed_seconds: float) -> list[tuple[datetime, float, float]]:
        out: list[tuple[datetime, float, float]] = []
        for cell in self.cells:
            out.extend(p for p in cell.pending if p[0] <= now)
            cell.pending = [p for p in cell.pending if p[0] > now]
            miles = cell.mph * elapsed_seconds / 3600
            cell.latitude, cell.longitude = offset(cell.latitude, cell.longitude, miles, cell.heading)
            expected = cell.strikes_per_min * elapsed_seconds / 60
            count = int(expected) + (1 if self.rng.random() < expected % 1 else 0)
            for _ in range(count):
                lat, lon = offset(cell.latitude, cell.longitude, self.rng.uniform(0, cell.radius_miles),
                                  self.rng.uniform(0, 360))
                out.append((now - timedelta(seconds=self.rng.uniform(0, elapsed_seconds)), lat, lon))
        self.cells = [c for c in self.cells if c.expires_at > now or c.pending]
        self._spawn_cells(now)
        return sorted(out)

    def stormiest_sites(self, limit: int) -> list[SiteClimate]:
        return sorted(self.climate.values(), key=lambda c: c.storm, reverse=True)[:limit]


class DummyWeatherSource:
    name = "dummy"

    def __init__(self, world: DummyWorld) -> None:
        self.world = world

    async def fetch(self, sites: list[SiteRecord], at: datetime | None = None) -> list[RawObservation]:
        at = at or utcnow()
        if at >= self.world.started:
            self.world.drift()
        return [RawObservation(source=self.name, site_id=s.id, fetched_at=at, payload=self.world.observe(s.id, at))
                for s in sites if s.id in self.world.climate]


class DummyAlertSource:
    """Emits NWS-style alerts that match the simulated weather. Ongoing alerts keep
    the same ID across polls (like NWS), so only the first poll creates an alert."""
    name = "dummy-nws"

    def __init__(self, world: DummyWorld) -> None:
        self.world = world

    async def fetch(self) -> list[RawNwsAlert]:
        now = utcnow()
        day = now.strftime("%Y%m%d")
        alerts: list[RawNwsAlert] = []
        for c in self.world.climate.values():
            hi = heat_index_f(c.max_temp, c.peak_humidity)
            if hi >= 110:
                alerts.append(self._alert(f"heat-{c.site.id}-{day}", "Excessive Heat Warning", "Severe",
                                          f"Heat index up to {round(hi)}°F this afternoon.", c, now))
            if c.tide_ft >= 1.0:
                alerts.append(self._alert(f"tide-{c.site.id}-{day}", "Coastal Flood Advisory", "Minor",
                                          f"Tides {c.tide_ft:.1f} ft above high water. Low docks and vaults may flood.",
                                          c, now))
        # Now and then a new statement for one of the stormiest sites.
        if self.world.rng.random() < 0.3:
            c = self.world.rng.choice(self.world.stormiest_sites(12))
            alerts.append(self._alert(
                f"sps-{c.site.id}-{now:%Y%m%d%H%M}", "Special Weather Statement", "Moderate",
                "Strong thunderstorms with frequent lightning and gusts to 45 mph moving through the area.", c, now))
        return alerts

    @staticmethod
    def _alert(alert_id: str, event: str, severity: str, description: str, c: SiteClimate, now: datetime) -> RawNwsAlert:
        return RawNwsAlert(alert_id=alert_id, event=event, severity=severity, headline=f"{event} for {c.site.county} County",
                           description=description, onset=now, expires=now + timedelta(hours=6), site_ids=[c.site.id])


class DummyLightningSource:
    name = "dummy-lightning"

    def __init__(self, world: DummyWorld) -> None:
        self.world = world
        self._last = world.started - timedelta(minutes=10)
        self._count = 0

    async def fetch(self) -> list[RawLightningStrike]:
        now = utcnow()
        elapsed = min(120.0, (now - self._last).total_seconds())
        self._last = now
        out = []
        for occurred_at, lat, lon in self.world.strikes(now, elapsed):
            self._count += 1
            out.append(RawLightningStrike(strike_id=f"dummy-{now:%H%M%S}-{self._count}", latitude=lat, longitude=lon,
                                          occurred_at=occurred_at, source=self.name))
        return out
