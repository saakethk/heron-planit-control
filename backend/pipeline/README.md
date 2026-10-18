# Heron: Multi-Hazard Machine Learning & Telemetry Pipeline

**Real-Time Predictive Environmental Intelligence for Florida Utility Operations**

The Heron ML Pipeline continuously extracts, normalizes, and evaluates atmospheric, hydrological, and geotechnical data across **346 EIA-860M Florida electric power generation and substation sites**. By mapping high-frequency telemetry into a 28-feature physical state vector, the pipeline drives a calibrated **Multi-Hazard Machine Learning Model** that outputs continuous **0–10 Hazard Indices** alongside deterministic **OSHA Stop-Work mandates** in under 2 milliseconds.

---

## 🏗 Pipeline Architecture

```
                                  ┌────────────────────────────────────────────────────────┐
                                  │               REAL-TIME INGESTION FEEDS                │
                                  │ • NOAA NWS Active Alerts (api.weather.gov)             │
                                  │ • Open-Meteo Atmospheric & Soil (api.open-meteo.com)   │
                                  │ • NOAA GOES-19 GLM Orbital Lightning (AWS S3)         │
                                  │ • FEMA NFHL Layer 28 Special Flood Hazard Areas       │
                                  │ • ECMWF ERA5-Land Volumetric Soil Moisture (3 Layers)  │
                                  └───────────────────────────┬────────────────────────────┘
                                                              │
                                                              ▼
┌──────────────────────────────┐              ┌────────────────────────────────────────────┐
│      MONITORED SITES         │              │        FEATURE TRANSFORMATION TIER         │
│ • EIA-860M Federal Registry  │─────────────►│ • Standardize 28-feature physical vector   │
│ • 346 Florida Power Plants   │              │ • Spatial & temporal harmonic encoding     │
│ • All 67 Florida Counties    │              │ • Compound FEMA interaction calculation    │
└──────────────────────────────┘              └───────────────────────┬────────────────────┘
                                                                      │
                                                                      ▼
┌──────────────────────────────┐              ┌────────────────────────────────────────────┐
│     CONTINUOUS RETRAINING    │              │            ML INFERENCE ENGINE             │
│ • 47,150 Historical Records  │◄─────────────┤ • best_hazard_model.joblib (GBDT Engine)   │
│ • Real-time Stream Buffer    │ (Auto-append │ • Calibrated 0–10 Hazard Index             │
│ • Atomic Hot-Swap (F1 ≥ 0.8) │  telemetry)  │ • 10-Mile Lightning & Heat Guardrails      │
└──────────────────────────────┘              └───────────────────────┬────────────────────┘
                                                                      │
                                                                      ▼
                                              ┌────────────────────────────────────────────┐
                                              │      PRODUCTION STREAMING API & WS HUB     │
                                              │ • Sequence-buffered WebSocket broadcast    │
                                              │ • REST endpoints (/api/v1/sites, /alerts)  │
                                              │ • Push adapter for time-sensitive alerts   │
                                              └────────────────────────────────────────────┘
```

---

## 🏭 Monitored Facilities: Official EIA-860M Registry

All monitored sites are ingested directly from the official U.S. Energy Information Administration (EIA) Form EIA-860M monthly registry:
- **346 Operating Power Plant Sites** across **all 67 Florida counties** (exceeding the 50-site challenge specification by ~7x).
- Spans critical base-load infrastructure (Turkey Point Nuclear, West County Energy Center, Crystal River Energy Complex) to distributed municipal solar arrays, combustion turbines, and battery storage yards.
- Pre-synchronized with the statutory **FEMA National Flood Hazard Layer (NFHL) Layer 28** MapServer to assign 100-year Special Flood Hazard Area (SFHA, Zone A/AE) and coastal wave hazard (Zone VE) determinations to every plant coordinate.

---

## 📊 Historical Dataset Curation (47,150 Records)

To guarantee that the machine learning model accurately mirrors actual industrial hazards faced by utility linemen and field operators, training data was assembled and cross-referenced from four authoritative federal databases:

