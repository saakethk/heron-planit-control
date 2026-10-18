# Backend

The CrewSafe backend follows the layers in the backend architecture doc: intake, processing, storage, and API. It serves the exact REST and WebSocket contract the iOS app uses.

Out of the box it runs on **dummy data that goes through the real pipeline**. Simulated weather, NWS alerts, and lightning are published to the raw topics, then cleaned, scored by a stand-in model, turned into alerts, stored, and served. Moving to real data and the trained model means changing settings and adapters, not the API or the app.

## Quick start

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn crewsafe.api.main:app --host 0.0.0.0 --port 8000
```

- Interactive docs: http://localhost:8000/docs
- Health: http://localhost:8000/api/v1/health
- Startup takes about 4 seconds. It seeds 346 EIA plants and backfills 8 hours of history.

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
  config.py                 settings from env / .env
  contracts/                FROZEN CONTRACTS
    api.py                    REST + WebSocket JSON (mirrors frontend/ios/CrewSafe/Models/Models.swift)
    events.py                 messages on the bus (one model per Kafka topic)
  ingestion/                LAYER 1: intake
    sources/open_meteo.py     real: Open-Meteo forecast API (batched, imperial units)
    sources/nws.py            real: api.weather.gov active alerts for FL
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
    scoring/model.py          MODEL ADAPTER: DummyHazardModel now, LightGBMHazardModel ready
    scoring/rules.py          heat + wildlife rules, crew-report adjustments, compound index, factor text
    scoring/service.py        features -> model -> rules -> hazard.scores
    alerts/service.py         hysteresis, cooldowns, targeting, decision log
    alerts/delivery.py        push adapter (logs today; APNs/SMS go here)
    briefings.py              site briefing + 6 PM next-day briefing
  storage/                  LAYER 3: storage
    repository.py             the storage interface everything uses
    memory.py                 in-memory implementation (demo, tests)
    postgres.py + schema.sql  Postgres implementation and tables
    seed/                     346 plants (florida_sites.json) + demo history
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
| `GET /health` | Status, model version, scored sites, active holds | |
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

## Plugging in the real model and data

Each step is independent:

1. **Model.** Train in `model/` using `crewsafe.processing.features.build_features` and `FEATURE_COLUMNS`, so training and serving use the same features.
   - Save one LightGBM booster per hazard as `models/hazard_lgbm/<hazard>.txt`. The hazards are `lightning`, `flood`, `soil_saturation`, and `wildfire`. Add an optional `VERSION` file.
   - Set `MODEL_KIND=lightgbm`.
   - Using a different library means writing one class with `version` and `predict(features) -> {hazard: HazardPrediction}` in `scoring/model.py`.
   - Heat and wildlife are scored by rules in `scoring/rules.py`. Remove a hazard from the rules once the model covers it.
2. **Weather.** Set `WEATHER_SOURCE=open-meteo`. The payload shape is already what the transformer parses.
   - Drought index (KBDI), river gauges, and tides currently come from the dummy `extras` block. Add sources for them, then map them in `transformer.normalize_open_meteo`.
3. **NWS alerts.** Set `ALERT_SOURCE=nws` and a real `NWS_USER_AGENT`. The transformer matches alert polygons to site coordinates.
4. **Lightning.** Implement `LightningSource.fetch()` for the licensed feed (Vaisala, Earth Networks, or Xweather) and select it in `ingestion/sources/__init__.py`. Set `LIGHTNING_SOURCE=none` to turn the dummy off.
5. **Site layer.** Replace the placeholder `coastal`, `near_river`, `elevation_ft`, and `wildlife_habitat` values in `storage/seed/__init__.py` with GIS joins (FEMA, USGS, NLD).
6. **Storage.** Set `STORAGE=postgres` and `DATABASE_URL` in `.env`, then load the tables once with `psql "$DATABASE_URL" -f crewsafe/storage/schema.sql`.
7. **Push.** Implement `PushSender` with APNs, plus SMS fallback, in `processing/alerts/delivery.py`. `apns_payload()` already builds the body.
8. **Auth.** Set `AUTH_REQUIRED=true` and a real `JWT_SECRET` once the app has a login screen.
9. **Photos.** `routes/reports.py::_save_photo` writes to local disk. Swap it for S3 or GCS uploads.

Regenerate the plant list with `frontend/ios/scripts/export_sites.py`. It writes both the app copy and `crewsafe/storage/seed/florida_sites.json`.

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
  - Local mode end to end: 15 pytest tests pass.
  - The app's Swift models decode every response (`tools/ios_contract_check`).
  - The iOS app runs against this server in the simulator with `-useLiveBackend YES`.
- **Written but not yet run:** Kafka mode, `PostgresRepository`, the Open-Meteo and NWS clients, and the LightGBM adapter. They need a Kafka broker, a Postgres database, network access, and a trained model.
