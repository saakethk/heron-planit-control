<p align="center">
  <img src="assets/logo.png" alt="Heron App Logo" width="160" style="border-radius: 28px;" />
</p>

<h1 align="center">Heron</h1>
<p align="center">
  <b>Real-Time Environmental Intelligence & Worker Safety Platform for Florida Utility Field Crews</b>
</p>

---

## 🎯 Executive Summary

### The Reality on the Ground: 6:45 AM in the Everglades
It is 6:45 AM on a remote transmission corridor cutting through the Florida Everglades. The ambient heat index is already surging toward $110^\circ\text{F}$. Dark convective storm cells are gathering 12 miles to the west over the Gulf. Heavy overnight rainfall has turned the access road into saturated peat and mud, threatening to bog down a 40-ton boom truck. At the same time, crew members are trading hurried text messages about an 8-foot alligator spotted basking near the base of Tower 14.

In high-risk utility operations, danger rarely arrives as a single, isolated event—it arrives as a **compound cascade**. Today, field crews and dispatchers are forced to piece together disjointed information:
- Consumer weather apps report delayed, city-wide forecasts with zero site-level geotechnical resolution.
- Critical safety mandates—such as the **10-mile lightning rule**—rely on human guesswork until thunder is audibly heard.
- Ground realities like flooded access paths, saturated mud, and wildlife threats stay trapped in informal SMS chains rather than reaching control room supervisors.

### The Heron Platform
**Heron** transforms utility field safety from reactive guesswork into proactive, real-time environmental intelligence. Built specifically for Florida's volatile climate, Heron continuously monitors **346 EIA-860M electric power generation and substation facilities** across all 67 Florida counties.

By fusing high-frequency orbital weather satellites, ground meteorological networks, hydrological flood models, and live field reports into a calibrated **Multi-Hazard Machine Learning Model**, Heron computes a continuous, site-specific **0–10 Hazard Index**. When conditions deteriorate, Heron executes automated stop-work directives—including an active 30-minute lightning countdown timer—streamed directly to field crews' iPhones via native SwiftUI and WebSockets.

---

## 🏗 High-Level Architecture

<p align="center">
  <img src="assets/architecture.svg" alt="Heron High-Level Architecture Pipeline" width="100%" />
</p>

Heron decouples complex environmental data ingestion from edge mobile consumption through four resilient tiers:
1. **Environmental Ingestion**: Paced asynchronous pollers ingest live atmospheric, orbital lightning (NOAA GOES-19 GLM), and FEMA hydrological data.
2. **Unified Feature Transformation & ML Scoring**: Telemetry is mapped into a standardized 28-feature vector and evaluated by a Gradient Boosted Decision Tree (GBDT) running in $<2\text{ ms}$, bounded by deterministic OSHA safety guardrails.
3. **Event Streaming & State Management**: An at-least-once message bus broadcasts state updates, sequenced hazard batches, and stop-work events over low-latency WebSockets.
4. **Field Edge & Supervisor Client**: A native iOS application built with SwiftUI and MapKit delivers instant alerts, interactive risk mapping, offline fallback caches, and two-way field hazard reporting.

---

## ⚡ Core Capabilities

### 1. Unified Multi-Hazard Operational Picture (346 Monitored Facilities)
Heron monitors **346 operating electric power plants and substations** across Florida (sourced from the official U.S. Energy Information Administration EIA-860M registry)—from Turkey Point Nuclear and West County Energy Center to municipal solar arrays and battery storage sites. For every site, Heron synthesizes six concurrent data dimensions into a single operational picture:
- **Atmospheric Conditions**: Real-time ambient temperature, humidity, wind gusts, and barometric pressure.
- **Extreme Heat Index**: Apparent temperature calculations factoring high humidity and direct solar radiation.
- **Orbital Lightning Tracking**: Real-time flash coordinates captured by NOAA's GOES-19 Geostationary Lightning Mapper (GLM).
- **Hydrological & Flood Risks**: Live rainfall totals cross-referenced with statutory FEMA 100-year Special Flood Hazard Area (SFHA Zone A/AE) boundaries.
- **Geotechnical Soil Saturation**: Multi-layer root zone soil moisture from ECMWF ERA5-Land physics models evaluated against a $0.45\text{ m}^3/\text{m}^3$ porosity threshold to flag equipment bogging risks.
- **Wildlife & Ground Observations**: Verified crowd-sourced reports of gators, downed trees, and roadway washouts.

