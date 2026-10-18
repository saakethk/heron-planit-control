"""Offline tests for the live-data adapters. No network: synthetic payloads,
the pipeline's local SQLite + model files, and the SAME-code county table."""

from __future__ import annotations

import io
from datetime import UTC, datetime, timedelta

import numpy as np
from conftest import make_settings

from crewsafe.contracts.events import RawLightningStrike, RawNwsAlert
from crewsafe.geo import fl_county_same_code
from crewsafe.ingestion.sources.glm import _file_start, parse_flashes, thin
from crewsafe.messaging import topics
from crewsafe.messaging.bus import InMemoryBus
from crewsafe.pipeline_bridge import load_sites
from crewsafe.processing.features import MODEL_FEATURE_COLUMNS, approximate_model_inputs, build_features
from crewsafe.processing.scoring.model import PipelineHazardModel
from crewsafe.processing.transformer import Transformer, normalize_open_meteo_live
from crewsafe.storage.memory import InMemoryRepository
from crewsafe.storage.models import SiteRecord
from test_pipeline import SITE, collect, run


def test_florida_counties_map_to_same_codes():
    assert fl_county_same_code("Alachua") == "012001"
    assert fl_county_same_code("Miami-Dade") == "012086"
    assert fl_county_same_code("Miami Dade") == "012086"
    assert fl_county_same_code("St. Johns") == "012109"
    assert fl_county_same_code("Saint Lucie") == "012111"
    assert fl_county_same_code("De Soto") == "012027"
    assert fl_county_same_code("Atlantis") is None


def test_nws_same_codes_match_sites_by_county():
    async def scenario():
        bus, repo = InMemoryBus(), InMemoryRepository()
        everglades = SiteRecord(id=617, name="Port Everglades", county="Broward",
                                latitude=26.09, longitude=-80.12, capacity_mw=100)
        await repo.upsert_sites([SITE, everglades])
        Transformer(bus, repo).register()
        clean = collect(bus, topics.CLEAN_NWS_ALERTS)
        await bus.start()
        await bus.publish(topics.RAW_NWS_ALERTS, RawNwsAlert(
            alert_id="nws-1", event="Flood Warning", severity="Severe", headline="Flood",
            same_codes=["012001"]))
        await bus.drain()
        await bus.stop()
        return clean

    matched = run(scenario())
    assert [m["site_id"] for m in matched] == [SITE.id]


def test_glm_file_start_and_thin():
    key = "GLM-L2-LCFA/2026/291/06/OR_GLM-L2-LCFA_G19_s20262910608000_e20262910608200_c20262910608225.nc"
    assert _file_start(key) == datetime(2026, 10, 18, 6, 8, 0, tzinfo=UTC)

    t0 = datetime(2026, 10, 18, 6, 8, tzinfo=UTC)
    a = RawLightningStrike(strike_id="a", latitude=29.65, longitude=-82.32, occurred_at=t0, source="goes-glm")
    b = RawLightningStrike(strike_id="b", latitude=29.651, longitude=-82.321,
                           occurred_at=t0 + timedelta(seconds=20), source="goes-glm")
    far = RawLightningStrike(strike_id="c", latitude=27.0, longitude=-80.0,
                             occurred_at=t0 + timedelta(seconds=10), source="goes-glm")
    kept = thin([a, b, far])
    assert {s.strike_id for s in kept} == {"b", "c"}


def test_glm_parse_keeps_good_flashes_inside_florida():
    buf = io.BytesIO()
    import h5py

    with h5py.File(buf, "w") as f:
        f.create_dataset("flash_lat", data=np.array([29.65, 10.0, 29.7], dtype="f4"))
        f.create_dataset("flash_lon", data=np.array([-82.32, 0.0, -82.3], dtype="f4"))
        f.create_dataset("flash_id", data=np.array([11, 22, 33], dtype="u2"))
        f.create_dataset("flash_quality_flag", data=np.array([0, 0, 1], dtype="i4"))
        offset = f.create_dataset("flash_time_offset_of_first_event", data=np.array([10, 20, 30], dtype="u2"))
        offset.attrs["scale_factor"] = np.array([1.0])
        offset.attrs["add_offset"] = np.array([0.0])
    key = "OR_GLM-L2-LCFA_G19_s20262910608000_e20262910608200_c20262910608225.nc"
    flashes = parse_flashes(buf.getvalue(), key)
    assert len(flashes) == 1
    assert flashes[0].strike_id == "glm-20262910608000-11"
    assert flashes[0].source == "goes-glm"
    assert flashes[0].latitude == 29.65
    assert flashes[0].occurred_at == datetime(2026, 10, 18, 6, 8, 10, tzinfo=UTC)


