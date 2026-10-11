import json
import math
from pathlib import Path
from typing import List, Dict, Any
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

app = FastAPI()

# Locate and load the telemetry data file safely
BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "q-vercel-latency.json"
if not DATA_FILE.exists():
    DATA_FILE = BASE_DIR.parent / "q-vercel-latency.json"

TELEMETRY_DATA: List[Dict[str, Any]] = []
if DATA_FILE.exists():
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        TELEMETRY_DATA = json.load(f)


def calculate_p95(values: List[float]) -> float:
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    k = (len(sorted_vals) - 1) * 0.95
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return float(sorted_vals[int(k)])
    return float(sorted_vals[f] * (c - k) + sorted_vals[c] * (k - f))


def process_telemetry(payload: dict):
    req_regions = set(payload.get("regions", []))
    threshold = float(payload.get("threshold_ms", 180))

    grouped: Dict[str, List[Dict[str, Any]]] = {r: [] for r in req_regions}
    for item in TELEMETRY_DATA:
        reg = item.get("region")
        if reg in req_regions:
            grouped[reg].append(item)

    results = {}
    for reg in payload.get("regions", []):
        items = grouped.get(reg, [])
        if not items:
            results[reg] = {
                "avg_latency": 0.0,
                "p95_latency": 0.0,
                "avg_uptime": 0.0,
                "breaches": 0,
            }
            continue

        latencies = [
            float(x.get("latency", x.get("latency_ms", 0.0)))
            for x in items
        ]
        uptimes = [
            float(x.get("uptime", x.get("uptime_pct", 0.0)))
            for x in items
        ]

        results[reg] = {
            "avg_latency": round(sum(latencies) / len(latencies), 2),
            "p95_latency": round(calculate_p95(latencies), 2),
            "avg_uptime": round(sum(uptimes) / len(uptimes), 4),
            "breaches": sum(1 for lat in latencies if lat > threshold),
        }

    return results


# Preflight handler (returns 200 for any OPTIONS call)
@app.options("/{full_path:path}")
async def handle_options(full_path: str):
    return Response(status_code=200)


# Health check for browser GET requests
@app.get("/{full_path:path}")
async def handle_get(full_path: str):
    return {"status": "ok", "message": "Endpoint is live."}


# Catch-all POST handler
@app.post("/{full_path:path}")
async def handle_post(request: Request, full_path: str):
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    return process_telemetry(payload)
