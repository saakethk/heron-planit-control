# PlanIT Control: Real-Time Utility Jobsite Hazard Platform

PlanIT Control is an environmental intelligence and worker safety platform built for electric utility field crews across Florida. It continuously watches meteorological, hydrological, and geotechnical hazards at job sites, feeds genuine telemetry into a trained Multi-Hazard Machine Learning model, and broadcasts calibrated **0–10 Hazard Indices** alongside deterministic **Stop-Work safety mandates** over a high-throughput Pub/Sub event stream and FastAPI REST/WebSocket service.

---

## Architecture Overview

```
                                      ┌────────────────────────────────────────────────┐
                                      │             GENUINE LIVE DATA FEEDS            │
                                      │ • NOAA NWS Active Alerts (api.weather.gov)     │
                                      │ • Open-Meteo Real-Time (api.open-meteo.com)    │
                                      │ • FEMA NFHL Layer 28 (hazards.fema.gov)        │
                                      │ • USGS Stream Gauges (waterservices.usgs.gov)  │
                                      └───────────────────────┬────────────────────────┘
                                                              │
                                                              ▼
┌──────────────────────────────┐              ┌────────────────────────────────────────┐
│      MONITORED SITES         │              │        STREAMING & BROKER TIER         │
│ • EIA-860M Official Registry │─────────────►│ • Ingest live conditions for 346 sites │
│ • 346 Florida Power Plants   │              │ • Standardize 28-feature vector        │
│ • All 67 Florida Counties    │              │ • Pub/Sub Publisher & Commit Log       │
└──────────────────────────────┘              └───────────────────┬────────────────────┘
                                                                  │
                                                                  ▼
┌──────────────────────────────┐              ┌────────────────────────────────────────┐
│     CONTINUOUS RETRAINING    │              │          ML INFERENCE ENGINE           │
│ • 47,150 Historical Records  │◄─────────────┤ • best_hazard_model.joblib (GBDT / RF) │
│ • Appended Stream Buffer     │ (Auto-append │ • Calibrated 0–10 Hazard Index         │
│ • Hot-Swap Validation Check  │  observations│ • 10-Mile Lightning & Heat Guardrails  │
└──────────────────────────────┘  for retrain)└───────────────────┬────────────────────┘
                                                                  │
                                                                  ▼
                                      ┌────────────────────────────────────────────────┐
                                      │         FASTAPI REST & WEBSOCKET GATEWAY       │
                                      │ • REST: /api/v1/sites, /evaluate, /reports     │
                                      │ • WebSockets: /ws/hazards, /ws/sites/{id}      │
                                      │ • Background Event Bridge to All Clients       │
                                      └───────────────────────┬────────────────────────┘
                                                              │
                                     ┌────────────────────────┴────────────────────────┐
                                     ▼                                                 ▼
                      ┌─────────────────────────────┐                   ┌─────────────────────────────┐
                      │    CENTRAL CONTROL ROOM     │                   │    FIELD CREW LINEMEN       │
                      │  Live Telemetry Dashboard   │                   │ Mobile Stop-Work Directives │
                      └─────────────────────────────┘                   └─────────────────────────────┘
```

---

## Monitored Jobsites: Official EIA-860M Florida Registry

All monitored sites are ingested directly from the official U.S. Energy Information Administration (EIA) Form EIA-860M monthly workbook (`pipeline/data/eia860m.xlsx`):
* **346 Operating Power Plant Sites** across **all 67 Florida counties**.
* Spans large base-load facilities (West County 4,263 MW, Crystal River 3,449 MW, Turkey Point Nuclear 2,978 MW) to distributed municipal solar and combustion turbine yards.
* Pre-synchronized with the official **FEMA National Flood Hazard Layer (NFHL) Layer 28** MapServer to assign statutory 100-year Special Flood Hazard Area (SFHA, Zone A/AE) and coastal wave hazard (Zone VE) determinations to every plant coordinate.

---

## Multi-Hazard Machine Learning Model

The core classifier (`pipeline/model/artifacts/best_hazard_model.joblib`) is trained to distinguish between calm baseline operating conditions and 4 major life-threatening field hazards:

