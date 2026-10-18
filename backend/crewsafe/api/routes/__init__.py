from . import alerts, auth, briefings, decisions, devices, health, lightning, reports, simulate, sites

ROUTERS = [health.router, auth.router, sites.router, lightning.router, alerts.router, briefings.router,
           reports.router, devices.router, decisions.router, simulate.router]
