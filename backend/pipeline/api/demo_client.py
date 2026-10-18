"""FastAPI REST & WebSocket Verification Client.

Demonstrates:
1. Normal REST Requests: /health, /api/v1/sites, /api/v1/sites/{id}
2. Submitting Crew Hazard Report: POST /api/v1/reports/crew
3. Continuous Retraining Trigger: POST /api/v1/model/retrain
4. WebSocket Stream Subscription: ws://127.0.0.1:8000/ws/hazards

Run directly in terminal (requires FastAPI server running):
    python -m pipeline.api.demo_client
"""

import asyncio
import json
import requests

API_BASE = "http://127.0.0.1:8000"
WS_URL = "ws://127.0.0.1:8000/ws/hazards"


def test_rest_endpoints():
    print("=" * 80)
    print("1. TESTING FASTAPI REST ENDPOINTS")
    print("=" * 80)

    # 1. Healthcheck
    try:
        r = requests.get(f"{API_BASE}/health", timeout=3)
        print(f"[REST] GET /health -> Status {r.status_code}: {r.json()}")
    except Exception as e:
        print(f"[REST] Healthcheck note: {e}")
        return

    # 2. List Monitored Sites
    try:
        r = requests.get(f"{API_BASE}/api/v1/sites?limit=3", timeout=3)
        print(f"\n[REST] GET /api/v1/sites?limit=3 -> {len(r.json())} sites returned:")
        for s in r.json():
            print(f"  * #{s['plant_id']}: {s['plant_name']} ({s['county']} Co) - FEMA Zone: {s['fema_flood_zone']}")
    except Exception as e:
        print(f"[REST] Sites query error: {e}")

    # 3. Specific Site Risk Evaluation (Turkey Point #621)
    try:
        r = requests.get(f"{API_BASE}/api/v1/sites/621", timeout=5)
        d = r.json()
        print(f"\n[REST] GET /api/v1/sites/621 (Turkey Point):")
        print(f"  * Hazard Index: {d.get('hazard_index')}/10 | Primary Threat: {d.get('primary_hazard')}")
        print(f"  * Status: {d.get('operational_status')} - {d.get('alert_message')}")
        print(f"  * Probabilities: {d.get('probabilities')}")
    except Exception as e:
        print(f"[REST] Site detail error: {e}")

    # 4. Trigger Continuous Retraining
    try:
        print("\n[REST] POST /api/v1/model/retrain (Retraining on Historical + Appended Stream Data)...")
        r = requests.post(f"{API_BASE}/api/v1/model/retrain", timeout=15)
        print(f"  * Retraining Response: {r.json()}")
    except Exception as e:
        print(f"[REST] Retraining error: {e}")


async def test_websocket_stream():
    print("\n" + "=" * 80)
    print("2. TESTING WEBSOCKET REAL-TIME STREAM (/ws/hazards)")
    print("=" * 80)
    try:
        import websockets
    except ImportError:
        print("Note: 'websockets' library not installed in this environment. Run 'pip install websockets'.")
        return

    try:
        async with websockets.connect(WS_URL) as ws:
            print(f"[WS] Connected to {WS_URL}!")
            # Receive initial handshake
            greeting = await ws.recv()
            print(f"[WS] Handshake received: {greeting}")

            print("[WS] Listening for live broadcast events (listening for 5 seconds)...")
            try:
                for _ in range(3):
                    msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
                    evt = json.loads(msg)
                    print(f"[WS EVENT] #{evt.get('event_id', '--')}: {evt.get('plant_name')} | Hazard: {evt.get('hazard_index')}/10 | Threat: {evt.get('primary_hazard')}")
            except asyncio.TimeoutError:
                print("[WS] Stream listening timeout completed.")
    except Exception as e:
        print(f"[WS] Connection note: {e}")


if __name__ == "__main__":
    test_rest_endpoints()
    try:
        asyncio.run(test_websocket_stream())
    except KeyboardInterrupt:
        pass
