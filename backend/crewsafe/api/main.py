"""FastAPI app.

    uvicorn crewsafe.api.main:app --reload --host 0.0.0.0 --port 8000

In local mode (default, DATA_SOURCE=real) this one process also runs the whole
pipeline: Open-Meteo weather, NWS alerts, GOES GLM lightning, and the pipeline's
trained hazard model. Set DATA_SOURCE=dummy for the offline simulated world.
In Kafka mode it only serves the API and forwards pipeline events.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket
from fastapi.staticfiles import StaticFiles

from ..config import DEV_JWT_SECRET, Settings, get_settings
from ..runtime import build_pipeline, ensure_seeded, start_local, stop
from . import errors
from .deps import principal_from_token
from .realtime import RealtimeHub
from .routes import ROUTERS

API_PREFIX = "/api/v1"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    if settings.auth_required and settings.jwt_secret == DEV_JWT_SECRET:
        logging.getLogger(__name__).warning("AUTH_REQUIRED is on but JWT_SECRET is the development default")
    hub = RealtimeHub()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        pipeline = build_pipeline(settings)
        hub.register(pipeline.bus)
        app.state.pipeline = pipeline
        app.state.hub = hub
        if settings.pipeline_mode == "local":
            await start_local(pipeline)
        else:
            await ensure_seeded(pipeline)
            await pipeline.bus.start()
        yield
        await stop(pipeline)

    app = FastAPI(
        title="Heron API",
        version="0.1.0",
        summary="Hazard Index, lightning holds, alerts, briefings, and crew reports for Florida utility sites.",
        lifespan=lifespan,
    )
    errors.install(app)
    for router in ROUTERS:
        app.include_router(router, prefix=API_PREFIX)

    @app.websocket(f"{API_PREFIX}/ws/updates")
    async def updates(socket: WebSocket) -> None:
        if settings.auth_required:
            try:
                principal = principal_from_token(settings, socket.query_params.get("token"))
            except HTTPException:
                principal = None
            if principal is None:
                await socket.close(code=4401)
                return
        await hub.serve(socket)

    Path(settings.photo_dir).mkdir(parents=True, exist_ok=True)
    app.mount(f"{API_PREFIX}/photos", StaticFiles(directory=settings.photo_dir), name="photos")
    return app


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
app = create_app()