1. **`None` (Safe Control)**: Normal atmospheric conditions within safe operating limits.
2. **`Extreme Heat`**: High ambient temperature and apparent Heat Index ($T_{\text{apparent}} \ge 105^\circ\text{F}$) driving heat exhaustion and heat stroke.
3. **`Flood`**: Flash flooding, heavy rain inundation inside FEMA 100-year floodplains, and river stage breaches.
4. **`Lightning`**: Convective atmospheric lightning strikes and severe thunderstorm cells.
5. **`Wildfire`**: High winds, low relative humidity, and high vegetative evapotranspiration.

*(Note: In accordance with challenge requirements, sparse non-meteorological incident types like `Soil Saturation` (57 rows) and `Wildlife` are excluded from the core ML model to preserve statistical balance and calibration).*

### The 28 Standardized Model Features
Every inference pass evaluates exactly 28 standardized numerical inputs:
* **Temperature (6)**: 2m mean, max, min; Apparent (Heat Index) mean, max, min.
* **Precipitation & Moisture (7)**: Total rain sum, liquid rain, snowfall (0.0 in FL), rain hours, relative humidity (mean, max, min).
* **Wind & Atmosphere (4)**: Sustained 10m wind speed, peak gusts, solar shortwave radiation, evapotranspiration rate.
* **Subsurface & Storm (3)**: Volumetric soil moisture, topsoil temperature, WMO convective weather code (95/96/99 = Thunderstorm).
* **Spatial & Seasonality (4)**: Decimal Latitude, Longitude, Cyclical Month ($\sin / \cos$ harmonics).
* **FEMA Regulatory Flood (4)**: Special Flood Hazard Area (`is_sfha`), Coastal Velocity Zone (`is_coastal`), FEMA baseline score (0.05–1.0), and Compound Interaction (`fema_score * precipitation_sum`).

### Deterministic Operational Safeguards
Beyond the probabilistic ML score, hard rules instantly enforce mandatory safety protocols:
* ⚡ **10-Mile Lightning Rule**: Outdoor work ceases immediately if a strike is detected within 10 miles or active NWS Severe Thunderstorm Warning is present. Initiates a mandatory 30-minute all-clear timer.
* 🔥 **Extreme Heat Mandate**: Heat Index $\ge 105^\circ\text{F} \rightarrow$ Mandatory 15-min rest/hydration; $\ge 115^\circ\text{F} \rightarrow$ Mandatory work cessation.
* 🌊 **FEMA Floodplain Warning**: Rainfall $\ge 25\text{ mm}$ inside a FEMA 100-year Zone A/AE $\rightarrow$ Site Flood Advisory.

---

## Continuous Learning & Retraining Pipeline

PlanIT Control bridges the gap between historical training and streaming telemetry:
1. **Preserves Historical Baseline**: Retains all 47,150 historical records in `incidents.db` (OSHA injuries, NOAA storms, NIFC wildfires) with balanced representative sampling (`is_sampled = 1`).
2. **Auto-Appends Real-Time Data**: Incoming streaming observations and field crew reports are continuously written to `stream_training_records`.
3. **Automated Merged Retraining**: [`pipeline/model/continuous_trainer.py`](pipeline/model/continuous_trainer.py) merges historical anchors with newly streamed data, trains a fresh model, benchmarks validation performance on a holdout split, and atomically hot-swaps `best_hazard_model.joblib` if Macro F1 $\ge 0.80$ with zero service downtime.

---

## FastAPI REST & WebSocket Endpoints

The unified API server is implemented in [`pipeline/api/main.py`](pipeline/api/main.py).

### REST Endpoints
* `GET /health` — Service healthcheck, model version, monitored sites count, and active WebSocket connection count.
* `GET /api/v1/sites` — List Florida power plant job sites (filterable by county, capacity, FEMA zone).
* `GET /api/v1/sites/{plant_id}` — Real-time hazard evaluation and telemetry for a specific site.
* `POST /api/v1/sites/{plant_id}/evaluate` — Run hypothetical scenario simulations (e.g. test strike proximity slider).
* `POST /api/v1/reports/crew` — Submit crowd-sourced field hazard report (wildlife, mud, debris, tree down).
* `GET /api/v1/events/latest` — Read the most recent entries from the persistent event stream log.
* `POST /api/v1/model/retrain` — Manually trigger continuous retraining on historical + new streamed data.

