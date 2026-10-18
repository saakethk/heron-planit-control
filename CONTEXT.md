# Heron — application context and changes

This is the working record of **Heron**, a SwampHacks project for Florida utility field crews. The Xcode target and most package names are still `CrewSafe`; the name people see on the phone is **Heron**.

The original task list lives in [`README.md`](README.md). How to run the stack is also summarized at the end of this file.

---

## What it is

Heron watches weather, lightning, flooding, heat, wildfire, soil, and wildlife around **346 EIA-860M Florida power plants** and turns that into:

- A **0–10 Hazard Index** per site (low / moderate / high / severe)
- A **10-mile lightning stop-work** rule with a 30-minute all-clear that resets on each new strike
- **Real-time alerts** and a **6 PM next-day briefing**
- A **Sites map** that ranks plants near you (PlanIt-style supervisor view)
- **Crew hazard reports** with a photo

Tracks: Sperry PlanIt Control, and UF DSI “most creative use of AI.”

---

## Layout

```
swamphacks-project/
├── pipeline/     Training data, EIA/FEMA join, RandomForest artifact
├── backend/      FastAPI + in-process pipeline (default) that the app calls
└── frontend/ios  Native SwiftUI app (iOS 17+), generated with XcodeGen
```

There is **no Docker**. Secrets go in `backend/.env` (see `.env.example`). Do not commit `.env`.

---

## How the pieces fit

```
Open-Meteo / NWS / GOES-19 GLM
        │
        ▼
backend (local mode: one process, in-memory bus)
  pollers → transformer → lightning holds → RF model + rules → alerts
        │
        ├── REST  /api/v1/*
        └── WebSocket  /api/v1/ws/updates
                │
                ▼
         Heron iOS app
```

`PIPELINE_MODE=local` (default) runs every service inside uvicorn. Kafka + Postgres exist as optional code paths and have not been run end-to-end.

The iOS app talks only to `HazardAPI` and `RealtimeService`. Launch with `-useLiveBackend YES` (already on in the CrewSafe scheme) to hit `http://localhost:8000`. Without that argument it uses built-in mock data.

---

## Work so far (in order)

### 1. Problem and data

- Parsed the PlanIt brief; scoped Florida plants, lightning 10 mi / 30 min, flood after heavy rain, 6 PM briefing, crew reports, supervisor map, 0–10 index.
- EDA on OSHA incidents and EIA plants (~346 Florida sites).
- Cleaned weather + incident tables; built a training set of incident vs non-incident days.
- Added more sources (wildfire, FEMA flood zones). Model artifact: `pipeline/model/artifacts/best_hazard_model.joblib` (`RandomForestClassifier`).

### 2. First app + backend scaffold