def _live_payload() -> dict:
    hours = [f"2026-10-18T{h:02d}:00" for h in range(24)]
    days = ["2026-10-16", "2026-10-17", "2026-10-18", "2026-10-19"]
    soil_hours = [f"{d}T{h:02d}:00" for d in days for h in range(24)]
    return {
        "current": {"time": "2026-10-18T15:00", "temperature_2m": 88.0, "relative_humidity_2m": 70.0,
                    "wind_speed_10m": 8.0, "wind_gusts_10m": 14.0, "precipitation": 0.1, "weather_code": 61},
        "hourly": {"time": hours, "precipitation": [0.0] * 7 + [0.1] * 9 + [0.0] * 8, "cape": [200] * 24},
        "model": {
            "daily": {
                "time": days,
                "weather_code": [1, 61, 80, 95],
                "temperature_2m_mean": [24, 25, 26, 27],
                "temperature_2m_max": [28, 29, 31, 32],
                "temperature_2m_min": [20, 21, 22, 23],
                "apparent_temperature_mean": [25, 26, 27, 28],
                "apparent_temperature_max": [30, 31, 33, 34],
                "apparent_temperature_min": [21, 22, 23, 24],
                "precipitation_sum": [0.0, 5.0, 12.7, 8.0],
                "rain_sum": [0.0, 5.0, 12.7, 8.0],
                "precipitation_hours": [0, 3, 6, 4],
                "precipitation_probability_max": [10, 40, 70, 60],
                "wind_speed_10m_max": [20, 22, 25, 28],
                "wind_gusts_10m_max": [35, 40, 45, 50],
                "shortwave_radiation_sum": [18, 16, 14, 12],
                "et0_fao_evapotranspiration": [4.0, 3.8, 3.5, 3.2],
                "relative_humidity_2m_mean": [70, 75, 80, 78],
                "relative_humidity_2m_max": [90, 92, 94, 93],
                "relative_humidity_2m_min": [50, 55, 60, 58],
            },
            "hourly": {
                "time": soil_hours,
                "soil_moisture_3_to_9cm": [0.20] * len(soil_hours),
                "soil_moisture_9_to_27cm": [0.22] * len(soil_hours),
                "soil_moisture_27_to_81cm": [0.24] * len(soil_hours),
                "soil_temperature_18cm": [24.0] * len(soil_hours),
                "soil_temperature_54cm": [23.0] * len(soil_hours),
            },
        },
    }


def test_normalize_open_meteo_live():
    fields = normalize_open_meteo_live(_live_payload())
    assert fields["temperature_f"] == 88.0
    assert fields["rain_24h_in"] == 0.9
    assert fields["weather_code"] == 61
    assert abs(fields["rain_3d_in"] - (0 + 5 + 12.7) / 25.4) < 0.02
    assert 40 < fields["soil_moisture_pct"] < 60
    assert fields["model_inputs"]["snowfall_sum"] == 0.0
    assert fields["model_inputs"]["precipitation_sum"] == 12.7
    assert fields["forecast"].precip_in == round(8.0 / 25.4, 2)  # 0.31
    assert fields["forecast"].model_inputs["weather_code"] == 95


def test_pipeline_sites_join_fema_zones(tmp_path):
    plants = load_sites(make_settings(tmp_path))
    assert plants is not None and len(plants) == 346
    assert all(p["id"] and p["county"] for p in plants)
    zoned = [p for p in plants if p.get("flood_zone")]
    assert len(zoned) == 346
    assert any(p.get("fema_sfha") for p in plants)


def test_pipeline_model_columns_and_gates(tmp_path):
    settings = make_settings(tmp_path, model_kind="pipeline")
    model = PipelineHazardModel(settings)
    assert model.columns == MODEL_FEATURE_COLUMNS
    assert "None" in model.class_names

    calm = _features(temperature_f=72, humidity=55, rain=0.0, cape=50, code=1, heat_index=72)
    storm = _features(temperature_f=86, humidity=80, rain=1.5, cape=2200, code=95, heat_index=92,
                      fema_sfha=True, precipitation_sum=40)

    calm_out = model.predict(calm)
    storm_out = model.predict(storm)
    from crewsafe.contracts.common import HazardType

    assert all(0 <= p.score <= 10 for p in calm_out.values())
    assert storm_out[HazardType.lightning].score >= 8.5  # thunderstorm floor
    assert storm_out[HazardType.flood].score >= 6.5  # SFHA + 25 mm rain
    assert calm_out[HazardType.heat].score < storm_out[HazardType.heat].score
    assert model.gates(calm)[HazardType.heat] == 0.0
    assert model.gates(calm)[HazardType.flood] == 0.0


def _features(*, temperature_f, humidity, rain, cape, code, heat_index, fema_sfha=False,
              precipitation_sum=None) -> dict[str, float]:
    from crewsafe.contracts.events import CleanConditions
    from crewsafe.contracts.common import utcnow

    inputs = approximate_model_inputs(temperature_f, heat_index, humidity, 8, 14, rain, 50, cape)
    inputs["weather_code"] = float(code)
    if precipitation_sum is not None:
        inputs["precipitation_sum"] = precipitation_sum
        inputs["rain_sum"] = precipitation_sum
    site = SiteRecord(id=1, name="t", county="Alachua", latitude=29.65, longitude=-82.32,
                      capacity_mw=1, fema_sfha=fema_sfha, fema_score=0.85 if fema_sfha else 0.05)
    conditions = CleanConditions(
        site_id=1, obs_time=utcnow(), source="test", temperature_f=temperature_f, humidity_pct=humidity,
        heat_index_f=heat_index, wind_mph=8, wind_gust_mph=14, precip_1h_in=0, rain_24h_in=rain,
        rain_3d_in=rain, rain_7d_in=rain, cape=cape, soil_moisture_pct=50, weather_code=code,
        model_inputs=inputs)
    return build_features(conditions, site, 99.0, 0)
