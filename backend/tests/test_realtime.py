from __future__ import annotations

API = "/api/v1"


def receive_until(ws, wanted: set[str], limit: int = 50) -> dict[str, dict]:
    seen: dict[str, dict] = {}
    for _ in range(limit):
        message = ws.receive_json()
        seen.setdefault(message["type"], message)
        if wanted <= seen.keys():
            return seen
    raise AssertionError(f"missing {wanted - seen.keys()}, saw {set(seen)}")


def test_subscribe_then_receive_site_events(client):
    with client.websocket_connect(f"{API}/ws/updates") as ws:
        ws.send_json({"type": "subscribe", "payload": {"site_ids": [664], "include_severe_statewide": False}})
        subscribed = ws.receive_json()
        assert subscribed["type"] == "subscribed" and subscribed["payload"]["site_ids"] == [664]

        client.post(f"{API}/reports", json={"id": "ws-report", "site_id": 664, "type": "wildlife",
                                            "notes": "Snake by the gate.", "created_at": "2026-10-17T15:00:00Z"})
        seen = receive_until(ws, {"report_created", "alert", "hazard_index_updated"})

        alert = seen["alert"]["payload"]
        assert alert["site_id"] == 664 and alert["source"] == "Crew report"
        update = seen["hazard_index_updated"]["payload"]
        assert update["site_id"] == 664 and 0 <= update["hazard_index"] <= 10
        seqs = [m["seq"] for m in seen.values()]
        assert all(s > subscribed["seq"] for s in seqs)


def test_resume_replays_missed_events(client):
    with client.websocket_connect(f"{API}/ws/updates") as ws:
        ws.send_json({"type": "subscribe", "payload": {"site_ids": [627]}})
        last_seq = ws.receive_json()["seq"]

    client.post(f"{API}/reports", json={"id": "missed", "site_id": 627, "type": "flood", "notes": "Rising water.",
                                        "created_at": "2026-10-17T15:00:00Z"})
    with client.websocket_connect(f"{API}/ws/updates") as ws:
        # Give the pipeline a moment to process the report before resuming.
        ws.send_json({"type": "ping"})
        assert ws.receive_json()["type"] == "pong"
        ws.send_json({"type": "subscribe", "payload": {"site_ids": [627], "last_seq": last_seq}})
        seen = receive_until(ws, {"report_created", "alert", "subscribed"})
        assert seen["alert"]["payload"]["id"] == "report-missed"


def test_unknown_message_type(client):
    with client.websocket_connect(f"{API}/ws/updates") as ws:
        ws.send_json({"type": "dance"})
        assert ws.receive_json()["type"] == "error"
