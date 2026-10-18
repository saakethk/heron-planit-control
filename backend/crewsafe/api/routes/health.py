from __future__ import annotations

from fastapi import APIRouter, Depends

from ...contracts.api import Health
from ...runtime import Pipeline
from ..deps import get_pipeline

router = APIRouter(tags=["health"])


@router.get("/health", response_model=Health)
async def health(p: Pipeline = Depends(get_pipeline)) -> Health:
    scores = await p.repo.latest_scores()
    conditions = await p.repo.all_latest_conditions()
    s = p.settings
    return Health(
        data_sources={"weather": s.weather_source, "alerts": s.alert_source, "lightning": s.lightning_source},
        last_weather_at=max((c.obs_time for c in conditions.values()), default=None),
        stale_sites=sum(c.data_stale for c in conditions.values()),
        status="ok",
        pipeline_mode=p.settings.pipeline_mode,
        storage=p.settings.storage,
        model_version=p.model_version,
        sites=len(await p.repo.list_sites()),
        scored_sites=len(scores),
        last_scored_at=max((s.computed_at for s in scores.values()), default=None),
        active_holds=len(await p.repo.list_holds()),
    )
