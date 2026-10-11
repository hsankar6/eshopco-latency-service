import json
from pathlib import Path
from typing import List, Dict, Any
import numpy as np
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

app = FastAPI()

# Enable CORS for all origins, headers, and methods
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load telemetry bundle
DATA_FILE = Path(__file__).parent / "q-vercel-latency.json"
with open(DATA_FILE, "r", encoding="utf-8") as f:
    TELEMETRY_DATA: List[Dict[str, Any]] = json.load(f)


def compute_metrics(payload: dict):
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


# Browser health check (GET) across all routes
@app.get("/")
@app.get("/latency")
@app.get("/api/latency")
async def health_check():
    return {"status": "ok", "message": "Service is live and ready for POST requests."}


# Handle POST requests across all path variations
@app.post("/")
@app.post("/latency")
@app.post("/api/latency")
async def handle_post(request: Request):
    payload = await request.json()
    return compute_metrics(payload)
