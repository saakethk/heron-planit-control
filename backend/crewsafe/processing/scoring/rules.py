"""Rule-based parts of scoring: hazards the model doesn't cover, crew-report
adjustments, the compound index, and the human-readable factor text."""

from __future__ import annotations

from datetime import datetime, timedelta

from ...contracts.api import HazardDriver, HazardFactor
from ...contracts.common import HazardType
from ...contracts.events import Forecast
from ...storage.models import SiteRecord, StoredReport
from ..features import KMH_PER_MPH, MM_PER_IN, THUNDERSTORM_CODES

REPORT_WINDOW = timedelta(hours=6)
WILDLIFE_WINDOW = timedelta(hours=24)


def heat_score(heat_index_f: float) -> float:
    """OSHA/NIOSH heat index bands mapped onto 0-10: 95°F ~1.5, 104°F ~5, 115°F ~9."""
    return round(max(0.0, min(10.0, (heat_index_f - 91) / 2.6)), 1)


def wildlife_score(site: SiteRecord, reports: list[StoredReport], now: datetime) -> tuple[float, StoredReport | None]:
    sightings = [r for r in reports if r.type == HazardType.wildlife and now - r.created_at <= WILDLIFE_WINDOW]
    if not sightings:
        return 0.0, None
    latest = max(sightings, key=lambda r: r.created_at)
    age_hours = (now - latest.created_at).total_seconds() / 3600
    score = 3.5 + 1.0 * min(len(sightings), 3) + site.wildlife_habitat * 2 - age_hours * 0.1
    return round(max(1.0, min(10.0, score)), 1), latest


def report_adjustments(scores: dict[HazardType, float], reports: list[StoredReport],
                       now: datetime) -> list[str]:
    """Recent crew reports raise the matching hazard by half a point each (max +1),
    with a visible reason. Wildlife reports are handled by `wildlife_score`."""
    notes = []
    for hazard in scores:
        if hazard == HazardType.wildlife:
            continue
        matching = [r for r in reports if r.type == hazard and now - r.created_at <= REPORT_WINDOW]
        if matching:
            bump = min(1.0, 0.5 * len(matching))
            scores[hazard] = round(min(10.0, scores[hazard] + bump), 1)
            notes.append(f"+{bump:g} {hazard.value}: {len(matching)} crew report(s) in the last 6 h")
    return notes


def compound_index(scores: dict[HazardType, float]) -> float:
    """The worst hazard drives the index; the second adds a little."""
    top = sorted(scores.values(), reverse=True) + [0.0, 0.0]
    return round(max(0.3, min(10.0, top[0] * 0.78 + top[1] * 0.2)), 1)


def factor_detail(hazard: HazardType, f: dict[str, float], drivers: list[HazardDriver],
                  strike_direction: str | None, wildlife_report: StoredReport | None,
                  flood_zone: str | None = None) -> str:
    if hazard == HazardType.lightning:
        miles = f["nearest_strike_miles"]
        if miles <= 30:
            where = f"{miles:.1f} mi {strike_direction}" if strike_direction else f"{miles:.1f} mi away"
            return f"Lightning {where}" + (", inside the 10 mi radius" if miles <= 10 else "")
        if int(f.get("current_weather_code", 0)) in THUNDERSTORM_CODES:
            return "Thunderstorm reported at the site"
        code = int(f.get("weather_code", 0))
        gusts = round(f.get("wind_gusts_10m_max", f["wind_gust_mph"] * KMH_PER_MPH) / KMH_PER_MPH)
        if code >= 95:
            return "Thunderstorms forecast today"
        if code >= 61:
            return f"{'Showers' if code >= 80 else 'Rain'} today, gusts to {gusts} mph"
        return f"Storms possible (CAPE {round(f['cape'])} J/kg)"
    if hazard == HazardType.heat:
        hi = round(f["heat_index_f"])
        peak = round(f["apparent_temperature_max"] * 9 / 5 + 32) if "apparent_temperature_max" in f else hi
        text = f"Heat index {hi}°F" + (f", up to {peak}°F today" if peak >= hi + 3 else "")
        return text + (", limit exposure to 45 min" if max(hi, peak) >= 105 else "")
    if hazard == HazardType.flood:
        top = max(drivers, key=lambda d: d.contribution).feature if drivers else "rain_24h_in"
        if top == "river_stage_ft_above_flood":
            return f"River {f['river_stage_ft_above_flood']:+.1f} ft vs flood stage"
        if top == "tide_ft_above_mhhw":
            return f"Tide {f['tide_ft_above_mhhw']:.1f} ft above high water"
        today_in = f.get("precipitation_sum", 0.0) / MM_PER_IN
        rain = f"{today_in:.1f} in. of rain today" if today_in > f["rain_24h_in"] \
            else f"{f['rain_24h_in']:.1f} in. of rain in 24 hours"
        if f.get("fema_is_sfha"):
            return f"{rain}, FEMA flood zone {flood_zone}" if flood_zone else f"{rain}, in a FEMA floodplain"
        return rain
    if hazard == HazardType.soil_saturation:
        soil = round(f["soil_moisture_pct"])
        return f"Soil {soil}% saturated" + (", trench walls unstable" if soil >= 85 else "")
    if hazard == HazardType.wildfire:
        if any(d.feature == "drought_index" for d in drivers):
            return f"Dry fuels nearby, KBDI {round(f['drought_index'])}"
        humidity = round(f.get("relative_humidity_2m_min", f["humidity_pct"]))
        gusts = round(f.get("wind_gusts_10m_max", f["wind_gust_mph"] * KMH_PER_MPH) / KMH_PER_MPH)
        return f"Humidity down to {humidity}%, gusts {gusts} mph"
    if hazard == HazardType.wildlife and wildlife_report:
        return wildlife_report.notes.split(".")[0][:80] or "Wildlife reported on site"
    return hazard.value.replace("_", " ").capitalize()


def forecast_headline(forecast: Forecast, scores: dict[HazardType, float]) -> str:
    top = max(scores, key=scores.get)
    if scores[top] < 3:
        text = "No significant hazards expected"
    elif top == HazardType.lightning and forecast.precip_probability >= 30:
        text = f"Storms {round(forecast.precip_probability)}% likely"
    elif top == HazardType.heat:
        text = f"Heat index {round(forecast.max_heat_index_f)}°F; start crews early"
    elif top == HazardType.flood:
        text = f"{forecast.precip_in:.1f} in. of rain expected; watch low areas"
    elif top == HazardType.soil_saturation:
        text = "Saturated soil; delay trenching"
    elif top == HazardType.wildfire:
        text = "Dry and breezy; elevated fire danger"
    else:
        text = "Similar conditions to today"
    if top != HazardType.heat and forecast.max_heat_index_f >= 100:
        text += f"; heat index {round(forecast.max_heat_index_f)}°F"
    return text


def build_factors(scores: dict[HazardType, float], details: dict[HazardType, str], limit: int = 5) -> list[HazardFactor]:
    ranked = sorted(((h, s) for h, s in scores.items() if s >= 0.5), key=lambda x: x[1], reverse=True)[:limit]
    return [HazardFactor(type=h, score=s, detail=details[h]) for h, s in ranked]
