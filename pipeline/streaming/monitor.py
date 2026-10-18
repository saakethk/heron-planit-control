"""Real-Time Site Hazard Monitor & Streaming Inference Engine.

Integrates:
1. 346 operating Florida power plant job sites from EIA-860M.
2. Real-time meteorological stream from Open-Meteo with live timestamps.
3. Official NOAA National Weather Service (NWS) Active Hazards API (api.weather.gov).
4. Official FEMA National Flood Hazard Layer (NFHL) Layer 28 flood zones.
5. Trained Multi-Hazard ML Model (yielding the 0-10 Hazard Index).
6. Deterministic Safety Alerts (10-mile lightning rule, heat index warnings, flash floods).
7. Crowd-sourced crew hazard reports (wildlife sightings, mud/muck).
"""

from datetime import datetime
from pathlib import Path
import sqlite3
import time
from typing import Any, Dict, List, Optional, Tuple, Union
import joblib
import numpy as np
import pandas as pd

from pipeline.streaming.live_weather import LiveWeatherClient
from pipeline.streaming.nws_alerts import NWSAlertsClient

CLASSES = ["None", "Extreme Heat", "Flood", "Lightning", "Wildfire"]


class SiteHazardMonitor:
    """Production monitor evaluating live environmental conditions across Florida job sites."""

    def __init__(
        self,
        db_path: Optional[Union[str, Path]] = None,
        model_dir: Optional[Union[str, Path]] = None,
    ):
        if db_path is None:
            db_path = Path(__file__).resolve().parent.parent / "data" / "incidents.db"
        self.db_path = Path(db_path)

        if model_dir is None:
            model_dir = Path(__file__).resolve().parent.parent / "model" / "artifacts"
        self.model_dir = Path(model_dir)

        # Load ML model and scaler
        model_path = self.model_dir / "best_hazard_model.joblib"
        scaler_path = self.model_dir / "hazard_scaler.joblib"

        if not model_path.exists():
            raise FileNotFoundError(f"Trained model not found at {model_path}. Run benchmark first.")

        self.model = joblib.load(model_path)
        self.scaler = joblib.load(scaler_path) if scaler_path.exists() else None

        # Live external API clients
        self.weather_client = LiveWeatherClient()
        self.nws_client = NWSAlertsClient()

        self._init_crew_reports_table()

    def _init_crew_reports_table(self):
        """Ensures crew hazard reporting table exists in SQLite."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS crew_hazard_reports (
                    report_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    plant_id INTEGER,
                    reported_by TEXT,
                    hazard_type TEXT,
                    description TEXT,
                    latitude REAL,
                    longitude REAL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    photo_url TEXT
                )
            """)

    def get_florida_plants(self, min_capacity_mw: float = 0.0, limit: Optional[int] = None) -> pd.DataFrame:
        """Retrieves Florida power plant job sites from EIA-860M."""
        with sqlite3.connect(self.db_path) as conn:
            query = f"""
                SELECT plant_id, plant_name, utility_name, county, latitude, longitude, technology, capacity_mw
                FROM monitored_sites
                WHERE capacity_mw >= {min_capacity_mw}
                ORDER BY capacity_mw DESC
            """
            if limit:
                query += f" LIMIT {limit}"
            return pd.read_sql(query, conn)

    def extract_features_from_live_feed(
        self,
        lat: float,
        lon: float,
        live_data: Dict[str, Any],
    ) -> np.ndarray:
        """Transforms live API response into the standardized 28 model features."""
        daily = live_data["daily_aggregates"]
        hourly = live_data["hourly_samples"]

        t_mean = daily.get("temperature_2m_mean", [live_data["temperature_c"]])[0]
        t_max = daily.get("temperature_2m_max", [live_data["temperature_c"]])[0]
        t_min = daily.get("temperature_2m_min", [live_data["temperature_c"]])[0]
        at_mean = daily.get("apparent_temperature_mean", [live_data["apparent_temp_c"]])[0]
        at_max = daily.get("apparent_temperature_max", [live_data["apparent_temp_c"]])[0]
        at_min = daily.get("apparent_temperature_min", [live_data["apparent_temp_c"]])[0]
        precip = daily.get("precipitation_sum", [0.0])[0]
        rain = daily.get("rain_sum", [0.0])[0]
        snow = daily.get("snowfall_sum", [0.0])[0]
        precip_hrs = daily.get("precipitation_hours", [0.0])[0]
        wind_max = daily.get("wind_speed_10m_max", [live_data["wind_speed_kmh"]])[0]
        gust_max = daily.get("wind_gusts_10m_max", [live_data["wind_gusts_kmh"]])[0]
        solar = daily.get("shortwave_radiation_sum", [15.0])[0]
        et0 = daily.get("et0_fao_evapotranspiration", [3.5])[0]
        wcode = float(live_data["weather_code"])

        rh_vals = hourly.get("relative_humidity_2m", [live_data["relative_humidity"]])
        rh_mean = float(np.mean(rh_vals))
        rh_max = float(np.max(rh_vals))
        rh_min = float(np.min(rh_vals))

        sm_vals = hourly.get("soil_moisture_0_to_1cm", [0.25])
        sm_mean = float(np.mean(sm_vals))
        st_vals = hourly.get("soil_temperature_0cm", [t_mean])
        st_mean = float(np.mean(st_vals))

        # Cyclical month
        m = datetime.now().month
        m_sin = np.sin(2 * np.pi * m / 12.0)
        m_cos = np.cos(2 * np.pi * m / 12.0)

        # Lookup FEMA Flood Risk from database
        with sqlite3.connect(self.db_path) as conn:
            fema_row = conn.execute(
                "SELECT is_sfha, is_coastal_hazard, fema_flood_risk_score FROM fema_flood_risk WHERE Latitude = ? AND Longitude = ?",
                (round(lat, 4), round(lon, 4)),
            ).fetchone()

        is_sfha, is_coastal, fema_score = fema_row if fema_row else (0, 0, 0.05)
        fema_precip_compound = fema_score * precip

        feature_vector = np.array([
            t_mean, t_max, t_min, at_mean, at_max, at_min,
            precip, rain, snow, precip_hrs, rh_mean, rh_max, rh_min,
            wind_max, gust_max, solar, et0, sm_mean, st_mean, wcode,
            m_sin, m_cos, lat, lon, is_sfha, is_coastal, fema_score, fema_precip_compound
        ]).reshape(1, -1)

        return feature_vector, {
            "fema_is_sfha": bool(is_sfha),
            "fema_is_coastal": bool(is_coastal),
            "fema_risk_score": fema_score,
        }

    def evaluate_site(
        self,
        lat: float,
        lon: float,
        site_name: str = "Job Site",
        check_nws_alerts: bool = True,
        external_lightning_distance_miles: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Evaluates live environmental hazards for a specific Florida job site."""
        # 1. Fetch genuine live weather from Open-Meteo
        live_data = self.weather_client.fetch_current_conditions(lat, lon)

        # 2. Extract standardized 28 features and query FEMA flood layer
        X, fema_info = self.extract_features_from_live_feed(lat, lon, live_data)

        # 3. Model Inference (GBDT Multi-Hazard)
        probs = self.model.predict_proba(X)[0]
        p_hazard = float(1.0 - probs[0])  # P(Hazard vs Control)
        hazard_index = round(p_hazard * 10.0, 1)

        top_class_idx = int(np.argmax(probs))
        primary_hazard = CLASSES[top_class_idx]

        # 4. Check live NOAA NWS active alerts for this coordinate
        active_nws_alerts = []
        if check_nws_alerts:
            active_nws_alerts = self.nws_client.get_point_active_alerts(lat, lon)

        # 5. Deterministic Operational Safety Rule Evaluation
        alert_status = "NORMAL"
        alert_message = "All environmental parameters within safe operating thresholds."

        # Rule A: Active NWS Flash Flood or Flood Warning
        nws_flood_alerts = [a for a in active_nws_alerts if "Flood" in a.get("event", "")]
        if nws_flood_alerts:
            alert_status = "STOP_WORK"
            alert_message = f"OFFICIAL NWS WARNING: {nws_flood_alerts[0]['event']} - {nws_flood_alerts[0]['headline']}"
            hazard_index = max(hazard_index, 9.5)

        # Rule B: Lightning Stop-Work Rule
        # Detected via live NWS Severe Thunderstorm Warning, live convective WMO code, or field strike feed
        nws_storm_alerts = [a for a in active_nws_alerts if "Thunderstorm" in a.get("event", "")]
        if nws_storm_alerts:
            alert_status = "STOP_WORK"
            alert_message = f"STOP-WORK (LIGHTNING DANGER): Active NWS Severe Thunderstorm Warning in sector."
            hazard_index = max(hazard_index, 9.0)
        elif live_data["is_thunderstorm"]:
            alert_status = "STOP_WORK"
            alert_message = f"STOP-WORK: Live radar/sensor reports active thunderstorm (WMO {live_data['weather_code']})."
            hazard_index = max(hazard_index, 9.0)
        elif external_lightning_distance_miles is not None and external_lightning_distance_miles <= 10.0:
            alert_status = "STOP_WORK"
            alert_message = (
                f"STOP-WORK: Strike detected {external_lightning_distance_miles:.1f} mi from site "
                f"(10-mile safety rule). 30-min countdown active."
            )
            hazard_index = max(hazard_index, 9.0)

        # Rule C: Extreme Heat Safety
        elif live_data["apparent_temp_f"] is not None and live_data["apparent_temp_f"] >= 115.0:
            alert_status = "STOP_WORK"
            alert_message = f"DANGER: Heat Index reaches {live_data['apparent_temp_f']}°F. Mandatory work cessation."
            hazard_index = max(hazard_index, 9.0)
        elif live_data["apparent_temp_f"] is not None and live_data["apparent_temp_f"] >= 105.0:
            alert_status = "ADVISORY"
            alert_message = f"HEAT ADVISORY: Heat Index is {live_data['apparent_temp_f']}°F. Mandatory 15-min rest/hydration."
            hazard_index = max(hazard_index, 7.0)

        # Rule D: FEMA Floodplain Heavy Rain Interaction
        elif fema_info["fema_is_sfha"] and live_data["precipitation_rate_mm"] >= 25.0:
            alert_status = "ADVISORY"
            alert_message = "FLOOD ADVISORY: Heavy precipitation in FEMA 100-year Special Flood Hazard Area (Zone A/AE)."
            hazard_index = max(hazard_index, 7.5)

        return {
            "site_name": site_name,
            "latitude": lat,
            "longitude": lon,
            "data_timestamp": live_data["observation_timestamp"],
            "hazard_index": hazard_index,
            "alert_status": alert_status,
            "alert_message": alert_message,
            "primary_hazard": primary_hazard,
            "probabilities": {CLASSES[i]: round(float(probs[i]), 3) for i in range(len(CLASSES))},
            "live_metrics": {
                "temperature_c": live_data["temperature_c"],
                "apparent_temp_f": live_data["apparent_temp_f"],
                "relative_humidity": live_data["relative_humidity"],
                "precipitation_rate_mm": live_data["precipitation_rate_mm"],
                "wind_gusts_kmh": live_data["wind_gusts_kmh"],
                "weather_code": live_data["weather_code"],
            },
            "fema_risk": fema_info,
            "active_nws_alerts_count": len(active_nws_alerts),
            "nws_alerts": active_nws_alerts,
        }

    def rank_florida_sites(self, top_n: int = 50) -> pd.DataFrame:
        """Evaluates and ranks Florida power plant sites by the 0-10 Hazard Index."""
        plants = self.get_florida_plants(limit=top_n)
        results = []

        print(f"[MONITOR] Streaming environmental conditions for {len(plants)} Florida power plant sites...")
        for _, p in plants.iterrows():
            try:
                res = self.evaluate_site(
                    lat=p["latitude"],
                    lon=p["longitude"],
                    site_name=p["plant_name"],
                    check_nws_alerts=False,  # Bulk rank uses weather stream; site detail checks NWS point alerts
                )
                results.append({
                    "plant_id": p["plant_id"],
                    "plant_name": p["plant_name"],
                    "utility_name": p["utility_name"],
                    "county": p["county"],
                    "capacity_mw": p["capacity_mw"],
                    "hazard_index": res["hazard_index"],
                    "alert_status": res["alert_status"],
                    "primary_hazard": res["primary_hazard"],
                    "observation_time": res["data_timestamp"],
                    "heat_index_f": res["live_metrics"]["apparent_temp_f"],
                    "precip_rate_mm": res["live_metrics"]["precipitation_rate_mm"],
                    "fema_sfha": res["fema_risk"]["fema_is_sfha"],
                })
            except Exception as e:
                print(f"[WARN] Failed fetching live data for {p['plant_name']}: {e}")
            time.sleep(0.02)

        df = pd.DataFrame(results).sort_values(by="hazard_index", ascending=False).reset_index(drop=True)
        return df

    def submit_crew_report(
        self,
        plant_id: int,
        reported_by: str,
        hazard_type: str,
        description: str,
        latitude: float,
        longitude: float,
        photo_url: Optional[str] = None,
    ) -> int:
        """Records a field crew member's crowd-sourced hazard report (wildlife, mud, debris)."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO crew_hazard_reports 
                (plant_id, reported_by, hazard_type, description, latitude, longitude, photo_url)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (plant_id, reported_by, hazard_type, description, latitude, longitude, photo_url),
            )
            conn.commit()
            return cursor.lastrowid
