# Heron: Native iOS Field Safety Client

**Enterprise Environmental Intelligence & Worker Safety Application for Florida Utility Field Crews**

The Heron iOS application is a native **SwiftUI (iOS 17+)** client engineered for electric utility linemen, field technicians, and operations supervisors. Designed specifically for readability under direct, high-glare Florida sunlight, Heron delivers real-time site telemetry, automated OSHA stop-work countdowns, interactive supervisor risk mapping across **346 Florida power facilities**, and crowd-sourced hazard reporting.

---

## 📱 Core Views & User Experience

Heron is organized around four purpose-built tabs engineered for rapid decision-making in the field:

### 1. Today Tab (Crew Situational Awareness)
The operational home screen for field crews assigned to a specific job site:
- **Active Stop-Work Countdown Banner**: When a lightning strike is detected within 10 miles, an unmistakable amber/crimson banner locks to the top of the screen displaying the active **30-minute countdown timer**.
- **6:00 PM Daily Safety Briefing Card**: Pinned daily briefing analyzing projected heat indices, convective storm risks, and required PPE for the following shift.
- **Site Telemetry Grid**: Real-time atmospheric metrics (ambient temperature, Heat Index, sustained winds, peak gusts, relative humidity) and 3-layer soil moisture readings.
- **Quick Hazard Action**: One-tap shortcut to launch the camera and file a field report.

### 2. Sites Tab (Supervisor PlanIt Dashboard)
A command center for dispatchers and field supervisors monitoring distributed crews:
- **Interactive MapKit View**: Statewide map pinning all 346 EIA-860M Florida power facilities, color-coded by real-time Hazard Index.
- **"Risk Near You" Ranking Carousel**: Horizontally scrolling strip ranking sites from highest risk to lowest, allowing supervisors to immediately see which facilities require attention.
- **Multi-Hazard Filter Chips**: Instant filtering by hazard type (⚡ *Lightning*, 🌊 *Flood*, 🔥 *Extreme Heat*, 🌲 *Wildfire*).
- **Distance Grouping**: Categorizes facilities into nearby active sites, followed sites, and statewide infrastructure.

### 3. Alerts Tab (Incident & Mandate Center)
A centralized stream of real-time safety notifications:
- **Prioritized Severity Tiers**: Color-coded into `Stop-Work` (mandatory hold), `Warning` (elevated hazard), and `Advisory` (situational notice).
- **One-Tap Acknowledgment**: Linemen confirm receipt of critical safety directives, logging confirmation back to the central control room.
- **OSHA Actionable Directives**: Clear guidance accompanying each alert (e.g. *"Seek shelter in enclosed vehicles or grounded structures; disconnect high-voltage leads"*).

### 4. Report Hazard View (Waze-Style Field Reporting)
Enables linemen to crowdsource hazard intelligence in seconds:
- **Camera & Photo Library Integration**: Instant capture of on-site obstacles (substation flooding, downed lines, gator sightings, mud washouts).
- **Automatic High-Precision GPS Tagging**: Stamped coordinates bind the hazard to the exact site location.
- **Categorization**: Multi-select tags for *Wildlife / Gator*, *Mud & Soil Saturation*, *Downed Equipment*, and *Access Road Washout*.
- **Instant Control Room Broadcast**: Automatically syncs with the backend database and updates supervisor maps statewide.

---

## 🎨 High-Glare "Marsh" Design Tokens

Operating outdoors in Florida requires specialized visual accessibility. Heron rejects low-contrast pastels in favor of the **Marsh Color Palette**, calibrated for outdoor readability under intense solar glare:

- **Hazard Crimson (`#DC2626`)**: Reserved exclusively for mandatory Stop-Work directives and critical lightning holds.
- **Alert Amber (`#F59E0B`)**: Used for warnings, elevated heat indices ($\ge 105^\circ\text{F}$), and active countdown timers.
- **Safety Emerald (`#10B981`)**: Signals normal, safe operating conditions (Hazard Index 0–3).
- **High-Contrast Slate (`#0F172A`)**: Deep background surfaces that prevent wash-out in bright outdoor light.

---

## 🛠 Architecture & State Management

```
frontend/ios/CrewSafe/
├── CrewSafeApp.swift           # Application entrypoint & APNs push notification handling
├── AppStore.swift              # Central observable state store, WebSocket listener & hold timer
│
├── Views/                      # Native SwiftUI views
│   ├── RootView.swift          # Tab navigation & persistent Stop-Work banner host
│   ├── DashboardView.swift     # "Today" tab: site briefing, weather metrics, countdown
│   ├── SitesView.swift         # "Sites" tab: Supervisor MapKit map & ranked site carousel
│   ├── SiteDetailView.swift    # Deep-dive facility view with FEMA flood zones
│   ├── AlertsView.swift        # Prioritized alert feed with acknowledgment actions
│   ├── ReportHazardView.swift  # Waze-style hazard reporting with camera integration
│   ├── SettingsView.swift      # Live/Mock toggles, simulation triggers & backend config
│   └── Components/             # Reusable UI tokens, camera pickers, and hazard gauges
│
├── Services/                   # Network & Hardware interfaces
│   ├── HazardAPI.swift         # REST client communicating with FastAPI backend
│   ├── RealtimeService.swift   # WebSocket client with sequence buffering and auto-reconnect
│   ├── NotificationManager.swift # Time-sensitive local and remote APNs notifications
│   ├── LocationManager.swift   # High-accuracy CoreLocation manager
│   └── BackgroundRefresh.swift # Background push and telemetry polling tasks
│
└── Models/                     # Swift data structures mirroring Python Pydantic contracts
    ├── Models.swift            # Site, HazardAlert, LightningHold, DailyBriefing, RealtimeEvent
    └── MockData.swift          # Offline mock fallback dataset for field use
```

---

## 🚀 Building & Running the App

### 1. Prerequisites
- **macOS** with **Xcode 15+** installed.
- [**XcodeGen**](https://github.com/yonaskolb/XcodeGen) for declarative, merge-conflict-free project generation:
  ```bash
  brew install xcodegen
  ```

### 2. Generate and Open the Xcode Project
```bash
cd frontend/ios
xcodegen generate
open CrewSafe.xcodeproj
```

### 3. Run with Live Backend or Built-In Mock Data
- **Live Backend Mode (Default for Full Stack)**:
  1. Ensure the Python backend is running (`uvicorn crewsafe.api.main:app --host 0.0.0.0 --port 8000`).
  2. In Xcode, navigate to **Product > Scheme > Edit Scheme > Run > Arguments**.
  3. Add the launch argument: `-useLiveBackend YES`.
  4. (For physical iPhone testing over Wi-Fi, add: `-apiBaseURL http://<your-mac-name>.local:8000/api/v1/`).
  5. Press **<kbd>Cmd</kbd> + <kbd>R</kbd>** to build and run.

- **Offline Demonstration Mode**:
  Run without the launch argument. Heron will run on its built-in dataset containing all 346 Florida power facilities, complete with simulated real-time event feeds every 8–12 seconds.

---

## 🔔 Simulating Push Notifications Locally

You can test time-sensitive emergency alerts on the iOS Simulator without an active Apple Developer subscription:

```bash
# Push a simulated lightning stop-work alert to the booted simulator:
xcrun simctl push booted com.swamphacks.crewsafe ios/push-samples/lightning.apns
```
*(You can also drag and drop any `.apns` file from `ios/push-samples/` directly onto the Simulator window).*