### WebSocket Endpoints
* `WS /ws/hazards` — **Global Stream**: Broadcasts real-time inference events across all Florida job sites as they are evaluated.
* `WS /ws/sites/{plant_id}` — **Site-Specific Stream**: Subscribes exclusively to events for one jobsite.

---

## Directory Structure

```
pipeline/
├── config.py                     # Central configuration, file paths, and safety thresholds
│
├── api/                          # FastAPI REST & WebSocket Service
│   ├── __init__.py
│   ├── main.py                   # FastAPI application, CORS, routes & WebSocket bridge
│   ├── schemas.py                # Pydantic request and response schemas
│   ├── websocket_manager.py      # Connection manager for broadcast & per-site channels
│   └── demo_client.py            # Test client demonstrating REST & WebSocket streaming
│
├── model/                        # Machine Learning & Continuous Training
│   ├── dataset.py                # 28 standardized feature definitions & data prep
│   ├── continuous_trainer.py     # Continuous learner merging historical + stream data
│   ├── benchmark.py              # Model cross-validation and benchmarking harness
│   ├── hazard_net.py             # PyTorch Multi-Task Deep Neural Network
│   └── artifacts/
│       ├── best_hazard_model.joblib  # Active GBDT / Random Forest model
│       └── hazard_scaler.joblib      # Fitted StandardScaler
│
├── streaming/                    # Ingestion & Pub/Sub Event Streaming
│   ├── __init__.py
│   ├── live_weather.py           # Open-Meteo live API client (instantaneous surface readings)
│   ├── nws_alerts.py             # NOAA NWS active alerts client (api.weather.gov)
│   ├── event_stream.py           # Pub/Sub broker, append-only log, and inference loop
│   └── audit_pipeline.py         # 28-feature completeness and cadence verification
│
├── ingestion/                    # Static Baseline Ingestion
│   ├── __init__.py
│   └── eia_plants.py             # EIA-860M Florida power plant parser (346 sites)
│
├── steps/                        # Historical ETL Steps (OSHA, NOAA, NIFC, NASA POWER)
│   ├── osha_incident_data/
│   ├── noaa_flood_data/
│   ├── noaa_lightning_data/
│   ├── nifc_wildfire_data/
│   ├── weather_data/
│   ├── fema_flood_risk/
│   └── representative_sampling/
│
├── data/                         # Persistent Storage
│   ├── eia860m.xlsx              # Official EIA-860M workbook
│   ├── incidents.db              # SQLite database (monitored_sites, fema_flood_risk, event_stream)
│   ├── event_stream.jsonl        # Append-only persistent commit log
│   └── .weather_cache.sqlite     # Local HTTP extraction cache
│
└── __main__.py                   # Batch ETL pipeline runner
```

---

## Quickstart & Verification Commands

### 1. Verify Live Telemetry & Feature Completeness (100% Audit)
Checks external connections to NOAA NWS and Open-Meteo, verifies all 28 features without NaNs, and runs model inference:
```bash
python -m pipeline.streaming.audit_pipeline
```

### 2. Run the Pub/Sub Event Streaming Loop
Evaluates Florida power plant jobsites, runs model inference, appends to `event_stream.jsonl`, and updates the continuous training buffer:
```bash
python -m pipeline.streaming.event_stream --cycle
```

### 3. Test Continuous Learning & Atomic Model Hot-Swapping
Merges historical records with newly streamed observations, retrains the model, and hot-swaps `best_hazard_model.joblib`:
```bash
python -m pipeline.model.continuous_trainer
```

### 4. Launch the FastAPI REST & WebSocket Server
```bash
# Install dependencies
pip install fastapi uvicorn websockets

# Start server
uvicorn pipeline.api.main:app --host 127.0.0.1 --port 8000 --reload
```
* Interactive Swagger API Docs: `http://127.0.0.1:8000/docs`
* Global WebSocket: `ws://127.0.0.1:8000/ws/hazards`

### 5. Run the API & WebSocket Test Client
```bash
python -m pipeline.api.demo_client
```