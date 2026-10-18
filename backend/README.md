# Heron Backend: Real-Time Streaming & Safety Engine

**High-Throughput Telemetry Ingestion, Sequence-Buffered WebSockets, and OSHA Compliance Hub**

The Heron backend is an enterprise-grade environmental safety engine built on **FastAPI 0.115** and Python 3.12. It serves the high-throughput REST and WebSocket contracts powering the native iOS application, continuously processing meteorological, satellite lightning, and hydrological telemetry across **346 Florida power generation and substation sites**.

---

## 🏛 Architecture Layers

The backend follows a decoupled four-tier architecture designed for continuous uptime and deterministic safety enforcement:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                 LAYER 1: INGESTION                                     │
│  • Open-Meteo Poller: Paced atmospheric & 3-layer soil moisture telemetry              │
│  • NWS Active Alerts Poller: Real-time CAP 1.2 alerts matched via Florida SAME codes   │
│  • NOAA GOES-19 GLM Poller: Sub-second orbital lightning flashes from AWS S3           │
│  • Simulated Data Generator: Scenario injection for demonstrations and offline tests   │
└───────────────────────────────────────────┬────────────────────────────────────────────┘
                                            │ (Publishes to raw.* topics)
                                            ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                LAYER 2: PROCESSING                                     │
│  • Feature Transformer: Normalization, deduplication, and 28-feature vector extraction │
│  • Lightning Safety Engine: Server-side 30-minute hold countdown timer (OSHA mandate)  │
│  • ML Scoring Adapter: GBDT inference yielding calibrated 0–10 Hazard Indices          │
│  • Deterministic Rules: Heat index thresholds, FEMA floodplain saturation advisories   │
│  • Alert Manager: Hysteresis, cooldown deduplication, and priority targeting           │
│  • Briefing Engine: Forward-looking 24–48h meteorological outlook generated at 6:00 PM │
└───────────────────────────────────────────┬────────────────────────────────────────────┘
                                            │
                                            ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                 LAYER 3: STORAGE                                       │
│  • Repository Pattern: Abstract async interface implemented for In-Memory & Postgres   │
│  • EIA-860M Seeding: 346 power facilities joined with FEMA NFHL flood zones            │
│  • Persistent Audit Trail: Crew hazard reports, alert decision logs, and hold history  │
└───────────────────────────────────────────┬────────────────────────────────────────────┘
                                            │
                                            ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                              LAYER 4: API & WEBSOCKET HUB                              │
│  • REST Endpoints: Strict JSON contracts mirroring native Swift models                 │
│  • WebSocket Hub (/api/v1/ws/updates): Sequence numbering, subscription filtering,      │
│    client replay recovery, and 500ms batched state delivery                            │
│  • Interactive CLI (crewsafe.prompt): Natural-language emergency injection for judging │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 🚀 Quickstart & Server Setup

### 1. Initialize Virtual Environment & Install Dependencies

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Launch the FastAPI Production Service

```bash
uvicorn crewsafe.api.main:app --host 0.0.0.0 --port 8000
```

- **Interactive Swagger Documentation**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Health Check Endpoint**: [http://localhost:8000/api/v1/health](http://localhost:8000/api/v1/health)

*(On startup, the engine seeds all 346 Florida power plants from `backend/pipeline/data/incidents.db`, binds the FEMA flood zones, and initiates telemetry ingestion).*

---

## ⚡ Real-Time Simulation CLI (Judging Demos)

Heron features a built-in command-line simulation engine ([`crewsafe/prompt.py`](crewsafe/prompt.py)) designed to demonstrate how the platform responds to critical emergencies in real-time. Commands injected through the CLI traverse the exact same transformation, scoring, lightning hold, and WebSocket streaming pipeline as genuine satellite feeds:

In a separate terminal window:

```bash
# ⚡ Simulate an orbital lightning strike 4 miles from John R Kelly Plant (Site 664):
backend/.venv/bin/python -m crewsafe.prompt "lightning 4 miles from 664"
# --> Server initiates an OSHA Stop-Work Hold, broadcasts to iOS, and starts the 30-min timer.

# 🌊 Simulate severe flash flooding & heavy rain at Turkey Point:
backend/.venv/bin/python -m crewsafe.prompt "flood at Turkey Point"
# --> Injects 3.5 inches of rain into the FEMA model, spikes the Hazard Index, and issues a Warning.

# 🔥 Simulate extreme heat wave:
backend/.venv/bin/python -m crewsafe.prompt "heat at 664"
# --> Elevates apparent temperature above 105°F, issuing mandatory hydration rest directives.

# 📋 Trigger tomorrow's 6:00 PM Safety Briefing:
backend/.venv/bin/python -m crewsafe.prompt briefing
# --> Dispatches an immediate time-sensitive notification with tomorrow's hazard outlook.

# ☀️ Clear all active lightning holds:
backend/.venv/bin/python -m crewsafe.prompt "clear at 664"

# 💻 Launch the interactive simulation shell:
backend/.venv/bin/python -m crewsafe.prompt
```

---

## 📡 API Reference (`/api/v1`)

### REST Endpoints

| Method & Route | Purpose | Consumed by iOS App |
| :--- | :--- | :---: |
| `GET /api/v1/health` | Service health, model version, active WebSocket count, telemetry freshness | |
| `GET /api/v1/sites` | List all 346 monitored power plants with real-time hazard index, conditions, and history | **Yes** |
| `GET /api/v1/sites/{id}` | Detailed facility view with FEMA flood classification and geotechnical metrics | **Yes** |
| `GET /api/v1/sites/{id}/briefing` | Site-specific daily weather briefing and safety outlook | **Yes** |
| `GET /api/v1/lightning/holds` | Active 30-minute stop-work holds with remaining countdown timestamps | **Yes** |
| `GET /api/v1/alerts` | Prioritized alerts (`Advisory`, `Warning`, `Stop-Work`) with user acknowledgment | **Yes** |
| `POST /api/v1/alerts/{id}/ack` | Crew member acknowledges an active alert | **Yes** |
| `GET /api/v1/briefings/next-day` | Daily 6:00 PM forward-looking safety briefing for followed facilities | **Yes** |
| `GET /api/v1/reports` | Retrieve crowd-sourced hazard reports submitted by field crews | **Yes** |
| `POST /api/v1/reports` | Submit new hazard report with base64 photo, GPS pin, and category | **Yes** |
| `POST /api/v1/devices` | Register iOS APNs push notification token | **Yes** |
| `POST /api/v1/simulate` | Programmatic emergency scenario injection endpoint | **Yes** |

### WebSocket Hub: `/api/v1/ws/updates`

The WebSocket connection delivers sub-second bidirectional streaming between the backend engine and field iOS clients.

**Client Subscription Message:**
```json
{
  "type": "subscribe",
  "payload": {
    "site_ids": ["664", "6046"],
    "include_severe_statewide": true,
    "last_seq": 42
  }
}
```

**Server Broadcast Event Types:**
- `hazard_index_updated`: Real-time score recalculation for an individual site.
- `hazard_index_batch`: Aggregated multi-site updates buffered and dispatched every 500ms to conserve mobile radio battery.
- `alert`: New prioritized emergency directive.
- `lightning_strike`: Sub-second notification of an orbital flash with distance and countdown initiation.

---

## 🧪 Automated Testing & Verification

The backend includes a comprehensive pytest suite verifying contract schema parity with Swift models, WebSocket pub/sub mechanics, OSHA lightning hold logic, and simulation accuracy:

```bash
# Run the complete test suite
backend/.venv/bin/pytest -q backend/tests
```
*(All 28 automated tests pass in ~14 seconds).*
