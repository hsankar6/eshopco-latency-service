import json
from pathlib import Path
from typing import List

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI()

# CORS: allow POST (and preflight OPTIONS) from any origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_FILE = Path(__file__).resolve().parent.parent / "q-vercel-latency.json"


def load_records():
    with open(DATA_FILE) as f:
        data = json.load(f)
    # Support either a bare list or {"records": [...]} / {"data": [...]}
    if isinstance(data, dict):
        for key in ("records", "data", "telemetry"):
            if key in data:
                return data[key]
    return data


RECORDS = load_records()


class Query(BaseModel):
    regions: List[str]
    threshold_ms: float


def mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def percentile(xs, p):
    """Linear-interpolation percentile (same as numpy default)."""
    if not xs:
        return 0.0
    s = sorted(xs)
    k = (len(s) - 1) * p / 100
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def uptime_of(r):
    for key in ("uptime_pct", "uptime", "uptime_percent"):
        if key in r:
            return r[key]
    return 0.0


def compute(q: Query):
    result = {}
    for region in q.regions:
        rows = [r for r in RECORDS if str(r.get("region", "")).lower() == region.lower()]
        lat = [r["latency_ms"] for r in rows]
        result[region] = {
            "avg_latency": mean(lat),
            "p95_latency": percentile(lat, 95),
            "avg_uptime": mean([uptime_of(r) for r in rows]),
            "breaches": sum(1 for x in lat if x > q.threshold_ms),
        }
    return {"regions": result}


@app.post("/")
@app.post("/api")
@app.post("/api/index")
@app.post("/api/latency")
def latency(q: Query):
    return compute(q)
