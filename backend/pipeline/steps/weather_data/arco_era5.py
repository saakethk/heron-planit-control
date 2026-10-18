"""Direct Google Cloud ARCO-ERA5 Zarr Weather Feature Extractor.

Extracts identical 20 daily meteorological features directly from Google Cloud
Public Datasets (ARCO-ERA5) without third-party API rate limits.
"""

from datetime import datetime
import math
import os
from typing import Dict, List, Optional, Union
import certifi
import numpy as np
import pandas as pd
import xarray as xr

# ARCO-ERA5 single-level analysis-ready consolidated store
ARCO_ERA5_HTTP_URL = "https://storage.googleapis.com/gcp-public-data-arco-era5/ar/full_37-1h-0p25deg-chunk-1.zarr-v3"

DAILY_VARIABLES = [
    "weather_code",
    "temperature_2m_mean",
    "temperature_2m_max",
    "temperature_2m_min",
    "apparent_temperature_mean",
    "apparent_temperature_max",
    "apparent_temperature_min",
    "precipitation_sum",
    "rain_sum",
    "snowfall_sum",
    "precipitation_hours",
    "wind_speed_10m_max",
    "wind_gusts_10m_max",
    "shortwave_radiation_sum",
    "et0_fao_evapotranspiration",
    "relative_humidity_2m_mean",
    "relative_humidity_2m_max",
    "relative_humidity_2m_min",
    "soil_moisture_0_to_100cm_mean",
    "soil_temperature_0_to_100cm_mean",
]

# Essential surface variable subset needed from ARCO-ERA5
CORE_ERA5_VARS = [
    "2m_temperature",
    "2m_dewpoint_temperature",
    "10m_u_component_of_wind",
    "10m_v_component_of_wind",
    "10m_wind_gust_since_previous_post_processing",
    "total_precipitation",
    "surface_solar_radiation_downwards",
    "volumetric_soil_water_layer_1",
    "volumetric_soil_water_layer_2",
    "volumetric_soil_water_layer_3",
    "soil_temperature_level_1",
    "soil_temperature_level_2",
    "soil_temperature_level_3",
]


class ArcoEra5Client:
    """Manages persistent lazy dataset connection to Google Cloud ARCO-ERA5."""

    def __init__(self, url: str = ARCO_ERA5_HTTP_URL):
        self.url = url
        self._ds: Optional[xr.Dataset] = None

    def get_dataset(self) -> xr.Dataset:
        if self._ds is None:
            os.environ["SSL_CERT_FILE"] = certifi.where()
            os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()
            print("[ARCO-ERA5] Connecting to Google Cloud Storage public Zarr archive...")
            raw_ds = xr.open_zarr(self.url, consolidated=True, storage_options={"ssl": False})
            # Keep only the essential surface variables to speed up chunk requests
            avail_vars = [v for v in CORE_ERA5_VARS if v in raw_ds.data_vars]
            self._ds = raw_ds[avail_vars]
            print(f"[ARCO-ERA5] Connected successfully ({len(avail_vars)} surface variables loaded).")
        return self._ds


_CLIENT_INSTANCE: Optional[ArcoEra5Client] = None


def get_arco_client() -> ArcoEra5Client:
    global _CLIENT_INSTANCE
    if _CLIENT_INSTANCE is None:
        _CLIENT_INSTANCE = ArcoEra5Client()
    return _CLIENT_INSTANCE


def compute_relative_humidity(temp_c: np.ndarray, dewpoint_c: np.ndarray) -> np.ndarray:
    """Calculates relative humidity array from temperatures in Celsius."""
    a = 17.27
    b = 237.7
    alpha_t = (a * temp_c) / (b + temp_c)
    alpha_dp = (a * dewpoint_c) / (b + dewpoint_c)
    rh = 100.0 * np.exp(alpha_dp - alpha_t)
    return np.clip(rh, 0.0, 100.0)


def compute_apparent_temperature(temp_c: float, rh: float, wind_kmh: float) -> float:
    """Computes Australian Bureau of Meteorology Apparent Temperature."""
    wind_ms = wind_kmh / 3.6
    e = (rh / 100.0) * 6.105 * math.exp((17.27 * temp_c) / (237.7 + temp_c))
    at = temp_c + 0.33 * e - 0.70 * wind_ms - 4.00
    return round(at, 2)