1. **OSHA Severe Injury Reports (2015–Present)**: Occupational incidents across Florida electric utilities, line construction, and substations (heat stroke, lightning strikes, trench collapses, heavy equipment rollovers in mud).
2. **NOAA Storm Events Database**: Decadal historical storm archives detailing convective thunderstorm cells, flash flood episodes, severe microbursts, and tropical storm trajectories across Florida.
3. **NIFC Wildfire Archives**: National Interagency Fire Center records of wildland-urban interface fires, acreage burned, and associated meteorological fire weather conditions.
4. **FEMA NFHL Inundation Records**: Historical 100-year flood zone boundaries and hydrological floodway maps.

After feature extraction and cleaning, a balanced holdout dataset was compiled with representative sampling across the 5 primary operational categories.

---

## 🧬 Feature Engineering: The 28 Standardized Features

Every inference cycle evaluates exactly 28 physical and geotechnical features:

| Category | Features | Description & Physical Derivation |
| :--- | :---: | :--- |
| **Temperature** | 6 | 2m ambient mean, max, and min ($^\circ\text{C}$); Apparent Temperature (Heat Index) mean, max, and min factoring humidity and radiation. |
| **Precipitation & Moisture** | 7 | Total precipitation sum ($\text{mm}$), liquid precipitation, snowfall ($0.0\text{ mm}$ in FL), precipitation duration (hours), relative humidity (mean, max, min). |
| **Wind & Atmosphere** | 4 | 10m sustained wind speed ($\text{km/h}$), peak convective gusts, surface solar shortwave radiation ($\text{W/m}^2$), vegetative evapotranspiration rate. |
| **Geotechnical & Subsurface** | 3 | ECMWF ERA5-Land volumetric soil moisture ($0\text{--}7\text{ cm}$, $7\text{--}28\text{ cm}$, $28\text{--}100\text{ cm}$) against a $0.45\text{ m}^3/\text{m}^3$ peat/clay saturation threshold; topsoil temperature ($^\circ\text{C}$); WMO convective weather code (95/96/99 = severe thunderstorm). |
| **Spatial & Seasonality** | 4 | Precise decimal Latitude, Longitude, Cyclical Month Harmonics ($\sin(2\pi m / 12)$, $\cos(2\pi m / 12)$) to capture Florida's distinct summer convective rainy season vs. winter dry season. |
| **FEMA Flood Interactions** | 4 | Special Flood Hazard Area indicator (`is_sfha`), Coastal Wave Velocity Zone (`is_coastal`), baseline FEMA vulnerability score (0.05–1.0), and Compound Flood Interaction (`fema_score * precipitation_sum`). |

---

## 🔬 Benchmark Comparison Across 4 Model Architectures

All candidate architectures were trained and evaluated on an identical stratified holdout split (80% Train, 20% Test across 3,000 curated observations):

| Architecture | Test Accuracy | Macro F1 | Weighted F1 | Macro ROC-AUC | Inference Latency | Training Time |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| 🏆 **Hist Gradient Boosting (GBDT)** | **94.5%** | **0.9448** | **0.9448** | **0.9722** | **< 2 ms** | **0.42 s** |
| 🧠 **Multi-Task PyTorch HazardNet** | 85.7% | 0.8557 | 0.8562 | 0.9697 | 12 ms | 18.50 s |
| 🌲 **Balanced Random Forest** | 85.0% | 0.8504 | 0.8510 | 0.9640 | 5 ms | 1.85 s |
| 📈 **Logistic Regression (Baseline)** | 72.3% | 0.7210 | 0.7225 | 0.9015 | < 1 ms | 0.15 s |

### Why GBDT Won
- **Non-Linear Physical Thresholds**: Environmental hazards exhibit sharp step-function triggers (e.g. `apparent_temperature > 40.5°C` or `soil_moisture > 0.45 m³/m³`). Gradient-boosted decision trees partition these continuous physical bounds significantly better than neural networks without requiring complex kernel transforms.
- **Zero-GPU Production Deployment**: GBDT compiles into efficient C-based decision trees with a microscopic memory footprint, executing inference on 346 sites in under 2 milliseconds on standard server CPUs.
- **Explainability**: Decision tree leaf nodes map directly to human-interpretable hazard drivers that are surfaced on field crew dashboards (e.g. *"Driven by: Extreme Heat (0.94) + Saturated Topsoil"*).

