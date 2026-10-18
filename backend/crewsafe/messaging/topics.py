"""Kafka topic names. Messages are keyed by `site_id`, delivered at-least-once,
and every consumer write is idempotent."""

# Layer 1 -> Layer 2
RAW_WEATHER = "raw.weather"
RAW_NWS_ALERTS = "raw.nws.alerts"
RAW_LIGHTNING = "raw.lightning"

# Within Layer 2
CLEAN_CONDITIONS = "clean.conditions"
CLEAN_NWS_ALERTS = "clean.nws.alerts"
HAZARD_SCORES = "hazard.scores"
CREW_REPORTS = "crew.reports"
LIGHTNING_SITE_STRIKES = "lightning.site_strikes"
LIGHTNING_HOLDS = "lightning.holds"
ALERTS_ISSUED = "alerts.issued"

DEAD_LETTER = "dead-letter"

ALL = [
    RAW_WEATHER, RAW_NWS_ALERTS, RAW_LIGHTNING, CLEAN_CONDITIONS, CLEAN_NWS_ALERTS,
    HAZARD_SCORES, CREW_REPORTS, LIGHTNING_SITE_STRIKES, LIGHTNING_HOLDS, ALERTS_ISSUED, DEAD_LETTER,
]
