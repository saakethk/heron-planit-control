"""FastAPI Core Service for PlanIT Control.

Exposes:
1. REST Endpoints:
   - GET  /health
   - GET  /api/v1/sites
   - GET  /api/v1/sites/{plant_id}
   - POST /api/v1/sites/{plant_id}/evaluate
   - POST /api/v1/reports/crew
   - GET  /api/v1/events/latest
   - POST /api/v1/model/retrain
2. WebSockets:
   - WS   /ws/hazards (Global stream)
   - WS   /ws/sites/{plant_id} (Per-site stream)
3. Background Event Bridge:
   - Consumes events from EventStreamPublisher and dispatches to active WebSockets.
"""

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import threading
from typing import Any, Dict, List, Optional

try:
    from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Query, status
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse
except ImportError:
    # Minimal fallback mock if fastapi is being imported outside server runner
    FastAPI = None

from pipeline.api.schemas import (
    CrewReportCreate,
    CrewReportResponse,
    HealthResponse,
    RetrainStatusResponse,
    SimulationRequest,
    SiteDetailResponse,
    SiteSummaryResponse,
)
from pipeline.api.websocket_manager import ws_manager
from pipeline.model.continuous_trainer import ContinuousTrainer
from pipeline.streaming.event_stream import EventStreamPublisher, EventStreamProducer

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "incidents.db"
MODEL_PATH = Path(__file__).resolve().parent.parent / "model" / "artifacts" / "best_hazard_model.joblib"

publisher = EventStreamPublisher()
producer = EventStreamProducer(publisher)
trainer = ContinuousTrainer()


# Background Task: Bridge EventStreamPublisher events into FastAPI WebSockets
async def event_stream_bridge(loop: asyncio.AbstractEventLoop):
    sub_q = publisher.register_subscriber()
    try:
        while True:
            # Non-blocking check in async loop
            try:
                msg_str = await loop.run_in_executor(None, sub_q.get, True, 1.0)
                event_data = json.loads(msg_str)
                await ws_manager.broadcast_event(event_data)
            except Exception:
                await asyncio.sleep(0.1)
    finally:
        publisher.unregister_subscriber(sub_q)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Launch WebSocket event bridge
    loop = asyncio.get_running_loop()
    bridge_task = asyncio.create_task(event_stream_bridge(loop))
    yield
    # Shutdown
    bridge_task.cancel()