### Test Set Classification Report (Best Model)
Evaluated across 600 unseen test samples (120 per hazard class):

```
Hazard Category      Precision    Recall    F1-Score    Test Support
────────────────────────────────────────────────────────────────────
None (Safe Control)    0.9244     0.9167     0.9205         120
Extreme Heat           0.9113     0.9417     0.9262         120
Flood                  0.9675     0.9917     0.9794         120
Lightning              0.9640     0.8917     0.9264         120
Wildfire               0.9593     0.9833     0.9712         120
────────────────────────────────────────────────────────────────────
Macro Average          0.9453     0.9450     0.9448         600
Weighted Average       0.9453     0.9450     0.9448         600
Overall Accuracy                             0.9450 (94.5%)
```

---

## 📈 Visual Model Evaluation Artifacts

### 1. Normalized Confusion Matrix Heatmap
Shows exceptional separation across all 5 classes, with flood and wildfire detection exceeding 98% recall:

<p align="center">
  <img src="model/artifacts/confusion_matrix.svg" alt="Normalized Confusion Matrix Heatmap" width="85%" />
</p>

### 2. Multi-Class ROC Curves (One-vs-Rest)
Area Under the Curve (AUC) consistently ranges between 0.96 and 0.99 across all operational hazard classes:

<p align="center">
  <img src="model/artifacts/roc_curves.svg" alt="Multi-Class ROC Curves" width="85%" />
</p>

### 3. Feature Importance Analysis
Highlights the dominance of apparent temperature, compound FEMA flood interactions, and volumetric soil moisture:

<p align="center">
  <img src="model/artifacts/feature_importance.svg" alt="Feature Importance Analysis" width="85%" />
</p>

---

## ⚡ Deterministic Operational Safeguards

While the machine learning model produces a calibrated, continuous 0–10 hazard score, safety in high-voltage utility environments cannot depend solely on probabilistic inference. Heron overlays deterministic **OSHA safety guardrails**:

- ⚡ **10-Mile Lightning Rule**: Outdoor work is immediately halted whenever an orbital flash is registered within 10 miles. The system initiates an automated 30-minute all-clear countdown timer that resets with every subsequent strike.
- 🔥 **OSHA Heat Protocols**: Apparent temperatures $\ge 105^\circ\text{F}$ enforce mandatory 15-minute hydration breaks; conditions $\ge 115^\circ\text{F}$ trigger mandatory work cessation.
- 🌊 **FEMA Special Flood Hazard Inundation**: Sustained rainfall $\ge 25\text{ mm}$ within designated regulatory floodways immediately elevates site risk to a Flood Advisory or Warning.

---

## 🔄 Continuous Retraining & Hot-Swapping

Heron bridges the gap between static model weights and live operating environments:
1. **Preserves Historical Baseline**: Retains 47,150 historical records in `incidents.db` to prevent catastrophic forgetting.
2. **Auto-Appends Real-Time Data**: Incoming telemetry and verified crew hazard reports are buffered into `stream_training_records`.
3. **Automated Merged Retraining**: [`backend/pipeline/model/continuous_trainer.py`](model/continuous_trainer.py) merges historical records with newly streamed observations, executes cross-validation on a holdout split, and atomically hot-swaps `best_hazard_model.joblib` if Macro F1 $\ge 0.80$ with zero service downtime.

---

## 🛠 Verification & Execution Commands

### 1. Verify Pipeline Feature Completeness (100% Audit)
Validates live connections to NOAA NWS and Open-Meteo, verifies all 28 features without missing values, and checks model inference:
```bash
python -m backend.pipeline.streaming.audit_pipeline
```

### 2. Run the Benchmark Harness Across All 4 Architectures
```bash
python -m backend.pipeline.model.benchmark
```

### 3. Test Continuous Learning & Atomic Model Hot-Swapping
```bash
python -m backend.pipeline.model.continuous_trainer
```