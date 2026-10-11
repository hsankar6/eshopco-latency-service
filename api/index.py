import json
from pathlib import Path
from typing import List, Dict, Any
import numpy as np
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Locate and load the telemetry bundle
DATA_PATHS = [
    Path(__file__).resolve().parent / "q-vercel-latency.json",
    Path.cwd() / "api" / "q-vercel-latency.json",
    Path.cwd() / "q-vercel-latency.json",
]
TELEMETRY_DATA: List[Dict[str, Any]] = []
for p in DATA_PATHS:
    if p.exists():
        with open(p, "r", encoding="utf-8") as f:
            TELEMETRY_DATA = json.load(f)
        break


def compute_metrics(payload: dict):
    req_regions = payload.get("regions", [])
    threshold = float(payload.get("threshold_ms", 180))

    grouped: Dict[str, List[Dict[str, Any]]] = {
        str(r).lower(): [] for r in req_regions
    }
    for item in TELEMETRY_DATA:
        reg = str(item.get("region", "")).lower()
        if reg in grouped:
            grouped[reg].append(item)

    results = {}
    for r in req_regions:
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
            "avg_latency": round(float(np.mean(lats)), 2),
            "p95_latency": round(float(np.percentile(lats, 95)), 2),
            "avg_uptime": round(float(np.mean(upts)), 4),
            "breaches": int(sum(1 for lat in lats if lat > threshold)),
        }

    return results


# Universal catch-all for both "/" and any sub-path (prevents 404 entirely)
@app.api_route("/", methods=["GET", "POST", "OPTIONS"])
@app.api_route("/{full_path:path}", methods=["GET", "POST", "OPTIONS"])
async def universal_handler(request: Request, full_path: str = ""):
    # 1. Handle preflight CORS requests
    if request.method == "OPTIONS":
        return Response(
            status_code=200,
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                "Access-Control-Allow-Headers": "*",
            },
        )

    # 2. Handle GET requests (health-check)
    if request.method == "GET":
        return JSONResponse(
            status_code=200,
            content={"status": "ok", "message": "Endpoint is live."},
            headers={"Access-Control-Allow-Origin": "*"},
        )

    # 3. Handle POST requests (metric calculations)
    try:
        body = await request.json()
    except Exception:
        body = {}

    result = compute_metrics(body)
    return JSONResponse(
        status_code=200,
        content=result,
        headers={"Access-Control-Allow-Origin": "*"},
    )
