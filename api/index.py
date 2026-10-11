import json
import math
from pathlib import Path
from typing import List, Dict, Any
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

app = FastAPI()


# 1. Guaranteed CORS Middleware
@app.middleware("http")
async def cors_middleware(request: Request, call_next):
    # Respond immediately to preflight OPTIONS requests
    if request.method == "OPTIONS":
        res = Response(status_code=200)
        res.headers["Access-Control-Allow-Origin"] = "*"
        res.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        res.headers["Access-Control-Allow-Headers"] = "*"
        return res

    try:
        response = await call_next(request)
    except Exception as exc:
        response = JSONResponse(status_code=500, content={"error": str(exc)})

    # Unconditionally attach the required CORS header
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "*"
    return response


# 2. Locate and load telemetry data
def load_data():
    search_paths = [
        Path(__file__).resolve().parent / "q-vercel-latency.json",
        Path(__file__).resolve().parent.parent / "q-vercel-latency.json",
        Path.cwd() / "q-vercel-latency.json",
        Path.cwd() / "api" / "q-vercel-latency.json",
    ]
    for p in search_paths:
        if p.exists():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
    return []


TELEMETRY_DATA: List[Dict[str, Any]] = load_data()


def get_p95(values: List[float]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * 0.95
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return float(s[int(k)])
    return float(s[f] * (c - k) + s[c] * (k - f))


def process_request(payload: dict):
    req_regions = [str(r).lower() for r in payload.get("regions", [])]
    threshold = float(payload.get("threshold_ms", 180))

    grouped: Dict[str, List[Dict[str, Any]]] = {r: [] for r in req_regions}
    for item in TELEMETRY_DATA:
        reg = str(item.get("region", "")).lower()
        if reg in grouped:
            grouped[reg].append(item)

    results = {}
    for reg in req_regions:
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
            "p95_latency": round(get_p95(latencies), 2),
            "avg_uptime": round(sum(uptimes) / len(uptimes), 4),
            "breaches": sum(1 for lat in latencies if lat > threshold),
        }

    return results


# 3. Route Handlers
@app.options("/{full_path:path}")
async def options_route(full_path: str):
    res = Response(status_code=200)
    res.headers["Access-Control-Allow-Origin"] = "*"
    return res


@app.get("/{full_path:path}")
async def get_route(full_path: str):
    return {"status": "ok", "message": "Endpoint is live."}


@app.post("/{full_path:path}")
async def post_route(request: Request, full_path: str):
    try:
        body = await request.json()
    except Exception:
        body = {}
    return process_request(body)
