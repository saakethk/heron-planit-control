"""Hazard model interface: where the trained model plugs in.

The scoring service only calls `HazardModel.predict(features)`. To use the real
model, implement (or configure) an adapter that:

1. loads the trained artifact once at startup (from MODEL_PATH),
2. takes the feature dict built by `processing/features.py::build_features`
   (columns in `FEATURE_COLUMNS` order),
3. returns a 0-10 score per hazard plus the features that drove it.

Hazards the model doesn't cover (heat and wildlife today) are scored by rules in
`rules.py`; drop a hazard from the rules once the model covers it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from ...config import Settings
from ...contracts.api import HazardDriver
from ...contracts.common import HazardType
from ..features import FEATURE_COLUMNS

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


def load_model(settings: Settings) -> HazardModel:
    if settings.model_kind == "lightgbm":
        return LightGBMHazardModel(settings.model_path)
    return DummyHazardModel()
