"""Hazard model interface: where the trained model plugs in.

`PipelineHazardModel` (MODEL_KIND=pipeline, the default with real data) serves the
classifier trained by the pipeline at the repo root. The scoring service only
calls `HazardModel.predict(features)`. Another model plugs in as an adapter that:

1. loads the trained artifact once at startup (from MODEL_PATH),
2. takes the feature dict built by `processing/features.py::build_features`
   (columns in `FEATURE_COLUMNS` order),
3. returns a 0-10 score per hazard plus the features that drove it.

Hazards the model doesn't cover (heat and wildlife today) are scored by rules in
`rules.py`; drop a hazard from the rules once the model covers it.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from ...config import Settings
from ...contracts.api import HazardDriver
from ...contracts.common import HazardType
from ..features import FEATURE_COLUMNS, THUNDERSTORM_CODES

MODEL_HAZARDS = [HazardType.lightning, HazardType.flood, HazardType.soil_saturation, HazardType.wildfire]


@dataclass
class HazardPrediction:
    score: float  # 0-10
    drivers: list[HazardDriver] = field(default_factory=list)


class HazardModel(Protocol):
    version: str

    def predict(self, features: dict[str, float]) -> dict[HazardType, HazardPrediction]: ...


def _clamp(value: float) -> float:
    return round(max(0.0, min(10.0, value)), 1)


def _driver(name: str, contribution: float, features: dict[str, float]) -> HazardDriver:
    return HazardDriver(feature=name, contribution=round(contribution, 2), value=round(features[name], 2))


class DummyHazardModel:
    """Hand-tuned formulas standing in for the trained model. Same inputs and
    outputs as the real adapter, so swapping it is a config change."""

    version = "dummy-0.1"

    def predict(self, f: dict[str, float]) -> dict[HazardType, HazardPrediction]:
        return {
            HazardType.lightning: self._lightning(f),
            HazardType.flood: self._flood(f),
            HazardType.soil_saturation: self._soil(f),
            HazardType.wildfire: self._wildfire(f),
        }

    @staticmethod
    def _lightning(f: dict[str, float]) -> HazardPrediction:
        convective = f["cape"] / 3000 * 5.0
        miles = f["nearest_strike_miles"]
        if miles <= 10:
            proximity = 8.0 + (10 - miles) / 10 * 1.8
        elif miles <= 30:
            proximity = 4.0 + (30 - miles) / 20 * 3.5
        else:
            proximity = 0.0
        activity = min(1.0, f["strikes_30min"] * 0.1)
        return HazardPrediction(_clamp(max(convective, proximity) + activity), [
            _driver("nearest_strike_miles", proximity, f), _driver("cape", convective, f),
            _driver("strikes_30min", activity, f)])

    @staticmethod
    def _flood(f: dict[str, float]) -> HazardPrediction:
        rain = f["rain_24h_in"] * 2.0 + max(0.0, f["rain_3d_in"] - f["rain_24h_in"]) * 0.6 + f["precip_1h_in"] * 2
        river = 4.5 + 2.0 * f["river_stage_ft_above_flood"] if f["river_stage_ft_above_flood"] > -1 else 0.0
        tide = max(0.0, f["tide_ft_above_mhhw"]) * 3.2
        parts = sorted([rain, river, tide], reverse=True)
        return HazardPrediction(_clamp(parts[0] + 0.15 * sum(parts[1:])), [
            _driver("rain_24h_in", rain, f), _driver("river_stage_ft_above_flood", river, f),
            _driver("tide_ft_above_mhhw", tide, f)])

    @staticmethod
    def _soil(f: dict[str, float]) -> HazardPrediction:
        score = max(0.5, (f["soil_moisture_pct"] - 50) / 6.0) + max(0.0, f["rain_24h_in"] - 1) * 0.3
        return HazardPrediction(_clamp(score), [_driver("soil_moisture_pct", score, f)])

    @staticmethod
    def _wildfire(f: dict[str, float]) -> HazardPrediction:
        fuels = (f["drought_index"] - 350) / 45
        wind = max(0.0, f["wind_mph"] - 10) * 0.1
        dry_air = max(0.0, 40 - f["humidity_pct"]) * 0.05
        wet = f["rain_24h_in"] * 1.5
        return HazardPrediction(_clamp(fuels + wind + dry_air - wet), [
            _driver("drought_index", fuels, f), _driver("wind_mph", wind, f), _driver("humidity_pct", dry_air, f)])


class LightGBMHazardModel:
    """One LightGBM binary classifier per hazard, saved as `<MODEL_PATH>/<hazard>.txt`
    (`booster.save_model`), plus an optional `VERSION` file.

    score = 10 * P(hazard event); drivers = top SHAP contributions (`pred_contrib`).
    """

    def __init__(self, model_dir: str) -> None:
        import lightgbm as lgb

        root = Path(model_dir)
        self.boosters = {h: lgb.Booster(model_file=str(root / f"{h.value}.txt"))
                         for h in MODEL_HAZARDS if (root / f"{h.value}.txt").exists()}
        if not self.boosters:
            raise FileNotFoundError(f"no <hazard>.txt models found in {root}")
        version_file = root / "VERSION"
        self.version = version_file.read_text().strip() if version_file.exists() else f"lgbm-{root.name}"

    def predict(self, features: dict[str, float]) -> dict[HazardType, HazardPrediction]:
        row = [[features[c] for c in FEATURE_COLUMNS]]
        out = {}
        for hazard, booster in self.boosters.items():
            probability = float(booster.predict(row)[0])
            contributions = booster.predict(row, pred_contrib=True)[0][:-1]  # last value is the bias
            top = sorted(zip(FEATURE_COLUMNS, contributions), key=lambda x: abs(x[1]), reverse=True)[:3]
            out[hazard] = HazardPrediction(_clamp(probability * 10),
                                           [_driver(name, float(c), features) for name, c in top])
        return out


class PipelineHazardModel:
    """The pipeline's trained multi-class classifier
    (`pipeline/model/artifacts/best_hazard_model.joblib`) plus the pipeline's
    deterministic safety rules (`pipeline/streaming/event_stream.py`).

    Model classes: None, Extreme Heat, Flood, Lightning, Wildfire. Each hazard's
    0-10 score is 10 * P(hazard) / (P(hazard) + P(None)): how strongly today looks
    like that hazard's historical incident days rather than calm days, without
    the hazards diluting each other.

    The classifier learned from incident days, so on ordinary days it still finds
    resemblances (a humid October night "looks like" heat days). Each score is
    therefore scaled by a plausibility gate for the hazard's precondition: heat
    needs a daily max heat index of 85-95°F+, flood needs rain (full weight from
    0.5 in.), lightning needs showers/thunder in the forecast or CAPE, wildfire
    needs dry air (min RH below 60%) and no rain. Rules then set floors:

    - lightning: a flash within 10 mi -> 8+ (and a stop-work hold), within 30 mi
      -> 4-7.5; thunderstorm reported at the site -> 8.5
    - heat: NWS heat index bands; >= 105°F -> 7 (mandatory rest), >= 115°F -> 9
    - flood: >= 25 mm of rain in a FEMA 100-year floodplain -> 6.5
    - soil saturation (not in the model): soil moisture rule

    Drivers: the model's feature importances weighted by how far today's value
    is from the training mean (the pipeline's fitted StandardScaler).
    The artifact is reloaded when the file changes (the pipeline's continuous
    trainer hot-swaps it).
    """

    CLASS_HAZARDS = {"Extreme Heat": HazardType.heat, "Flood": HazardType.flood,
                     "Lightning": HazardType.lightning, "Wildfire": HazardType.wildfire}
    HAZARD_FEATURES = {
        HazardType.heat: ["temperature_2m_max", "apparent_temperature_max", "apparent_temperature_mean",
                          "relative_humidity_2m_mean", "shortwave_radiation_sum", "temperature_2m_mean"],
        HazardType.flood: ["precipitation_sum", "rain_sum", "precipitation_hours", "fema_flood_precip_compound",
                           "fema_flood_risk_score", "soil_moisture_0_to_100cm_mean"],
        HazardType.lightning: ["weather_code", "precipitation_hours", "precipitation_sum",
                               "relative_humidity_2m_max", "temperature_2m_max", "wind_gusts_10m_max"],
        HazardType.wildfire: ["relative_humidity_2m_min", "wind_gusts_10m_max", "et0_fao_evapotranspiration",
                              "shortwave_radiation_sum", "soil_moisture_0_to_100cm_mean", "wind_speed_10m_max"],
    }
    RELOAD_CHECK_SECONDS = 60.0

    def __init__(self, settings: Settings) -> None:
        from ...pipeline_bridge import import_pipeline, model_path, scaler_path
        from ..features import MODEL_FEATURE_COLUMNS

        import_pipeline(settings)
        from pipeline.model.dataset import CLASS_NAMES, FEATURE_COLS

        if list(FEATURE_COLS) != MODEL_FEATURE_COLUMNS:
            raise ValueError("pipeline FEATURE_COLS changed; update features.MODEL_FEATURE_COLUMNS to match")
        self.class_names = list(CLASS_NAMES)
        self.path, self.scaler_path = model_path(settings), scaler_path(settings)
        self.columns = MODEL_FEATURE_COLUMNS
        self._checked_at = 0.0
        self._mtime = 0.0
        self._load()

    def _load(self) -> None:
        import joblib
        import numpy as np

        self.model = joblib.load(self.path)
        if hasattr(self.model, "n_jobs"):
            self.model.n_jobs = 1  # one row at a time; worker threads only add overhead
        self._cache: dict[tuple[float, ...], dict[str, float]] = {}
        self._mtime = self.path.stat().st_mtime
        scaler = joblib.load(self.scaler_path) if self.scaler_path.exists() else None
        self.mean = np.asarray(scaler.mean_) if scaler is not None else np.zeros(len(self.columns))
        self.scale = np.asarray(scaler.scale_) if scaler is not None else np.ones(len(self.columns))
        importances = getattr(self.model, "feature_importances_", None)
        self.importance = dict(zip(self.columns, importances if importances is not None else [1.0] * len(self.columns)))
        stamp = datetime.fromtimestamp(self._mtime, UTC).strftime("%Y%m%d-%H%M")
        self.version = f"pipeline-{type(self.model).__name__}-{stamp}"

    def _maybe_reload(self) -> None:
        now = time.monotonic()
        if now - self._checked_at < self.RELOAD_CHECK_SECONDS:
            return
        self._checked_at = now
        try:
            if self.path.stat().st_mtime != self._mtime:
                self._load()
        except Exception:  # keep serving the loaded model if the swap is mid-write
            logging.getLogger(__name__).exception("reloading %s failed", self.path)

    def probabilities(self, f: dict[str, float]) -> dict[str, float]:
        import numpy as np

        self._maybe_reload()
        key = tuple(round(f[c], 4) for c in self.columns)
        if key not in self._cache:
            # Inputs are daily aggregates, so most rescoring within a day repeats a row.
            if len(self._cache) > 20_000:
                self._cache.clear()
            probs = self.model.predict_proba(np.array([key]))[0]
            self._cache[key] = dict(zip(self.class_names, (float(p) for p in probs)))
        return self._cache[key]

    def _drivers(self, hazard: HazardType, f: dict[str, float]) -> list[HazardDriver]:
        index = {c: i for i, c in enumerate(self.columns)}
        weighted = []
        for name in self.HAZARD_FEATURES[hazard]:
            i = index[name]
            z = (f[name] - self.mean[i]) / (self.scale[i] or 1.0)
            weighted.append((name, float(self.importance[name] * z * 10)))
        top = sorted(weighted, key=lambda x: abs(x[1]), reverse=True)[:3]
        return [_driver(name, c, f) for name, c in top]

    def predict(self, f: dict[str, float]) -> dict[HazardType, HazardPrediction]:
        from .rules import heat_score

        p = self.probabilities(f)
        none = p.get("None", 0.0)
        gates = self.gates(f)
        out = {}
        for name, hazard in self.CLASS_HAZARDS.items():
            share = p.get(name, 0.0)
            ml = 10 * share / (share + none) if share + none > 0 else 0.0
            out[hazard] = HazardPrediction(_clamp(ml * gates[hazard]), self._drivers(hazard, f))

        miles = f["nearest_strike_miles"]
        proximity = 8.0 + (10 - miles) / 10 * 1.8 if miles <= 10 else 4.0 + (30 - miles) / 20 * 3.5 if miles <= 30 else 0.0
        thunder = 8.5 if int(f["current_weather_code"]) in THUNDERSTORM_CODES else 0.0
        self._floor(out[HazardType.lightning], max(proximity, thunder),
                    _driver("nearest_strike_miles", proximity, f) if proximity >= thunder
                    else _driver("current_weather_code", thunder, f))

        hi = f["heat_index_f"]
        heat_rule = max(heat_score(hi), 9.0 if hi >= 115 else 7.0 if hi >= 105 else 0.0)
        self._floor(out[HazardType.heat], heat_rule, _driver("heat_index_f", heat_rule, f))

        floodplain = 6.5 if f["fema_is_sfha"] and f["precipitation_sum"] >= 25 else 0.0
        self._floor(out[HazardType.flood], floodplain, _driver("fema_is_sfha", floodplain, f))

        out[HazardType.soil_saturation] = DummyHazardModel._soil(f)
        return out

    @staticmethod
    def gates(f: dict[str, float]) -> dict[HazardType, float]:
        """0-1 multipliers for the physical precondition each hazard needs."""
        def ramp(x: float, lo: float, hi: float) -> float:
            return min(1.0, max(0.0, (x - lo) / (hi - lo)))

        rain_mm = max(f["precipitation_sum"], f["rain_24h_in"] * 25.4)
        code = int(f["weather_code"])
        convective = 1.0 if code >= 95 else 0.7 if code >= 80 else 0.5 if code >= 61 else 0.3 if code >= 51 else 0.15
        return {
            HazardType.heat: ramp(f["apparent_temperature_max"], 29.4, 35.0),  # 85-95°F
            HazardType.flood: ramp(rain_mm, 0.0, 12.7),  # full weight from half an inch
            HazardType.lightning: max(convective, ramp(f["cape"], 0, 2500)),
            HazardType.wildfire: ramp(60 - f["relative_humidity_2m_min"], 0, 25) * (rain_mm < 5),
        }

    @staticmethod
    def _floor(prediction: HazardPrediction, floor: float, driver: HazardDriver) -> None:
        if floor > prediction.score:
            prediction.score = _clamp(floor)
            prediction.drivers.insert(0, driver)


def load_model(settings: Settings) -> HazardModel:
    if settings.model_kind == "pipeline":
        return PipelineHazardModel(settings)
    if settings.model_kind == "lightgbm":
        return LightGBMHazardModel(settings.model_path)
    return DummyHazardModel()
