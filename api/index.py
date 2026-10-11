import json
import math
from pathlib import Path
from typing import List, Dict, Any
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

app = FastAPI()

# Enable CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Safely locate and load telemetry data
def load_telemetry() -> List[Dict[str, Any]]:
    possible_paths = [
        Path(__file__).resolve().parent / "q-vercel-latency.json",
        Path(__file__).resolve().parent.parent / "q-vercel-latency.json",
        Path.cwd() / "api" / "q-vercel-latency.json",
        Path.cwd() / "q-vercel-latency.json",
    ]
    for p in possible_paths:
        if p.exists():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    content = json.load(f)
                    if isinstance(content, list):
                        return content
                    if isinstance(content, dict):
                        for val in content.values():
                            if isinstance(val, list):
                                return val
            except Exception:
                pass
    return []


TELEMETRY_DATA = load_telemetry()


def calc_p95(vals: List[float]) -> float:
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
    req_regions = payload.get("regions", [])
    threshold = float(payload.get("threshold_ms", 180))

    grouped: Dict[str, List[Dict[str, Any]]] = {
        str(r).strip().lower(): [] for r in req_regions
    }

    for item in TELEMETRY_DATA:
        reg = str(item.get("region", "")).strip().lower()
        if reg in grouped:
            grouped[reg].append(item)

    regions_list = []
    output_dict = {}

    for r in req_regions:
        key = str(r).strip().lower()
        items = grouped.get(key, [])
        if not items:
            stat = {
                "avg_latency": 0.0,
                "p95_latency": 0.0,
                "avg_uptime": 0.0,
                "breaches": 0,
            }
        else:
            lats = [
                float(x.get("latency", x.get("latency_ms", 0.0)))
                for x in items
            ]
            upts = [
                float(x.get("uptime", x.get("uptime_pct", 0.0)))
                for x in items
            ]
            stat = {
                "avg_latency": round(sum(lats) / len(lats), 2),
                "p95_latency": round(calc_p95(lats), 2),
                "avg_uptime": round(sum(upts) / len(upts), 4),
                "breaches": int(sum(1 for lat in lats if lat > threshold)),
            }

        output_dict[r] = stat
        regions_list.append({"region": r, **stat})

    # Compatible with tests expecting {"regions": [...]} or {"emea": {...}, ...}
    result = dict(output_dict)
    result["regions"] = regions_list
    return result


# Global catch-all handler for GET, POST, and preflight OPTIONS
@app.api_route("/{full_path:path}", methods=["GET", "POST", "OPTIONS"])
@app.api_route("/", methods=["GET", "POST", "OPTIONS"])
async def handle_all(request: Request, full_path: str = ""):
    cors_headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "*",
    }

    if request.method == "OPTIONS":
        return Response(status_code=200, headers=cors_headers)

    if request.method == "GET":
        return JSONResponse(
            status_code=200,
            content={"status": "ok", "message": "Service live"},
            headers=cors_headers,
        )

    try:
        body = await request.json()
    except Exception:
        body = {}

    try:
        data = compute_metrics(body)
        return JSONResponse(status_code=200, content=data, headers=cors_headers)
    except Exception as e:
        return JSONResponse(
            status_code=200,
            content={"error": str(e)},
            headers=cors_headers,
        )