def create_app() -> Any:
    if FastAPI is None:
        raise RuntimeError("FastAPI is not installed. Run 'pip install fastapi uvicorn websockets'.")

    app = FastAPI(
        title="PlanIT Control: Real-Time Environmental Hazard API",
        description="Unified REST & WebSocket gateway for electric utility jobsite safety across Florida.",
        version="2.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 1. Healthcheck
    @app.get("/health", response_model=HealthResponse)
    async def get_health():
        with sqlite3.connect(DB_PATH) as conn:
            cnt = conn.execute("SELECT COUNT(*) FROM monitored_sites").fetchone()[0]
        return {
            "status": "HEALTHY",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "model_version": type(producer.model).__name__,
            "monitored_sites_count": cnt,
            "active_stream_subscribers": len(ws_manager.active_connections),
        }

    # 2. List Monitored Florida Jobsites
    @app.get("/api/v1/sites", response_model=List[SiteSummaryResponse])
    async def list_sites(
        county: Optional[str] = None,
        min_capacity_mw: float = 0.0,
        limit: int = 50,
    ):
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            query = """
                SELECT m.plant_id, m.plant_name, m.utility_name, m.county, m.latitude, m.longitude,
                       m.capacity_mw, m.technology,
                       COALESCE(f.fld_zone, 'X') as fema_flood_zone,
                       COALESCE(f.is_sfha, 0) as is_sfha
                FROM monitored_sites m
                LEFT JOIN fema_flood_risk f ON round(m.latitude, 4) = f.Latitude AND round(m.longitude, 4) = f.Longitude
                WHERE m.capacity_mw >= ?
            """
            params: List[Any] = [min_capacity_mw]
            if county:
                query += " AND m.county LIKE ?"
                params.append(f"%{county}%")
            query += " ORDER BY m.capacity_mw DESC LIMIT ?"
            params.append(limit)

            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    # 3. Live Evaluation for Single Jobsite
    @app.get("/api/v1/sites/{plant_id}", response_model=SiteDetailResponse)
    async def get_site_hazard(plant_id: int):
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            q = """
                SELECT m.*, COALESCE(f.is_sfha, 0) as is_sfha, COALESCE(f.is_coastal_hazard, 0) as is_coastal,
                       COALESCE(f.fema_flood_risk_score, 0.05) as fema_score, COALESCE(f.fld_zone, 'X') as fld_zone
                FROM monitored_sites m
                LEFT JOIN fema_flood_risk f ON round(m.latitude, 4) = f.Latitude AND round(m.longitude, 4) = f.Longitude
                WHERE m.plant_id = ?
            """
            row = conn.execute(q, (plant_id,)).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail=f"Jobsite #{plant_id} not found in EIA-860M database")

            p_series = dict(row)

        evt = producer.evaluate_and_publish_site(p_series)
        return {
            "plant_id": evt.plant_id,
            "plant_name": evt.plant_name,
            "utility_name": p_series.get("utility_name", ""),
            "county": evt.county,
            "latitude": evt.latitude,
            "longitude": evt.longitude,
            "capacity_mw": p_series.get("capacity_mw", 0.0),
            "hazard_index": evt.hazard_index,
            "primary_hazard": evt.primary_hazard,
            "probabilities": evt.probabilities,
            "operational_status": evt.operational_status,
            "alert_message": evt.alert_message,
            "live_telemetry": evt.live_telemetry,
            "fema_flood_risk": evt.fema_flood_zone,
            "active_nws_warnings": evt.active_nws_warnings,
        }

    # 4. Ad-hoc Hypothetical Simulation
    @app.post("/api/v1/sites/{plant_id}/evaluate")
    async def evaluate_simulation(plant_id: int, sim: SimulationRequest):
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            q = """
                SELECT m.*, COALESCE(f.is_sfha, 0) as is_sfha, COALESCE(f.is_coastal_hazard, 0) as is_coastal,
                       COALESCE(f.fema_flood_risk_score, 0.05) as fema_score, COALESCE(f.fld_zone, 'X') as fld_zone
                FROM monitored_sites m
                LEFT JOIN fema_flood_risk f ON round(m.latitude, 4) = f.Latitude AND round(m.longitude, 4) = f.Longitude
                WHERE m.plant_id = ?
            """
            row = conn.execute(q, (plant_id,)).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Jobsite not found")

        evt = producer.evaluate_and_publish_site(
            dict(row),
            external_strike_miles=sim.external_strike_miles,
        )
        return evt

    # 5. Submit Field Crew Hazard Report
    @app.post("/api/v1/reports/crew", response_model=CrewReportResponse)
    async def submit_crew_report(report: CrewReportCreate):
        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO crew_hazard_reports
                (plant_id, reported_by, hazard_type, description, latitude, longitude, photo_url)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                report.plant_id, report.reported_by, report.hazard_type,
                report.description, report.latitude, report.longitude, report.photo_url
            ))
            report_id = cur.lastrowid
            conn.commit()

        # Emit report to WebSocket stream
        report_evt = {
            "event_type": "CREW_REPORT_SUBMITTED",
            "report_id": report_id,
            "plant_id": report.plant_id,
            "reported_by": report.reported_by,
            "hazard_type": report.hazard_type,
            "description": report.description,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await ws_manager.broadcast_event(report_evt)

        return {
            "report_id": report_id,
            "status": "RECORDED",
            "message": f"Hazard report logged and broadcast to operations stream.",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    # 6. Latest Stream Events Log
    @app.get("/api/v1/events/latest")
    async def get_latest_events(limit: int = Query(25, ge=1, le=100)):
        return publisher.get_latest(limit=limit)

    # 7. Continuous Retraining Trigger
    @app.post("/api/v1/model/retrain", response_model=RetrainStatusResponse)
    async def trigger_retraining():
        res = trainer.retrain_and_hotswap(min_f1_threshold=0.75)
        # Reload model in active producer
        producer.model = trainer.model_path
        # Broadcast retraining notification to all WebSockets
        await ws_manager.broadcast_event({
            "event_type": "MODEL_RETRAINED",
            "validation_macro_f1": res["validation_macro_f1"],
            "total_samples": res["total_samples"],
            "timestamp": res["timestamp"],
        })
        return res

    # 8. WebSockets Gateway: Global Broadcast
    @app.websocket("/ws/hazards")
    async def websocket_global(websocket: WebSocket):
        await ws_manager.connect_global(websocket)
        try:
            # Send initial handshake
            await websocket.send_json({
                "type": "CONNECTION_ESTABLISHED",
                "channel": "global_hazard_stream",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            while True:
                # Keepalive / listen for client ping
                data = await websocket.receive_text()
                if data == "ping":
                    await websocket.send_text("pong")
        except WebSocketDisconnect:
            ws_manager.disconnect_global(websocket)

    # 9. WebSockets Gateway: Site-Specific Channel
    @app.websocket("/ws/sites/{plant_id}")
    async def websocket_site(websocket: WebSocket, plant_id: int):
        await ws_manager.connect_site(plant_id, websocket)
        try:
            await websocket.send_json({
                "type": "CONNECTION_ESTABLISHED",
                "channel": f"site_{plant_id}_stream",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            while True:
                data = await websocket.receive_text()
                if data == "ping":
                    await websocket.send_text("pong")
        except WebSocketDisconnect:
            ws_manager.disconnect_site(plant_id, websocket)

    return app


try:
    app = create_app()
except Exception:
    app = None
