import json
import os
from pathlib import Path
from statistics import mean

from fastapi import FastAPI, Request
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)
@app.middleware("http")
async def ensure_cors_headers(request: Request, call_next):
    if request.method == "OPTIONS":
        response = Response(status_code=200)
    else:
        response = await call_next(request)

    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "*"
    return response



DATA_FILE = Path(__file__).resolve().parent.parent / "q-vercel-latency.json"


class RequestBody(BaseModel):
    regions: List[str]
    threshold_ms: float = 180


def get_value(record, keys):
    for key in keys:
        if key in record:
            return record[key]
    return None


def collect_records(obj):
    records = []

    def walk(value):
        if isinstance(value, dict):
            region = get_value(value, ["region", "region_name"])
            latency = get_value(
                value, ["latency_ms", "latency", "response_time_ms"]
            )

            if region is not None and latency is not None:
                records.append(value)

            for child in value.values():
                if isinstance(child, (dict, list)):
                    walk(child)

        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(obj)
    return records


def percentile_95(values):
    values = sorted(values)

    if len(values) == 1:
        return float(values[0])

    position = (len(values) - 1) * 0.95
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    fraction = position - lower

    return values[lower] + (
        values[upper] - values[lower]
    ) * fraction


@app.post("/")
@app.post("/api")
@app.post("/api/index")
def latency_metrics(body: RequestBody):
    if not DATA_FILE.exists():
        raise HTTPException(
            status_code=500,
            detail="Telemetry JSON file not found",
        )

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError):
        raise HTTPException(
            status_code=500,
            detail="Unable to read telemetry data",
        )

    records = collect_records(data)
    results = []

    for region in body.regions:
        selected = [
            record for record in records
            if str(get_value(record, ["region", "region_name"])).lower()
            == region.lower()
        ]

        if not selected:
            raise HTTPException(
                status_code=404,
                detail=f"No telemetry records for region: {region}",
            )

        latencies = [
            float(get_value(
                record,
                ["latency_ms", "latency", "response_time_ms"]
            ))
            for record in selected
        ]

        uptimes = [
            float(get_value(
                record,
                ["uptime", "uptime_pct", "uptime_percent"]
            ))
            for record in selected
            if get_value(
                record,
                ["uptime", "uptime_pct", "uptime_percent"]
            ) is not None
        ]

        results.append({
            "region": region,
            "avg_latency": mean(latencies),
            "p95_latency": percentile_95(latencies),
            "avg_uptime": mean(uptimes) if uptimes else 0,
            "breaches": sum(
                latency > body.threshold_ms for latency in latencies
            ),
        })

    return {"regions": results}
