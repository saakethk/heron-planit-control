from __future__ import annotations

from ...config import Settings
from ...storage.models import SiteRecord
from .base import AlertSource, LightningSource, WeatherSource


def create_sources(settings: Settings, sites: list[SiteRecord]) -> tuple[WeatherSource, AlertSource, LightningSource | None]:
    """Pick real or dummy sources from settings. Dummy sources share one simulated
    world so weather, NWS alerts, and lightning agree with each other."""
    world = None

    def dummy_world():
        nonlocal world
        if world is None:
            from .dummy import DummyWorld
            world = DummyWorld(sites)
        return world

    if settings.weather_source == "open-meteo":
        from .open_meteo import OpenMeteoSource
        weather: WeatherSource = OpenMeteoSource()
    else:
        from .dummy import DummyWeatherSource
        weather = DummyWeatherSource(dummy_world())

    if settings.alert_source == "nws":
        from .nws import NwsAlertSource
        alerts: AlertSource = NwsAlertSource(settings.nws_user_agent)
    else:
        from .dummy import DummyAlertSource
        alerts = DummyAlertSource(dummy_world())

    lightning: LightningSource | None = None
    if settings.lightning_source == "dummy":
        from .dummy import DummyLightningSource
        lightning = DummyLightningSource(dummy_world())
    return weather, alerts, lightning