### 2. Instant Dangerous Condition Alerts & OSHA Guardrails
When site conditions cross hazardous thresholds, Heron immediately issues prioritized, color-coded directives (`Advisory`, `Warning`, or `Stop-Work`):
- ⚡ **10-Mile Lightning Rule**: Detection of an orbital flash within 10 miles of any job site instantly triggers a mandatory **Stop-Work directive**. The system initiates a synchronized **30-minute all-clear countdown timer** that automatically resets to 30:00 with every subsequent strike inside the 10-mile radius.
- 🔥 **OSHA Extreme Heat Protocol**: Apparent temperatures $\ge 105^\circ\text{F}$ enforce mandatory 15-minute hydration rests; conditions $\ge 115^\circ\text{F}$ trigger mandatory work cessation.
- 🌊 **Flash Flooding & Heavy Inundation**: Sustained rainfall $\ge 25\text{ mm}$ within designated FEMA floodways instantly alerts crews to substation pooling and sub-surface trench collapses.

### 3. Automated 6:00 PM Next-Day Safety Briefings
Every evening at **6:00 PM local time**, Heron's automated briefing pipeline analyzes the forward-looking 24- to 48-hour meteorological outlook for every followed site. The resulting briefing is dispatched via iOS `.timeSensitive` push notifications and pinned directly to the mobile app's **Today** view, arming supervisors with projected peak heat hours, storm probabilities, and required PPE before morning tailboard meetings.

### 4. Waze-Style Crew Hazard Reporting
Field linemen can report on-site dangers in seconds. Tapping **Report Hazard** opens the native camera or photo library, automatically attaches high-precision GPS coordinates, and allows the worker to categorize the hazard (e.g., *Wildlife / Gator*, *Mud & Soil Saturation*, *Downed Utility Poles*, *Debris*). Once submitted, the report synchronizes with the central database and broadcasts instantly to nearby crews and the supervisor's live map.

### 5. Supervisor PlanIt Risk Dashboard
Designed for dispatchers and safety supervisors, the interactive MapKit interface visualizes the entire state of Florida with custom hazard pins. A docked **"Risk Near You"** carousel automatically sorts and ranks facilities from highest to lowest Hazard Index, enabling operations leaders to triage emergency personnel, delay high-voltage switching, and pre-position recovery equipment where risks are greatest.

### 6. Calibrated Machine Learning Hazard Index (0–10)
At the core of Heron is a calibrated classification engine trained on **47,150 historical records** (spanning OSHA Severe Injury Reports, NOAA Storm Events, NIFC Wildfires, and FEMA floodplains). Evaluating **28 physical features**, Heron's Gradient Boosted Decision Tree (GBDT) achieves a **94.5% test accuracy (0.945 Macro F1)** across 5 distinct hazard classes (`Safe Control`, `Extreme Heat`, `Flood`, `Lightning`, and `Wildfire`), delivering an explainable, continuous 0–10 risk score with $<2\text{ ms}$ inference latency.

---

## 📖 In-Depth Technical Documentation

For deep technical specifications, model benchmarks, and architectural designs, explore our specialized sub-module documentation:

| Sub-Module | Focus & Technical Depth | Documentation Link |
| :--- | :--- | :---: |
| 🧠 **Machine Learning & Pipeline** | Multi-hazard GBDT vs. PyTorch vs. Random Forest benchmarks (94.5% test accuracy), 28-feature schema, evaluation ROC/confusion matrix plots, and continuous learning hot-swap loop. | [**Machine Learning Guide**](backend/pipeline/README.md) |
| ⚙️ **Backend & Streaming Engine** | FastAPI 0.115 architecture, async satellite pollers, message bus, sequence-buffered WebSockets, and scripted simulation CLI. | [**Backend Architecture**](backend/README.md) |
| 📱 **Native iOS App ("Heron")** | Native SwiftUI (iOS 17+), high-glare Marsh design tokens, MapKit supervisor view, time-sensitive local notifications, and camera integration. | [**iOS App Guide**](frontend/README.md) |

---

## 🚀 Quickstart & Live Judging Demo Guide

