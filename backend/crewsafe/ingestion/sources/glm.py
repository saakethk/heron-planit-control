"""Real-time lightning from NOAA's GOES-East Geostationary Lightning Mapper (GLM).

GLM Level-2 flash files land in NOAA's public S3 bucket every 20 seconds
(`s3://noaa-goes19/GLM-L2-LCFA/<year>/<day-of-year>/<hour>/`), free and without
credentials. Each file lists every flash over the hemisphere with its centroid
and time. GLM sees in-cloud and cloud-to-ground flashes alike; both count for
the 10-mile stop-work rule.

Each poll downloads the files published since the last poll, keeps good-quality
flashes over Florida plus the 30-mile watch margin, and reduces them to the
latest flash per ~3-mile grid cell so a busy storm doesn't flood the pipeline
while nearest-flash distances stay accurate to about a mile and a half.
"""

from __future__ import annotations

import asyncio
import io
import logging
import re
from datetime import UTC, datetime, timedelta

import httpx

from ...contracts.common import utcnow
from ...contracts.events import RawLightningStrike

log = logging.getLogger(__name__)

# Florida plus ~30 mi on every side.
BBOX = (24.0, 31.5, -88.0, -79.5)  # lat min, lat max, lon min, lon max
CELL_DEG = 0.04
# On the first poll, only look this far back.
FIRST_LOOKBACK = timedelta(minutes=3)
MAX_FILES_PER_POLL = 12
START_RE = re.compile(r"_s(\d{4})(\d{3})(\d{2})(\d{2})(\d{2})(\d)_")


def _file_start(key: str) -> datetime | None:
    m = START_RE.search(key)
    if not m:
        return None
    year, doy, hh, mm, ss, tenth = (int(g) for g in m.groups())
    return datetime(year, 1, 1, hh, mm, ss, tenth * 100_000, tzinfo=UTC) + timedelta(days=doy - 1)


def parse_flashes(data: bytes, key: str) -> list[RawLightningStrike]:
    """Good-quality flashes inside BBOX from one GLM L2 LCFA netCDF file."""
    import h5py
    import numpy as np

    start = _file_start(key)
    with h5py.File(io.BytesIO(data), "r") as f:
        lat = f["flash_lat"][:].astype(float)
        lon = f["flash_lon"][:].astype(float)
        ids = f["flash_id"][:].astype(np.uint16)
        quality = f["flash_quality_flag"][:].astype(np.int32) if "flash_quality_flag" in f else np.zeros(len(lat))
        offset = f["flash_time_offset_of_first_event"]
        seconds = offset[:].astype(np.uint16) * float(offset.attrs.get("scale_factor", [1.0])[0]) \
            + float(offset.attrs.get("add_offset", [0.0])[0])
    keep = (quality == 0) & (lat >= BBOX[0]) & (lat <= BBOX[1]) & (lon >= BBOX[2]) & (lon <= BBOX[3])
    stamp = key.rsplit("_s", 1)[-1].split("_")[0]
    return [RawLightningStrike(strike_id=f"glm-{stamp}-{int(i)}", latitude=round(float(a), 4),
                               longitude=round(float(o), 4), occurred_at=start + timedelta(seconds=float(s)),
                               source="goes-glm")
            for a, o, i, s in zip(lat[keep], lon[keep], ids[keep], seconds[keep])]


def thin(strikes: list[RawLightningStrike]) -> list[RawLightningStrike]:
    """Latest flash per CELL_DEG grid cell."""
    cells: dict[tuple[int, int], RawLightningStrike] = {}
    for s in strikes:
        cell = (round(s.latitude / CELL_DEG), round(s.longitude / CELL_DEG))
        if cell not in cells or s.occurred_at > cells[cell].occurred_at:
            cells[cell] = s
    return sorted(cells.values(), key=lambda s: s.occurred_at)


class GlmLightningSource:
    name = "goes-glm"

    def __init__(self, bucket: str = "noaa-goes19", timeout: float = 20.0) -> None:
        self._base = f"https://{bucket}.s3.amazonaws.com"
        self._timeout = timeout
        self._last_key: str | None = None

    async def _list(self, client: httpx.AsyncClient, hour: datetime) -> list[str]:
        prefix = f"GLM-L2-LCFA/{hour:%Y}/{hour.timetuple().tm_yday:03d}/{hour:%H}/"
        params = {"list-type": "2", "prefix": prefix}
        if self._last_key and self._last_key.startswith(prefix):
            params["start-after"] = self._last_key
        response = await client.get(self._base + "/", params=params)
        response.raise_for_status()
        return re.findall(r"<Key>([^<]+)</Key>", response.text)

    async def fetch(self) -> list[RawLightningStrike]:
        now = utcnow()
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            keys: list[str] = []
            for hour in (now - timedelta(hours=1), now):
                keys += await self._list(client, hour.replace(minute=0, second=0, microsecond=0))
            if self._last_key:
                keys = [k for k in keys if k > self._last_key]
            else:
                keys = [k for k in keys if (_file_start(k) or now) >= now - FIRST_LOOKBACK]
            keys = sorted(keys)[-MAX_FILES_PER_POLL:]
            blobs = await asyncio.gather(*(client.get(f"{self._base}/{k}") for k in keys), return_exceptions=True)

        strikes: list[RawLightningStrike] = []
        for key, blob in zip(keys, blobs):
            if isinstance(blob, Exception) or blob.status_code != 200:
                log.warning("GLM file %s unavailable: %s", key, blob if isinstance(blob, Exception) else blob.status_code)
                continue
            try:
                strikes += await asyncio.to_thread(parse_flashes, blob.content, key)
            except Exception:
                log.exception("could not parse GLM file %s", key)
        if keys:
            self._last_key = keys[-1]
        return thin(strikes)
