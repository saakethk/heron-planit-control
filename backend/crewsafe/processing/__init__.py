"""Layer 2: processing services connected by the bus.

transformer: raw.weather / raw.nws.alerts -> clean.conditions / clean.nws.alerts
lightning:   raw.lightning -> lightning.site_strikes / lightning.holds
scoring:     clean.conditions + crew.reports + lightning.site_strikes -> hazard.scores
alerts:      hazard.scores + clean.nws.alerts + lightning.holds + crew.reports -> alerts.issued (+ push)
"""
