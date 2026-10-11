import json
import math
from pathlib import Path
from typing import List, Dict, Any
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# Standard FastAPI CORS configuration (handles preflight OPTIONS automatically)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Safe loader for telemetry data
DATA_PATH = Path(__file__).resolve().parent / "q-vercel-latency.json"
TELEMETRY_DATA: List[Dict[str, Any]] = []

if DATA_PATH.exists():
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        TELEMETRY_DATA = json.load(f)


def calculate_p95(vals: List[float]) -> float:
    if not vals:
        return 0.0
    s = sorted(vals)
    k = (len(s) - 1) * 0.95
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return float(s[int(k)])
    return float(s[f] * (c - k) + s[c] * (k - f))


def compute_metrics(payload: dict):
    regions = payload.get("regions", [])
    threshold = float(payload.get("threshold_ms", 180))

    req_set = {str(r).lower() for r in regions}
    grouped: Dict[str, List[Dict[str, Any]]] = {r: [] for r in req_set}

    for item in TELEMETRY_DATA:
        reg = str(item.get("region", "")).lower()
        if reg in grouped:
            grouped[reg].append(item)

    results = {}
    for r in regions:
        key = str(r).lower()
        items = grouped.get(key, [])
        if not items:
            results[r] = {
                "avg_latency": 0.0,
                "p95_latency": 0.0,
                "avg_uptime": 0.0,
                "breaches": 0,
            }
            continue

        lats = [float(x.get("latency", x.get("latency_ms", 0.0))) for x in items]
        upts = [float(x.get("uptime", x.get("uptime_pct", 0.0))) for x in items]

        results[r] = {
            "avg_latency": round(sum(lats) / len(lats), 2),
            "p95_latency": round(calculate_p95(lats), 2),
            "avg_uptime": round(sum(upts) / len(upts), 4),
            "breaches": sum(1 for lat in lats if lat > threshold),
        }

    return results


# Health check
@app.get("/")
@app.get("/latency")
@app.get("/api/latency")
async def health():
    return {"status": "ok"}


# Handles POST across all path variants
@app.post("/")
@app.post("/latency")
@app.post("/api/latency")
async def handle_metrics(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    return compute_metrics(body)
