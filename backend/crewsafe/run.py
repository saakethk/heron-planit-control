"""Run one pipeline service as its own process (Kafka mode).

    python -m crewsafe.run poller|transformer|lightning|scoring|alerts

The API runs separately: `uvicorn crewsafe.api.main:app`.
"""

from __future__ import annotations

import asyncio
import logging
import sys

from .config import get_settings
from .runtime import _every, attach_poller, bootstrap, build_pipeline, create_bus, ensure_seeded, stop

SERVICES = ["poller", "transformer", "lightning", "scoring", "alerts"]


async def main(name: str) -> None:
    settings = get_settings()
    p = build_pipeline(settings, bus=create_bus(settings, client_id=f"crewsafe-{name}"))
    await ensure_seeded(p)
    loops = []
    if name == "transformer":
        p.transformer.register()
        loops.append(_every(300, p.transformer.flag_stale, "stale check"))
    elif name == "lightning":
        p.lightning.register()
        loops.append(p.lightning.run())
    elif name == "scoring":
        p.scoring.register()
    elif name == "alerts":
        p.alerts.register()
    await p.bus.start()
    if name == "poller":
        await attach_poller(p)
        await bootstrap(p)
        loops.append(p.poller.run())
    try:
        await asyncio.gather(*loops) if loops else await asyncio.Event().wait()
    finally:
        await stop(p)


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in SERVICES:
        sys.exit(f"usage: python -m crewsafe.run {{{'|'.join(SERVICES)}}}")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    asyncio.run(main(sys.argv[1]))
