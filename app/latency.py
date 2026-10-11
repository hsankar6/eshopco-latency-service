import json
from pathlib import Path
from statistics import mean
from typing import List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI()

# Allow POST requests from any origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_FILE = (
    Path(__file__).resolve().parent.parent
    / "q-vercel-latency.json"
)


class RequestBody(BaseModel):
    regions: List[str]
    threshold_ms: float = 180


def get_value(record, keys):
    """Return the first matching field in a record."""
    for key in keys:
        if key in record:
            return record[key]
    return None


def collect_records(data):
    """Find telemetry records in nested dictionaries or lists."""
    records = []

    def walk(value):
        if isinstance(value, dict):
            region = get_value(
                value, ["region", "region_name"]
            )
            latency = get_value(
                value,
                ["latency_ms", "latency", "response_time_ms"],
            )

            if region is not None and latency is not None:
                records.append(value)
                return

            for child in value.values():
                if isinstance(child, (dict, list)):
                    walk(child)

        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(data)
    return records


def percentile_95(values):
    """Calculate the 95th percentile using linear interpolation."""
    values = sorted(values)

    if len(values) == 1:
        return float(values[0])

    position = (len(values) - 1) * 0.95
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    fraction = position - lower

    return (
        values[lower]
        + (values[upper] - values[lower]) * fraction
    )


@app.post("/")
@app.post("/latency")
@app.post("/api/latency")
def latency_metrics(body: RequestBody):
    if not DATA_FILE.exists():
        raise HTTPException(
            status_code=500,
            detail="Telemetry JSON file not found",
        )

    try:
        with DATA_FILE.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=500,
            detail="Unable to read telemetry data",
        ) from exc

    records = collect_records(data)
    results = {}

    for region in body.regions:
        selected = [
            record
            for record in records
            if str(
                get_value(record, ["region", "region_name"])
            ).lower() == region.lower()
        ]

        if not selected:
            raise HTTPException(
                status_code=404,
                detail=f"No telemetry records for region: {region}",
            )

        latencies = [
            float(
                get_value(
                    record,
                    ["latency_ms", "latency", "response_time_ms"],
                )
            )
            for record in selected
        ]

        uptime_values = []

        for record in selected:
            uptime = get_value(
                record,
                ["uptime", "uptime_pct", "uptime_percent"],
            )

            if uptime is not None:
                uptime_values.append(float(uptime))

        results[region] = {
            "avg_latency": mean(latencies),
            "p95_latency": percentile_95(latencies),
            "avg_uptime": (
                mean(uptime_values) if uptime_values else 0
            ),
            "breaches": sum(
                latency > body.threshold_ms
                for latency in latencies
            ),
        }

    return {"regions": results}
