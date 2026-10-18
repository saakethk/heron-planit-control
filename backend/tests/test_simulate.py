"""Scripted events go through the same pipeline as live weather and lightning."""

from __future__ import annotations

from conftest import wait_for
from crewsafe.processing.simulate import parse_prompt
from crewsafe.storage.models import SiteRecord

API = "/api/v1"
SITES = [
    SiteRecord(id=664, name="John R Kelly", county="Alachua", latitude=29.65, longitude=-82.32, capacity_mw=1),
    SiteRecord(id=621, name="Turkey Point", county="Miami-Dade", latitude=25.43, longitude=-80.33, capacity_mw=1),
    SiteRecord(id=617, name="Port Everglades", county="Broward", latitude=26.09, longitude=-80.12, capacity_mw=1),
]


def test_parse_prompt_kinds_and_sites():
    assert parse_prompt("lightning", SITES).kind == "lightning" and parse_prompt("lightning", SITES).site_id == 664
    assert parse_prompt("flood at Turkey Point", SITES).site_id == 621
    assert parse_prompt("lightning 6 miles from 617", SITES).miles == 6.0
    assert parse_prompt("next-day briefing").kind == "briefing"
    assert parse_prompt("clear holds").kind == "clear" and parse_prompt("clear holds").site_id is None
    try:
        parse_prompt("dance party")
    except ValueError as exc:
        assert "could not tell" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_simulate_rejects_bad_kind(client):
    response = client.post(f"{API}/simulate", json={"kind": "tornado", "site_id": 664})
    assert response.status_code == 422


def test_simulate_heat_changes_score_and_alerts(client):
    before = client.get(f"{API}/sites/664").json()
    had_heat = any(a["type"] == "heat" and a["source"] == "Hazard model"
                   for a in client.get(f"{API}/alerts", params={"site_ids": "664"}).json())
    body = client.post(f"{API}/simulate", json={"kind": "heat", "site_id": 664}).json()
    assert body["kind"] == "heat" and body["heat_index_f"] == 113
    after = client.get(f"{API}/sites/664").json()
    assert after["conditions"]["heat_index_f"] == 113
    assert after["hazard_index"] >= before["hazard_index"]
    assert any(f["type"] == "heat" and f["score"] >= 7.5 for f in after["factors"])
    if not had_heat:
        alert = wait_for(lambda: next((a for a in client.get(f"{API}/alerts", params={"site_ids": "664"}).json()
                                       if a["type"] == "heat" and a["source"] == "Hazard model"), None))
        assert alert["severity"] == "warning"


def test_simulate_lightning_starts_hold(client):
    body = client.post(f"{API}/simulate", json={"kind": "lightning", "site_id": 56518, "miles": 4}).json()
    assert body["kind"] == "lightning" and body["active_hold"] is True
    hold = wait_for(lambda: next((h for h in client.get(f"{API}/lightning/holds").json()
                                  if h["site_id"] == 56518), None))
    assert hold["last_distance_miles"] == 4.0 and hold["all_clear_interval"] == 60
    alert = wait_for(lambda: next((a for a in client.get(f"{API}/alerts", params={"site_ids": "56518"}).json()
                                   if a["severity"] == "stop_work" and a["type"] == "lightning"), None))
    assert "lightning" in alert["title"].lower()

    cleared = client.post(f"{API}/simulate", json={"kind": "clear", "site_id": 56518}).json()
    assert cleared["kind"] == "clear"
    assert all(h["site_id"] != 56518 for h in client.get(f"{API}/lightning/holds").json())


def test_simulate_flood_issues_nws_alert(client):
    before = client.get(f"{API}/sites/664").json()["conditions"]["rain24h_in"]
    body = client.post(f"{API}/simulate", json={"kind": "flood", "site_id": 664}).json()
    assert body["rain24h_in"] == 3.5
    after = client.get(f"{API}/sites/664").json()
    assert after["conditions"]["rain24h_in"] == 3.5
    assert after["conditions"]["rain24h_in"] >= before
    alert = wait_for(lambda: next((a for a in client.get(f"{API}/alerts", params={"site_ids": "664"}).json()
                                   if a["title"] == "Flood Warning" and a["source"] == "NWS"), None))
    assert alert["severity"] == "warning"


def test_simulate_prompt_and_briefing(client):
    body = client.post(f"{API}/simulate", json={"prompt": "lightning 5 miles from 56518"}).json()
    assert body["kind"] == "lightning" and body["active_hold"] is True
    briefing = client.post(f"{API}/simulate", json={"prompt": "next-day briefing"}).json()
    assert briefing["kind"] == "briefing" and briefing["detail"]
    alert = wait_for(lambda: next(
        (a for a in client.get(f"{API}/alerts", params={"site_ids": str(briefing["site_id"])}).json()
         if a["title"] == "Tomorrow's safety briefing"), None))
    assert alert["source"] == "Briefing" and alert["message"] == briefing["detail"]