def fetch_weather_arco_era5(
    client: ArcoEra5Client,
    record_id: Union[str, int],
    latitude: float,
    longitude: float,
    date_str: str,
) -> Optional[Dict]:
    """Extracts all 20 standardized daily meteorological features from ARCO-ERA5."""
    try:
        ds = client.get_dataset()

        # ERA5 longitudes are in 0-360 range
        lon_360 = float(longitude) % 360.0
        time_slice = slice(f"{date_str}T00:00:00", f"{date_str}T23:00:00")

        # Select nearest spatial grid point then extract 24 hours for the date
        pt = ds.sel(latitude=float(latitude), longitude=lon_360, method="nearest")
        day_data = pt.sel(time=time_slice).compute()

        # Temperature (Kelvin to Celsius)
        temp_c = day_data["2m_temperature"].values - 273.15
        dew_c = day_data["2m_dewpoint_temperature"].values - 273.15
        t_mean = round(float(np.mean(temp_c)), 2)
        t_max = round(float(np.max(temp_c)), 2)
        t_min = round(float(np.min(temp_c)), 2)

        # Relative Humidity
        rh_arr = compute_relative_humidity(temp_c, dew_c)
        rh_mean = round(float(np.mean(rh_arr)), 2)
        rh_max = round(float(np.max(rh_arr)), 2)
        rh_min = round(float(np.min(rh_arr)), 2)

        # Wind Speed & Gusts (m/s to km/h)
        u_wind = day_data["10m_u_component_of_wind"].values
        v_wind = day_data["10m_v_component_of_wind"].values
        wind_speeds = np.sqrt(u_wind**2 + v_wind**2) * 3.6
        w_max = round(float(np.max(wind_speeds)), 2)
        w_mean = round(float(np.mean(wind_speeds)), 2)

        if "10m_wind_gust_since_previous_post_processing" in day_data:
            gust_arr = day_data["10m_wind_gust_since_previous_post_processing"].values * 3.6
            gust_max = round(float(np.nanmax(gust_arr)), 2)
        else:
            gust_max = round(w_max * 1.3, 2)

        # Apparent Temperature
        at_mean = compute_apparent_temperature(t_mean, rh_mean, w_mean)
        at_max = compute_apparent_temperature(t_max, rh_mean, w_max)
        at_min = compute_apparent_temperature(t_min, rh_mean, w_mean)

        # Precipitation (meters to mm)
        precip_m = day_data["total_precipitation"].values
        precip_mm = np.clip(precip_m * 1000.0, 0.0, None)
        precip_sum = round(float(np.sum(precip_mm)), 2)
        precip_hours = round(float(np.sum(precip_mm > 0.1)), 1)

        # Snow vs Rain partitioning (based on 0°C threshold)
        is_snow = temp_c < 0.0
        snowfall_sum = round(float(np.sum(precip_mm[is_snow])), 2)
        rain_sum = round(float(precip_sum - snowfall_sum), 2)

        # Solar Radiation (J/m² to MJ/m²)
        solar_j = day_data["surface_solar_radiation_downwards"].values
        solar_mj = round(float(np.sum(np.clip(solar_j, 0, None))) / 1e6, 2)

        # Reference Evapotranspiration (Hargreaves-Samani approximation mm/day)
        t_range = max(t_max - t_min, 0.0)
        et0 = round(0.0023 * (t_mean + 17.8) * math.sqrt(t_range) * (solar_mj * 0.408), 2)
        et0 = max(et0, 0.0)

        # Soil Moisture 0-100cm (weighted average of layers 1, 2, 3: 7cm, 21cm, 72cm)
        sm1 = np.nanmean(day_data["volumetric_soil_water_layer_1"].values)
        sm2 = np.nanmean(day_data["volumetric_soil_water_layer_2"].values)
        sm3 = np.nanmean(day_data["volumetric_soil_water_layer_3"].values)
        soil_moisture = round(float((sm1 * 0.07 + sm2 * 0.21 + sm3 * 0.72) / 1.0), 3)

        # Soil Temperature 0-100cm (Kelvin to Celsius)
        st1 = np.nanmean(day_data["soil_temperature_level_1"].values) - 273.15
        st2 = np.nanmean(day_data["soil_temperature_level_2"].values) - 273.15
        st3 = np.nanmean(day_data["soil_temperature_level_3"].values) - 273.15
        soil_temp = round(float((st1 * 0.07 + st2 * 0.21 + st3 * 0.72) / 1.0), 2)

        # WMO Weather Code estimation
        if snowfall_sum > 2.0:
            weather_code = 71.0  # Snow
        elif precip_sum > 10.0 or w_max > 50.0:
            weather_code = 65.0  # Heavy rain / convective
        elif precip_sum > 1.0:
            weather_code = 61.0  # Moderate rain
        elif rh_mean > 85.0 and solar_mj < 5.0:
            weather_code = 3.0  # Overcast
        elif rh_mean > 65.0:
            weather_code = 2.0  # Partly cloudy
        else:
            weather_code = 0.0  # Clear sky

        return {
            "ID": str(record_id),
            "weather_code": weather_code,
            "temperature_2m_mean": t_mean,
            "temperature_2m_max": t_max,
            "temperature_2m_min": t_min,
            "apparent_temperature_mean": at_mean,
            "apparent_temperature_max": at_max,
            "apparent_temperature_min": at_min,
            "precipitation_sum": precip_sum,
            "rain_sum": rain_sum,
            "snowfall_sum": snowfall_sum,
            "precipitation_hours": precip_hours,
            "wind_speed_10m_max": w_max,
            "wind_gusts_10m_max": gust_max,
            "shortwave_radiation_sum": solar_mj,
            "et0_fao_evapotranspiration": et0,
            "relative_humidity_2m_mean": rh_mean,
            "relative_humidity_2m_max": rh_max,
            "relative_humidity_2m_min": rh_min,
            "soil_moisture_0_to_100cm_mean": soil_moisture,
            "soil_temperature_0_to_100cm_mean": soil_temp,
        }
    except Exception as exc:
        print(f"[ARCO-ERA5:ERROR] ID {record_id} ({latitude}, {longitude}, {date_str}): {exc}")
        return None
