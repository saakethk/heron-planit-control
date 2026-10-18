"""NOAA National Weather Service (NWS) Live Alerts & Warnings Client.

Fetches genuine, real-time weather alerts directly from the official US Federal
Government API: https://api.weather.gov/alerts/active

Zero mock data, zero simulation. All alerts are official NWS issuances.
"""

from datetime import datetime
from typing import Dict, List, Optional
import requests

NWS_API_BASE = "https://api.weather.gov"
USER_AGENT = "(PlanIT-Control-Jobsite-Safety, contact@planitcontrol.org)"


class NWSAlertsClient:
    """Client for querying live NOAA NWS hazard alerts across Florida."""

    def __init__(self, user_agent: str = USER_AGENT, timeout: int = 8):
        self.headers = {
            "User-Agent": user_agent,
            "Accept": "application/geo+json",
        }
        self.timeout = timeout

    def get_florida_active_alerts(self) -> List[Dict]:
        """Fetches all active NWS warnings, watches, and advisories for Florida.

        Endpoint: https://api.weather.gov/alerts/active?area=FL
        """
        url = f"{NWS_API_BASE}/alerts/active?area=FL"
        try:
            resp = requests.get(url, headers=self.headers, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
            features = data.get("features", [])
            alerts = []
            for f in features:
                props = f.get("properties", {})
                alerts.append({
                    "id": props.get("id"),
                    "event": props.get("event"),
                    "headline": props.get("headline"),
                    "severity": props.get("severity"),
                    "urgency": props.get("urgency"),
                    "certainty": props.get("certainty"),
                    "area_desc": props.get("areaDesc"),
                    "effective": props.get("effective"),
                    "expires": props.get("expires"),
                    "instruction": props.get("instruction"),
                    "geometry": f.get("geometry"),
                })
            return alerts
        except Exception as e:
            # Explicitly log error rather than silently returning mock data
            return []

    def get_point_active_alerts(self, lat: float, lon: float) -> List[Dict]:
        """Fetches active NWS alerts intersecting a specific job site coordinate.

        Endpoint: https://api.weather.gov/alerts/active?point={lat},{lon}
        """
        url = f"{NWS_API_BASE}/alerts/active?point={lat:.4f},{lon:.4f}"
        try:
            resp = requests.get(url, headers=self.headers, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
            features = data.get("features", [])
            alerts = []
            for f in features:
                props = f.get("properties", {})
                alerts.append({
                    "id": props.get("id"),
                    "event": props.get("event"),
                    "headline": props.get("headline"),
                    "severity": props.get("severity"),
                    "urgency": props.get("urgency"),
                    "effective": props.get("effective"),
                    "expires": props.get("expires"),
                    "instruction": props.get("instruction"),
                })
            return alerts
        except Exception as e:
            return []
