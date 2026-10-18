from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ...contracts.api import SimulateIn, SimulateOut
from ...processing.simulate import run
from ...runtime import Pipeline
from ..deps import current_user, get_pipeline

router = APIRouter(prefix="/simulate", tags=["simulate"])


@router.post("", response_model=SimulateOut)
async def simulate(body: SimulateIn, p: Pipeline = Depends(get_pipeline),
                   _user=Depends(current_user)) -> SimulateOut:
    """Inject a scripted lightning strike, flood, heat spike, or next-day
    briefing into the live pipeline. Body is either `{"kind":"lightning","site_id":664}`
    or a natural-language `{"prompt":"flood at Turkey Point"}`.
    From the server: `python -m crewsafe.prompt`."""
    try:
        return await run(p, body)
    except KeyError as exc:
        raise HTTPException(404, f"unknown site {exc.args[0]}") from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
