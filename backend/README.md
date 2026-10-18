# Backend

The CrewSafe backend follows the layers in the backend architecture doc: intake, processing, storage, and API. It serves the exact REST and WebSocket contract the iOS app uses.

Out of the box (`DATA_SOURCE=real`) it reads **live weather, alerts, and lightning** and scores every site with the pipeline's trained classifier. Open-Meteo current conditions and daily aggregates, NWS county alerts (matched by SAME codes), and NOAA GOES-19 GLM flashes feed the same topics the dummy world uses. `DATA_SOURCE=dummy` is the offline simulated world for demos and tests.

## Quick start

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn crewsafe.api.main:app --host 0.0.0.0 --port 8000
```

- Interactive docs: http://localhost:8000/docs
- Health: http://localhost:8000/api/v1/health
- First response is immediate. Live Open-Meteo is paced to the free-tier per-minute limit, so all 346 sites fill in over about a minute. It seeds the EIA plants from `pipeline/data/incidents.db` (with FEMA flood zones) and backfills the index chart from Open-Meteo's hourly history.

### Simulate from the server prompt

With the server running, type commands in another terminal. They go through the same pipeline as live weather, so the app updates and notifies.

```bash
.venv/bin/python -m crewsafe.prompt
# or one shot:
.venv/bin/python -m crewsafe.prompt "lightning at 664"
.venv/bin/python -m crewsafe.prompt "flood at Turkey Point"
.venv/bin/python -m crewsafe.prompt briefing
```

`simulate>` lightning · flood · heat · briefing · clear. You can name a site (`at Turkey Point`) or an EIA id (`664`). Default is John R Kelly (664).

### Run the app against the backend

In Xcode, open *Product > Scheme > Edit Scheme > Run > Arguments* and add `-useLiveBackend YES`. Without it, the app uses its built-in mock data.

On a physical phone, Debug builds use `CREWSAFE_DEV_SERVER_HOST` from `frontend/ios/project.yml` (your Mac's `scutil --get LocalHostName` plus `.local`). The phone must be on the same network, and you must allow the Local Network prompt. `-apiBaseURL <url>` overrides the address.

### Tests

```bash
.venv/bin/pytest -q                  # contract, pipeline, WebSocket, auth
tools/ios_contract_check/run.sh      # server must be running: decodes live responses with the app's Models.swift
```

## Layout

Each folder maps to a layer in the architecture doc:

```
crewsafe/
  config.py                 settings from env / .env (DATA_SOURCE=real|dummy)
  pipeline_bridge.py        read-only access to pipeline/ (sites, FEMA, trained model)
  contracts/                FROZEN CONTRACTS
    api.py                    REST + WebSocket JSON (mirrors frontend/ios/CrewSafe/Models/Models.swift)
    events.py                 messages on the bus (one model per Kafka topic)
  ingestion/                LAYER 1: intake
    sources/open_meteo.py     real: Open-Meteo (current + daily/soil model inputs, paced)
    sources/nws.py            real: api.weather.gov active alerts for FL (SAME county codes)
    sources/glm.py            real: NOAA GOES-19 GLM flashes from the public S3 bucket
    sources/dummy.py          dummy world: Open-Meteo-shaped weather, NWS-style alerts, moving storm cells
    poller.py                 fetch on intervals -> raw.weather, raw.nws.alerts, raw.lightning
  messaging/                Kafka topics + bus
    topics.py                 topic names
    bus.py                    MessageBus interface + in-memory bus (the no-Kafka fallback)
    kafka_bus.py              aiokafka bus (at-least-once, commit after handling)
  processing/               LAYER 2: processing
    features.py               SHARED FEATURE MODULE (training and serving import this)
    transformer.py            validate, normalize, dedupe (site_id, obs_time), derive, flag stale
    lightning.py              30-min stop-work timer on the server: holds start / extend / clear
    scoring/model.py          MODEL ADAPTER: PipelineHazardModel (default), DummyHazardModel, LightGBMHazardModel
    scoring/rules.py          heat + wildlife rules, crew-report adjustments, compound index, factor text
    scoring/service.py        features -> model -> rules -> hazard.scores
    alerts/service.py         hysteresis, cooldowns, targeting, decision log
    alerts/delivery.py        push adapter (logs today; APNs/SMS go here)
    briefings.py              site briefing + 6 PM next-day briefing
  storage/                  LAYER 3: storage
    repository.py             the storage interface everything uses
    memory.py                 in-memory implementation (demo, tests)
    postgres.py + schema.sql  Postgres implementation and tables
    seed/                     346 plants from pipeline/data/incidents.db (FEMA join) or florida_sites.json
  api/                      LAYER 4: API
    main.py                   app factory; in local mode it also runs the pipeline
    routes/                   one file per resource
    realtime.py               WebSocket hub: subscribe, seq, replay, batching
    auth.py, deps.py          JWT (supervisor / crew), optional while the app has no login
    errors.py                 every error is {"error", "detail"}
  runtime.py                wires layers; local mode vs Kafka mode
  run.py                    `python -m crewsafe.run <service>` for Kafka mode