Merged as **PlanIt-Mockup** (`c294ba2` / PR #8):

- Native SwiftUI app: Today, Sites (MapKit + ranked list), Alerts, Report, Settings.
- Notifications, camera, location, background refresh.
- Mock store that matches the Figma/Python mockup; 346 plants from `florida_sites.json`.
- Layered backend: intake → bus → processing → storage → REST/WebSocket, matching the iOS JSON contract (snake_case, ISO-8601 **without** fractional seconds).

### 3. Pipeline cleanup

PR #9: pipeline data/model cleanup. The backend later reads sites and the trained model from `pipeline/data/incidents.db` and `pipeline/model/artifacts/`.

### 4. Live data (`DATA_SOURCE=real`, the default)

The dummy world is still there (`DATA_SOURCE=dummy`). Live mode wires:

| Feed | Source | Notes |
|---|---|---|
| Weather | Open-Meteo | Current + daily/soil model inputs. 0.1° grid (~223 cells for 346 plants). Paced to ~500 weighted calls/min. Current weather every 2700s; model inputs every 21600s. |
| Alerts | NWS `api.weather.gov` | Florida `status=actual`. SAME county codes (e.g. `012001` = Alachua). Beach/marine products dropped. |
| Lightning | NOAA GOES-19 GLM on public S3 | In-cloud and CG both count for the 10 mi rule. Thinned to one flash per 0.04° cell. |
| Sites | EIA-860M in `incidents.db` | Joined to FEMA NFHL (`flood_zone`, SFHA, coastal). Shown on site detail. |
| Model | Pipeline RandomForest | `10 * P(hazard) / (P(hazard) + P(None))`, then a **plausibility gate** so ordinary days do not over-score. Deterministic floors: GLM within 10/30 mi, thunderstorm at site, heat index ≥ 105/115°F, ≥ 25 mm rain in a FEMA floodplain. |

Still not live: Keetch-Byram, USGS river stage, NOAA tides, paid CG lightning, APNs/SMS, login, Kafka/Postgres in practice.

### 5. Simulate (app + server prompt)

Demo events go through the **same topics** as live weather, so scoring, holds, WebSocket, and notifications all fire.

- `POST /api/v1/simulate` with `{ "kind": "lightning" }` or `{ "prompt": "lightning at 664" }`.
- Kinds: `lightning`, `heat`, `flood`, `briefing`, `clear`.
- Site targeting: EIA id (`664`), plant name (`Turkey Point`, `John R Kelly`), or county. Words that work: `at` / `for` / `near` / `on`. Default site is **664 John R Kelly**.
- Simulated lightning holds last **60 seconds** so the all-clear is visible.
- Heat is ~113°F heat index; flood is ~3.5 in rain + a Flood Warning.

From the app: **Settings → Simulate**.

From the server:

```bash
.venv/bin/python -m crewsafe.prompt
.venv/bin/python -m crewsafe.prompt "lightning at 664"
.venv/bin/python -m crewsafe.prompt "flood at Turkey Point"
.venv/bin/python -m crewsafe.prompt briefing
```

Tests: `backend/tests/test_simulate.py`.

### 6. Heron UI and branding

Display name, usage strings, and onboarding say **Heron**. The Xcode project, bundle id (`com.swamphacks.crewsafe`), and folder stay `CrewSafe` so XcodeGen paths do not break.

- Marsh palette: dark teal background, teal accent `#38629E`-like RGB `0.22, 0.62, 0.62`.
- App icon: stylized heron on dark teal (`Assets.xcassets/AppIcon.appiconset/AppIcon.png`, 1024).
- Today: dropped the extra location chip; briefing / drivers / alerts capped (3 each); conditions wrap 4-across or 2×2; risk bar uses flexible capsules.
- Sites: “Risk near you” is a compact bottom strip. It uses the map’s safe area (not a `GeometryReader` overlay that ate the map). Extra bottom clearance for iOS 26’s floating tab bar. Filters are lightning / flood / heat / wildfire.
- Alerts: All / Unread / Stop work / My site.
- Site detail: smaller gauge, fewer stacked sections.

Verified on the iPhone 17 simulator against the live backend: Sites map + risk bar sit above the tab bar; Today / Alerts / Report stay readable.

---

## iOS surface

| Tab | Role |
|---|---|
| Today | Home site index, stop-work banner, conditions, briefing, top drivers, recent alerts |
| Sites | Map of pins/dots, search, location chip, **Risk near you** list (nearby or statewide) |
| Alerts | Grouped today / earlier; acknowledge; open site |
| Report | Type, nearest site, photo, notes, GPS |

Sheets: site picker, next-day briefing, settings, location onboarding, site detail.

Useful launch arguments (scheme already has `-useLiveBackend YES`):

| Argument | Effect |
|---|---|
| `-useLiveBackend YES` | Talk to the backend instead of mock data |
| `-apiBaseURL <url>` | Override host (needed on a physical phone) |
| `-skipNotificationPrompt YES` | Do not ask for notifications on start |
| `-chooseLocation YES\|NO` | Show or skip first-launch location |
| `-location Miami` | Preset city from the picker |
| `-initialTab sites\|alerts\|report` | Opening tab |
| `-showSite 617` | Open a site sheet after launch |

On a phone, Debug builds use `CREWSAFE_DEV_SERVER_HOST` from `frontend/ios/project.yml` (`<Mac>.local`). The phone must be on the same network and allow Local Network access.

---

## API the app actually uses

Base: `/api/v1`

| Call | Why |
|---|---|
| `GET /sites` | Snapshot of all plants |
| `GET /sites/{id}/briefing` | Today’s site briefing |
| `GET /lightning/holds` | Active stop-work timers |
| `GET /alerts`, `POST /alerts/{id}/ack` | Alert list + acknowledge |
| `GET /briefings/next-day` | 6 PM outlook |
| `GET /reports`, `POST /reports` | Crew reports (JPEG as base64) |
| `POST /devices` | APNs token (registration only; remote push not wired) |
| `POST /simulate` | Demo events |
| `PUT /me/subscription` | Location, home site, followed sites |
| `WS /ws/updates` | `hazard_index_updated`, `hazard_index_batch`, `alert`, `lightning_strike` |

Hazard types in JSON: `lightning flood heat wildfire wildlife soil_saturation other`. Severities: `advisory warning stop_work`. Rain field is `rain24h_in` (not `rain_24h_in`) so Swift decoding stays `rain24hIn`.

---

## How to run

### Backend

```bash
cd swamphacks-project/backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn crewsafe.api.main:app --host 0.0.0.0 --port 8000
```

Health: http://localhost:8000/api/v1/health  
Docs: http://localhost:8000/docs

First response is immediate; all 346 sites score over about a minute (Open-Meteo pacing).

Offline demo: `DATA_SOURCE=dummy` in `backend/.env`.

### iOS

Needs Xcode (command-line tools pointed at the app, not just CLT) and [XcodeGen](https://github.com/yonaskolb/XcodeGen).

```bash
cd swamphacks-project/frontend/ios
xcodegen generate
open CrewSafe.xcodeproj
```

Pick an iPhone simulator, Run (⌘R). Re-run `xcodegen generate` after adding or removing Swift files. `CrewSafe.xcodeproj` is gitignored.

Mock-only: uncheck `-useLiveBackend YES` in the scheme.

### Tests

```bash
cd swamphacks-project/backend
.venv/bin/pytest -q
```

`tools/ios_contract_check/run.sh` decodes live JSON with the app’s `Models.swift` (server must be up).

---

## What is still open

- Kafka mode and Postgres repository: written, not exercised.
- Remote APNs / SMS: local notifications work; the push adapter logs only.
- Login: JWT exists (`POST /auth/login`) but the app has no auth UI; `AUTH_REQUIRED` defaults off.
- USGS / drought / tides and licensed CG lightning.
- Target/folder rename from `CrewSafe` to `Heron` (display name only, on purpose).
- Physical-device check of the Heron icon and Sites risk bar (simulator was used).

---

## Constraints we kept

- No Docker.
- No secrets in git.
- Do not commit unless asked.
- iOS scheme stays on `-useLiveBackend YES` for the live demo.
- Do not rename the Xcode target/folder just to match the brand (XcodeGen path risk).
