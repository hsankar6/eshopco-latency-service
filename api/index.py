import json
from pathlib import Path
from typing import List, Dict, Any
import numpy as np
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

app = FastAPI()

# Enable CORS middleware with wildcard origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Custom middleware to guarantee the CORS header is on every response
@app.middleware("http")
async def add_cors_headers(request: Request, call_next):
    if request.method == "OPTIONS":
        response = Response(status_code=200)
    else:
        response = await call_next(request)
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "*"
    return response


# Load telemetry data
DATA_FILE = Path(__file__).parent / "q-vercel-latency.json"
with open(DATA_FILE, "r", encoding="utf-8") as f:
    TELEMETRY_DATA: List[Dict[str, Any]] = json.load(f)


def calculate(payload: dict):
    req_regions = set(payload.get("regions", []))
    threshold = float(payload.get("threshold_ms", 180))

    grouped: Dict[str, List[Dict[str, Any]]] = {r: [] for r in req_regions}
    for item in TELEMETRY_DATA:
        reg = item.get("region")
        if reg in req_regions:
            grouped[reg].append(item)

    regions_output = []
    for reg in payload.get("regions", []):
        items = grouped.get(reg, [])
        if not items:
            regions_output.append({
                "region": reg,
                "avg_latency": 0.0,
                "p95_latency": 0.0,
                "avg_uptime": 0.0,
                "breaches": 0,
            })
            continue

        latencies = [
            float(x.get("latency", x.get("latency_ms", 0.0)))
            for x in items
        ]
        uptimes = [
            float(x.get("uptime", x.get("uptime_pct", 0.0)))
            for x in items
        ]

        regions_output.append({
            "region": reg,
            "avg_latency": float(np.mean(latencies)),
            "p95_latency": float(np.percentile(latencies, 95)),
            "avg_uptime": float(np.mean(uptimes)),
            "breaches": int(sum(1 for lat in latencies if lat > threshold)),
        })

    return {"regions": regions_output}


# Respond to preflight OPTIONS requests
@app.options("/{full_path:path}")
async def options_handler(full_path: str):
    return Response(
        status_code=200,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "*",
        },
    )


# Health check for GET
@app.get("/{full_path:path}")
async def catch_all_get(full_path: str):
    return JSONResponse(
        content={"status": "ok", "path_received": full_path},
        headers={"Access-Control-Allow-Origin": "*"},
    )


# POST handler for metric calculation
@app.post("/{full_path:path}")
async def catch_all_post(request: Request, full_path: str):
    payload = await request.json()
    result = calculate(payload)
    return JSONResponse(
        content=result,
        headers={"Access-Control-Allow-Origin": "*"},
    )
