"""The JSON must decode with the app's Swift models (`Models.swift`):
snake_case keys, ISO-8601 dates WITHOUT fractional seconds, known enum values."""

from __future__ import annotations

import base64
import re

from conftest import make_settings, wait_for
from fastapi.testclient import TestClient

from crewsafe.api.main import create_app

ISO = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
HAZARDS = {"lightning", "flood", "heat", "wildfire", "wildlife", "soil_saturation", "other"}
SEVERITIES = {"advisory", "warning", "stop_work"}
API = "/api/v1"


def test_health(client):
    body = client.get(f"{API}/health").json()
    assert body["status"] == "ok" and body["sites"] == 346 and body["scored_sites"] == 346
    assert body["data_sources"] == {"weather": "dummy", "alerts": "dummy", "lightning": "dummy"}


def test_sites_match_app_model(client):
    response = client.get(f"{API}/sites")
    assert response.status_code == 200 and "etag" in response.headers
    sites = response.json()
    assert len(sites) == 346
    for site in sites:
        assert {"id", "name", "county", "latitude", "longitude", "capacity_mw", "hazard_index", "factors",
                "updated_at"} <= site.keys()
        assert isinstance(site["id"], int) and 0 <= site["hazard_index"] <= 10
        assert ISO.match(site["updated_at"])
        assert all(f["type"] in HAZARDS and 0 <= f["score"] <= 10 for f in site["factors"])
        assert {"temperature_f", "heat_index_f", "wind_mph", "rain24h_in", "soil_moisture_pct"} <= site["conditions"].keys()
        assert all(ISO.match(p["time"]) for p in site["history"])

    etag = response.headers["etag"]
    assert client.get(f"{API}/sites", headers={"If-None-Match": etag}).status_code == 304

    summary = client.get(f"{API}/sites?view=summary").json()
    assert "history" not in summary[0] and "conditions" not in summary[0]


def test_site_detail_nearby_and_briefing(client):
    site = client.get(f"{API}/sites/664").json()
    assert site["name"] == "John R Kelly" and site["history"]

    nearby = client.get(f"{API}/sites/nearby", params={"lat": 29.6516, "lon": -82.3248, "limit": 25})
    assert nearby.headers["x-total-count"] == "346"
    rows = nearby.json()
    assert len(rows) == 25 and rows[0]["id"] == 664
    assert [r["distance_miles"] for r in rows] == sorted(r["distance_miles"] for r in rows)

    briefing = client.get(f"{API}/sites/664/briefing").json()
    assert briefing["site_id"] == 664 and briefing["events"] and ISO.match(briefing["updated_at"])
    assert briefing["events"][0]["type"] == "lightning"  # the active hold leads

    detail = client.get(f"{API}/sites/664/hazard").json()
    assert detail["model_version"] == "dummy-0.1" and "lightning" in detail["drivers"]

    missing = client.get(f"{API}/sites/1")
    assert missing.status_code == 404 and missing.json()["error"] == "not_found"


def test_lightning_holds_from_pipeline(client):
    holds = {h["site_id"]: h for h in client.get(f"{API}/lightning/holds").json()}
    assert {664, 617} <= holds.keys()
    hold = holds[664]
    assert hold["all_clear_interval"] == 1800 and hold["strike_count"] >= 2 and hold["last_direction"] == "SW"
    assert ISO.match(hold["started_at"]) and ISO.match(hold["last_strike_at"])


def test_alerts_filter_and_ack(client):
    alerts = client.get(f"{API}/alerts", params={"site_ids": "664,627"}).json()
    assert alerts and {a["site_id"] for a in alerts} <= {664, 627}
    assert all(a["severity"] in SEVERITIES and a["type"] in HAZARDS and ISO.match(a["issued_at"]) for a in alerts)
    assert any(a["severity"] == "stop_work" and a["site_id"] == 664 for a in alerts)

    target = next(a for a in alerts if not a["acknowledged"])
    assert client.post(f"{API}/alerts/{target['id']}/ack", json={}).status_code == 204
    again = {a["id"]: a for a in client.get(f"{API}/alerts", params={"site_ids": "664,627"}).json()}
    assert again[target["id"]]["acknowledged"] is True
    assert client.post(f"{API}/alerts/nope/ack", json={}).json() == {"error": "not_found", "detail": "alert nope not found"}


def test_report_flows_through_pipeline(client):
    jpeg = base64.b64encode(b"\xff\xd8\xff\xe0" + b"0" * 64).decode()
    body = {"id": "test-report-1", "site_id": 627, "type": "flood", "notes": "Water over the access road.",
            "latitude": 27.758, "longitude": -82.635, "created_at": "2026-10-17T15:00:00Z", "photo_jpeg": jpeg}
    response = client.post(f"{API}/reports", json=body)
    assert response.status_code == 201
    assert client.post(f"{API}/reports", json=body).status_code == 200  # retry is idempotent

    reports = {r["id"]: r for r in client.get(f"{API}/reports").json()}
    assert reports["test-report-1"]["photo_url"].endswith("/api/v1/photos/test-report-1.jpg")
    assert client.get(reports["test-report-1"]["photo_url"]).content.startswith(b"\xff\xd8")

    alert = wait_for(lambda: next((a for a in client.get(f"{API}/alerts", params={"site_ids": "627"}).json()
                                   if a["id"] == "report-test-report-1"), None))
    assert alert["source"] == "Crew report"

    bad = client.post(f"{API}/reports", json={**body, "id": "x", "photo_jpeg": "not base64!"})
    assert bad.status_code == 422 and bad.json()["error"] == "validation_error"


def test_devices_subscription_and_next_day(client):
    assert client.post(f"{API}/devices", json={"apns_token": "abc123", "platform": "ios"}).status_code == 201
    subscription = {"location": {"name": "Gainesville, FL", "latitude": 29.6516, "longitude": -82.3248},
                    "home_site_id": 664, "site_ids": [664, 56518, 999999]}
    assert client.put(f"{API}/me/subscription", json=subscription).status_code == 204

    briefing = client.get(f"{API}/briefings/next-day").json()
    assert ISO.match(briefing["for_date"]) and briefing["summary"]
    assert {i["site_id"] for i in briefing["items"]} == {664, 56518}


def test_auth_required_mode(tmp_path):
    with TestClient(create_app(make_settings(tmp_path, auth_required=True))) as c:
        assert c.get(f"{API}/sites").status_code == 401
        assert c.get(f"{API}/health").status_code == 200
        assert c.post(f"{API}/auth/login", json={"username": "crew", "password": "wrong"}).status_code == 401

        crew = c.post(f"{API}/auth/login", json={"username": "crew", "password": "demo"}).json()
        headers = {"Authorization": f"Bearer {crew['access_token']}"}
        assert c.get(f"{API}/sites?view=summary", headers=headers).status_code == 200
        assert c.get(f"{API}/decision-log", headers=headers).status_code == 403

        boss = c.post(f"{API}/auth/login", json={"username": "supervisor", "password": "demo"}).json()
        log = c.get(f"{API}/decision-log", headers={"Authorization": f"Bearer {boss['access_token']}"}).json()
        assert any(d["decision"] == "issued" for d in log)