```

## Data flow

```
pollers ─► raw.weather ──────► transformer ─► clean.conditions ─┐
        ─► raw.nws.alerts ───► transformer ─► clean.nws.alerts ─┼─► alerts ─► alerts.issued ─┐
        ─► raw.lightning ────► lightning ──► lightning.holds ───┤        └─► push (APNs)     │
                                         └─► lightning.site_strikes ─► scoring ─► hazard.scores
API POST /reports ─────────────────────────► crew.reports ─────► scoring + alerts            │
                                                                                             ▼
                              storage (memory / Postgres) ◄── every service   API + WebSocket hub ─► app
```

Two run modes share the same code:

| Mode | How | Use |
|---|---|---|
| `PIPELINE_MODE=local` (default) | One process. All services run on the in-memory bus with in-memory storage. | Demo, development, tests. This is the doc's "fallback without Kafka". |
| `PIPELINE_MODE=kafka` | `pip install -r requirements-pipeline.txt`, point `KAFKA_BOOTSTRAP` and `DATABASE_URL` at your own Kafka and Postgres, then run the API plus one `python -m crewsafe.run <service>` per service (poller, transformer, lightning, scoring, alerts). | Production shape. Optional; the demo doesn't need it. |

## API (base `/api/v1`)

| Method and path | Purpose | Used by the app today |
|---|---|---|
| `GET /health` | Status, model version, scored sites, data sources, stale sites | |
| `POST /auth/login` | JWT for `supervisor` / `crew` | |
| `GET /sites?view=full\|summary&site_ids=` | All sites with index, factors, conditions, today's history; ETag | Yes |
| `GET /sites/nearby?lat=&lon=&limit=25&offset=` | Sites by distance; `X-Total-Count` | |
| `GET /sites/{id}` | One site in full | |
| `GET /sites/{id}/briefing` | Today's site briefing | Yes |
| `GET /sites/{id}/hazard` | Full model output: drivers, adjustments, model version | |
| `GET /lightning/holds` | Active stop-work holds (server-side 30-min timer) | Yes |
| `GET /alerts?site_ids=&since=&limit=` | Alerts, newest first, per-user `acknowledged` | Yes |
| `POST /alerts/{id}/ack` | Acknowledge (204) | Yes |
| `GET /briefings/next-day?site_ids=` | 6 PM outlook; defaults to the caller's followed sites | Yes |
| `GET /reports`, `POST /reports` | Crew reports; JSON with base64 `photo_jpeg`; idempotent on `id` | Yes |
| `POST /devices` | APNs token | Yes |
| `POST /simulate` | Inject lightning / heat / flood / briefing / clear (`kind` or a `prompt` string) | Yes |
| `PUT /me/subscription` | Location, home site, followed sites (204) | Yes |
| `GET /decision-log` | Why each alert was sent or suppressed (supervisor) | |

Contract rules, enforced by tests:
- Keys are snake_case.
- Dates are ISO-8601 UTC **without fractional seconds**, because the app's `.iso8601` decoder rejects them.
- Hazard types: `lightning flood heat wildfire wildlife soil_saturation other`.
- Severities: `advisory warning stop_work`.
- The rain field is `rain24h_in`, not `rain_24h_in`, because Swift's snake_case conversion would turn the latter into `rain24HIn`.

### WebSocket `/api/v1/ws/updates`

App to server:
- `{"type":"subscribe","payload":{"site_ids":[...],"include_severe_statewide":true,"last_seq":41}}`
- `{"type":"ping"}`

Server to app: `{"type","seq","payload"}`. The types the app reads:
- `hazard_index_updated`;
- `hazard_index_batch` (index updates collected for 0.5 s into one message);
- `alert`;
- `lightning_strike`.

Also sent, and ignored by the app for now: `subscribed`, `lightning_hold_updated`, `lightning_hold_cleared`, `report_created`, `resync_required`, `pong`.

On reconnect with `last_seq`, the server replays missed events from a buffer of the last 2,000 events. If the gap is older than that, it sends `resync_required`.

## Live data (default) and what is still a stub

`DATA_SOURCE=real` (the default) already wires:

1. **Model.** `pipeline/model/artifacts/best_hazard_model.joblib`, a `RandomForestClassifier` trained on Open-Meteo archive days plus FEMA fields. Scores are `10 * P(hazard) / (P(hazard) + P(None))`, then scaled by a plausibility gate (heat needs a hot day, flood needs rain, lightning needs showers/CAPE, wildfire needs dry air). Deterministic floors still apply: GLM flash within 10/30 mi, thunderstorm at the site, heat index ≥ 105/115°F, ≥ 25 mm rain in a FEMA floodplain.
2. **Weather.** Open-Meteo forecast API. Current conditions (imperial, every `WEATHER_INTERVAL`) plus daily aggregates and soil layers the model was trained on (metric, every `MODEL_INPUTS_INTERVAL` or at the UTC day rollover). Sites share a location on a `WEATHER_GRID_DEG` grid (0.1° ≈ 223 points). Free-tier requests are paced to 500 weighted calls/minute. Set `OPEN_METEO_API_KEY` to use the paid host and drop the cap.
3. **NWS alerts.** `api.weather.gov` active Florida alerts (`status=actual`). Beach/marine products are dropped. Most alerts have no polygon; the transformer matches SAME county codes (`012001` = Alachua) to each site's county.
4. **Lightning.** NOAA GOES-19 GLM L2 flashes from the public `noaa-goes19` S3 bucket, thinned to one flash per 0.04° cell. Both in-cloud and cloud-to-ground count for the 10-mile stop-work rule.
5. **Site layer.** EIA-860M plants from `pipeline/data/incidents.db`, joined to FEMA NFHL flood zones (`flood_zone`, SFHA, coastal, risk score). The app shows the zone on the site detail screen.

Still not live (dummy-only or unused):

- Keetch-Byram drought index, USGS river stage, and NOAA tides. The dummy world's `extras` block still supplies them; live mode leaves them unset and the model/rules fall back to defaults.
- Licensed CG lightning (Vaisala / Earth Networks / Xweather) if you need cloud-to-ground only. Plug a `LightningSource` into `ingestion/sources/__init__.py`.
- Postgres, Kafka, APNs/SMS, login. Same as before: `STORAGE=postgres`, `PIPELINE_MODE=kafka`, implement `PushSender`, set `AUTH_REQUIRED=true`.

Switch the whole stack to the offline demo with `DATA_SOURCE=dummy`. Override one feed with `WEATHER_SOURCE`, `ALERT_SOURCE`, `LIGHTNING_SOURCE`, or `MODEL_KIND`.

Regenerate the plant list with `frontend/ios/scripts/export_sites.py`. It writes both the app copy and `crewsafe/storage/seed/florida_sites.json` (used only if the pipeline database is missing).

## Differences from the architecture doc

The layers, the topic flow, and the reliability rules follow the doc. There is no Docker setup; the backend runs as a plain Python process. These parts follow the current app instead:

| Doc (older) | Now |
|---|---|
| Green/yellow/orange/red levels | 0-10 Hazard Index with factor scores; bands are low, moderate, high, severe |
| Doc endpoint list | Endpoints the app calls (table above), plus `/sites/nearby`, `/sites/{id}/hazard`, `/decision-log` |
| One model output | Per-hazard scores: model for lightning, flood, soil, and wildfire; rules for heat and wildlife; compound index |
| No lightning engine | `raw.lightning` → `lightning.site_strikes` / `lightning.holds` with the 10 mi / 30 min policy on the server |
| WebSocket forwards raw messages | Subscription filter, `seq`, replay, batching, and statewide severe events |

## Status

- **Verified:**
  - Local mode end to end on dummy data (pytest) and on live Open-Meteo / NWS / GLM + the pipeline model.
  - The app's Swift models decode every response (`tools/ios_contract_check`). Extra fields (`flood_zone`, `data_sources`) are ignored until the app is rebuilt.
  - The iOS app runs against this server in the simulator with `-useLiveBackend YES`. Settings → Backend shows "Live API".
- **Written but not yet run:** Kafka mode and `PostgresRepository`. They need a Kafka broker and a Postgres database.
