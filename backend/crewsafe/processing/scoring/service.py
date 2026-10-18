"""Scoring service.

Rescores a site whenever its conditions change, a crew report arrives, or
lightning strikes nearby:

    features (shared module) -> model.predict -> rule-based hazards (heat, wildlife)
    -> crew-report adjustments -> compound index -> factors + drivers -> hazard.scores
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from ...contracts.api import HazardDriver
from ...contracts.common import HazardType, utcnow
from ...contracts.events import CleanConditions, CrewReportEvent, HazardScore, SiteStrike
from ...messaging import topics
from ...messaging.bus import MessageBus
from ...storage.repository import Repository
from ..features import build_features, build_forecast_features
from . import rules
from .model import HazardModel

log = logging.getLogger(__name__)

STRIKE_WINDOW = timedelta(minutes=30)
# Strikes farther than this don't change the lightning score enough to rescore.
RESCORE_STRIKE_MILES = 20.0
# Scores older than this when computed are backfill: charted, never alerted on.
LIVE_WINDOW = timedelta(minutes=20)


class ScoringService:
    def __init__(self, bus: MessageBus, repo: Repository, model: HazardModel) -> None:
        self.bus, self.repo, self.model = bus, repo, model
        self.recent_strikes: dict[int, list[SiteStrike]] = defaultdict(list)

    def register(self) -> None:
        self.bus.subscribe([topics.CLEAN_CONDITIONS, topics.CREW_REPORTS, topics.LIGHTNING_SITE_STRIKES],
                           "scoring", self.handle)

    async def handle(self, topic: str, key: str | None, value: dict[str, Any]) -> None:
        if topic == topics.CLEAN_CONDITIONS:
            conditions = CleanConditions(**value)
            await self.score(conditions, conditions.obs_time)
        elif topic == topics.CREW_REPORTS:
            report = CrewReportEvent(**value)
            if report.site_id is not None:
                await self.rescore(report.site_id)
        elif topic == topics.LIGHTNING_SITE_STRIKES:
            strike = SiteStrike(**value)
            cutoff = utcnow() - STRIKE_WINDOW
            earlier = [s for s in self.recent_strikes[strike.site_id] if s.occurred_at >= cutoff]
            self.recent_strikes[strike.site_id] = earlier + [strike]
            # A busy storm sends hundreds of flashes; rescore only when one changes the picture.
            closest = min((s.distance_miles for s in earlier), default=None)
            if strike.distance_miles <= RESCORE_STRIKE_MILES and (closest is None or strike.distance_miles < closest):
                await self.rescore(strike.site_id)

    async def rescore(self, site_id: int) -> HazardScore | None:
        conditions = await self.repo.latest_conditions(site_id)
        if conditions is None:
            return None
        return await self.score(conditions, max(utcnow(), conditions.obs_time))

    async def score(self, c: CleanConditions, at: datetime) -> HazardScore | None:
        site = await self.repo.get_site(c.site_id)
        if site is None:
            log.warning("conditions for unknown site %s", c.site_id)
            return None

        strikes = [s for s in self.recent_strikes.get(c.site_id, []) if at - STRIKE_WINDOW <= s.occurred_at <= at]
        nearest = min(strikes, key=lambda s: s.distance_miles) if strikes else None
        features = build_features(c, site, nearest.distance_miles if nearest else None, len(strikes))

        predictions = self.model.predict(features)
        scores = {hazard: p.score for hazard, p in predictions.items()}
        drivers = {hazard.value: p.drivers for hazard, p in predictions.items()}

        if HazardType.heat not in scores:
            scores[HazardType.heat] = rules.heat_score(c.heat_index_f)
            drivers[HazardType.heat.value] = [HazardDriver(feature="heat_index_f", contribution=scores[HazardType.heat],
                                                           value=c.heat_index_f)]
        reports = [r for r in await self.repo.list_reports([c.site_id], at - timedelta(hours=24), 50)
                   if r.created_at <= at]
        wildlife, sighting = rules.wildlife_score(site, reports, at)
        if wildlife:
            scores[HazardType.wildlife] = wildlife
        adjustments = rules.report_adjustments(scores, reports, at)

        details = {
            hazard: rules.factor_detail(hazard, features, predictions[hazard].drivers if hazard in predictions else [],
                                        nearest.direction if nearest else None, sighting, site.flood_zone)
            for hazard in scores
        }

        forecast_index = forecast_text = None
        if c.forecast:
            tomorrow = {h: p.score for h, p in
                        self.model.predict(build_forecast_features(c.forecast, c, site)).items()}
            tomorrow.setdefault(HazardType.heat, rules.heat_score(c.forecast.max_heat_index_f))
            forecast_index = rules.compound_index(tomorrow)
            forecast_text = rules.forecast_headline(c.forecast, tomorrow)

        score = HazardScore(
            site_id=c.site_id,
            computed_at=at,
            hazard_index=rules.compound_index(scores),
            factors=rules.build_factors(scores, details),
            drivers=drivers,
            report_adjustments=adjustments,
            model_version=self.model.version,
            data_stale=c.data_stale,
            forecast_index=forecast_index,
            forecast_headline=forecast_text,
            backfill=utcnow() - at > LIVE_WINDOW,
        )
        await self.repo.save_score(score)
        await self.bus.publish(topics.HAZARD_SCORES, score, key=c.site_id)
        return score