Run the complete Heron stack locally in under 2 minutes:

### 1. Start the Backend Server

```bash
# Navigate to the backend directory
cd backend

# Create and activate Python virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install production dependencies
pip install -r requirements.txt

# Start the FastAPI engine (binds to 0.0.0.0:8000 for local network device access)
uvicorn crewsafe.api.main:app --host 0.0.0.0 --port 8000
```
- **Interactive Swagger API Documentation**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Health Check Endpoint**: [http://localhost:8000/api/v1/health](http://localhost:8000/api/v1/health)

*(The backend seeds all 346 EIA power facilities from `backend/pipeline/data/incidents.db` and begins telemetry ingestion).*

---

### 2. Launch the Native iOS App

```bash
# In a new terminal, navigate to the iOS project directory
cd frontend/ios

# Generate the Xcode project cleanly using XcodeGen
xcodegen generate

# Open the project in Xcode
open CrewSafe.xcodeproj
```
- Select an **iPhone 17 Simulator** (or your plugged-in physical iPhone).
- Press **<kbd>Cmd</kbd> + <kbd>R</kbd>** to build and run.

---

### 3. Simulate Emergency Events in Real-Time

Heron includes a command-line simulation tool ([`backend/crewsafe/prompt.py`](backend/crewsafe/prompt.py)) that injects simulated events into the running pipeline, demonstrating how the system responds to real-time emergencies:

In a separate terminal window:

```bash
# ⚡ Simulate a lightning strike 4 miles from John R Kelly Plant (Site 664):
backend/.venv/bin/python -m crewsafe.prompt "lightning 4 miles from 664"
# --> Initiates an immediate Stop-Work Hold, broadcasts to iOS, and starts the 30-min countdown.

# 🌊 Simulate an extreme flood warning & heavy rain:
backend/.venv/bin/python -m crewsafe.prompt "flood at 664"
# --> Injects 3.5 inches of rain into the model, spikes the Hazard Index, and issues a Flood Warning.

# 📋 Simulate tomorrow's 6 PM Safety Briefing:
backend/.venv/bin/python -m crewsafe.prompt briefing
# --> Pushes an immediate time-sensitive notification with tomorrow's hazard outlook.

# ☀️ Clear active lightning holds:
backend/.venv/bin/python -m crewsafe.prompt "clear at 664"

# 💻 Launch the interactive simulation shell:
backend/.venv/bin/python -m crewsafe.prompt
```

---

### 4. Run the Automated Test Suite

```bash
backend/.venv/bin/pytest -q backend/tests
```
*(All 28 contract, pipeline, WebSocket, and simulation tests pass).*

---

## 📂 Repository Organization

```
heron-planit-control/
├── backend/                        # Comprehensive Backend & ML Pipeline Tier
│   ├── crewsafe/                   # Production Real-Time Engine (FastAPI 0.115)
│   │   ├── api/                    # REST routes, auth, WebSocket hub (/ws/updates)
│   │   ├── contracts/              # Strict Pydantic contracts mirroring Swift models
│   │   ├── ingestion/              # Real-time pollers: Open-Meteo, NWS, GOES-19 GLM
│   │   ├── messaging/              # At-least-once message bus (in-memory / Kafka)
│   │   ├── processing/             # Features, transformer, scoring engine, alerts
│   │   ├── storage/                # Repository interface, in-memory state, SQLite
│   │   └── prompt.py               # Natural-language CLI for live judging simulations
│   │
│   ├── pipeline/                   # Data Science, ML Modeling & Retraining Pipeline
│   │   ├── data/                   # 47,150 historical records (OSHA, NOAA, NIFC, FEMA)
│   │   ├── model/                  # Multi-hazard GBDT, PyTorch models, and benchmark artifacts
│   │   └── steps/                  # ETL extraction and transformation scripts
│   │
│   ├── tests/                      # Automated test suite (28 passing pytest tests)
│   └── requirements.txt            # Python dependencies
│
└── frontend/                       # Native iOS Client Application ("Heron")
    └── ios/
        ├── CrewSafe/               # Native Swift source code (iOS 17+)
        └── project.yml             # Declarative XcodeGen project specification
```

---

*Built with ❤️ at SwampHacks 2026 by Saaketh & Sai.*