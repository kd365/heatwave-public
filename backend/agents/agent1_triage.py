"""Agent 1: Spatial Triage — ingest raw data, filter noise, geocode to H3 hex grid.

Data sources: 911 dispatch, weather stations, 311 requests, social media posts.
Output: list of HexEvents (hex_id, event_type, severity_score, timestamp, source).
"""

import json
import logging

from backend.agents.base import run_agent
from backend.utils.h3_geocoding import (
    geocode_911_records,
    geocode_weather_records,
    geocode_social_media_posts,
    aggregate_by_hex,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System Prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are the Spatial Triage Analyst for HEATWAVE, a heat crisis response system for Dallas, TX during the August 2023 heat wave (peak 109.3F on Aug 18).

YOUR MISSION: Ingest raw, unstructured data from multiple sources, extract ONLY heat-relevant signals, and output a structured spatial event list geocoded to H3 hexagonal grid cells.

DATA SOURCES AVAILABLE (use the tools to load each):
1. get_weather_data — 4,608 hourly weather records from 8 Dallas stations
2. get_911_records — 1,035 real Dallas PD dispatch records (heat signals buried in noise)
3. get_311_records — 4,482 service requests (homeless encampments, water, animal complaints)
4. get_social_media — 300 social media posts (mix of real heat complaints, sarcasm, and noise)

YOUR PROCESS:
1. Load each data source using the tools.
2. For 911 records: examine the "mo" (modus operandi) and "offincident" fields. Look for heat-related keywords: heat, hot, dehydrat, unresponsive, collapse, pass out, unconscious, welfare check, found down. IGNORE: thefts, assaults, traffic violations, property crimes — these are noise.
3. For 311 records: flag "Homeless Encampment" (vulnerable population exposure), "Dead Animal Pick Up" (heat mortality indicator), and "Water/Wastewater" (infrastructure stress). Other types are noise.
4. For weather data: identify stations/hours where temp_f >= 105 OR apparent_temp_f >= 108 as CRITICAL. Temp >= 100 as HIGH. Temp >= 95 as MEDIUM.
5. For social media: you MUST analyze the text for heat relevance. Ignore sarcasm ("oh wow sooo hot today" on a mild day), irrelevant posts (sports, food, jobs), and ads. Posts mentioning power outages, AC failure, elderly/vulnerable people, cooling centers, dehydration, or heat illness ARE signals. Posts without a zip code need you to extract location clues from the text.
6. After processing, use geocode_events to convert all events to H3 hex IDs and aggregate.

OUTPUT FORMAT: Return a JSON object with:
{
  "hex_events": [
    {
      "hex_id": "string",
      "event_type": "weather|dispatch_911|service_311|social_media",
      "severity_score": 0.0-1.0,
      "timestamp": "ISO-8601",
      "source": "description of the signal",
      "details": "relevant extracted text or conditions"
    }
  ],
  "summary": {
    "total_events": int,
    "by_type": {"weather": int, "dispatch_911": int, "service_311": int, "social_media": int},
    "critical_hexes": int,
    "data_quality": "notes on skipped records, sarcasm filtered, etc."
  }
}

CRITICAL RULES:
- You must ONLY output signals that are genuinely heat-related. Do NOT inflate the signal count.
- Sarcastic posts must be DISCARDED, not scored.
- For social media posts without zip codes, examine the text for location clues (neighborhood names, street references, landmarks). If no location can be determined, include the event with hex_id set to null.
- Return ONLY the JSON output. No preamble, no commentary."""

# ---------------------------------------------------------------------------
# Tool Definitions (Bedrock converse API format)
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "toolSpec": {
            "name": "get_weather_data",
            "description": "Load Dallas weather station data for Aug 2023. Returns JSON array of hourly weather records with station_id, lat, lon, timestamp, temp_f, apparent_temp_f, humidity, wind, and solar radiation.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {},
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "get_911_records",
            "description": "Load Dallas 911 dispatch records for Aug 2023. Returns JSON array with incidentnum, signal, offincident, mo (modus operandi narrative), premise, date1, time1, incident_address, zip_code, and geocoded_column (lat/lon).",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {},
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "get_311_records",
            "description": "Load Dallas 311 service requests for Aug 2023. Returns JSON array with service_request_type, address, created_date, lat, lon. Types include: Homeless Encampment, Dead Animal Pick Up, Animal Lack of Care, Water/Wastewater.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {},
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "get_social_media",
            "description": "Load social media posts from Dallas Aug 2023. Returns JSON array with id, timestamp, text, platform, and optional zip field. WARNING: ~40% of posts are noise (sports, food, ads), ~30% are sarcastic or ambiguous, ~30% are genuine heat signals. Many posts are missing zip codes — you must analyze the text for location clues.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {},
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "geocode_events",
            "description": "Geocode processed records to H3 hex grid and aggregate. Pass pre-classified events with lat/lon. Returns events enriched with hex_id and aggregation counts per hex.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "weather_records": {
                            "type": "array",
                            "description": "Weather records to geocode (must have lat, lon fields)",
                        },
                        "dispatch_records": {
                            "type": "array",
                            "description": "911 records to geocode (must have geocoded_column or zip_code)",
                        },
                        "service_records": {
                            "type": "array",
                            "description": "311 records to geocode (must have lat, lon fields)",
                        },
                        "social_posts": {
                            "type": "array",
                            "description": "Social media posts to geocode (must have zip field if available)",
                        },
                    },
                }
            },
        }
    },
]

# ---------------------------------------------------------------------------
# Data Loaders (read from local files or S3)
# ---------------------------------------------------------------------------

def _load_json(filename: str) -> list[dict]:
    """Load a JSON data file from the data directory."""
    import os
    # Try local path first, then S3
    local_paths = [
        os.path.join("data", "raw", filename),
        os.path.join("data", "synthetic", filename),
        os.path.join("/var/task", "data", "raw", filename),
        os.path.join("/var/task", "data", "synthetic", filename),
    ]
    for path in local_paths:
        if os.path.exists(path):
            with open(path) as f:
                return json.load(f)

    # Fallback: try S3
    try:
        import boto3
        bucket = os.environ.get("DATA_BUCKET")
        if bucket:
            s3 = boto3.client("s3")
            for prefix in ["raw/", "synthetic/"]:
                try:
                    obj = s3.get_object(Bucket=bucket, Key=f"{prefix}{filename}")
                    return json.loads(obj["Body"].read())
                except s3.exceptions.NoSuchKey:
                    continue
    except Exception as e:
        logger.warning("S3 fallback failed: %s", e)

    raise FileNotFoundError(f"Could not find {filename} locally or in S3")


def _load_weather():
    return _load_json("dallas_weather_aug2023.json")


def _load_911():
    return _load_json("dallas_911_aug2023.json")


def _load_311():
    return _load_json("dallas_311_aug2023.json")


def _load_social():
    return _load_json("social_media_posts.json")


# ---------------------------------------------------------------------------
# Geocoding Tool Handler
# ---------------------------------------------------------------------------

def _geocode_events(tool_input: dict) -> str:
    """Geocode all event types and return aggregated results."""
    results = {}

    weather = tool_input.get("weather_records", [])
    if weather:
        results["weather"] = geocode_weather_records(weather)

    dispatch = tool_input.get("dispatch_records", [])
    if dispatch:
        enriched, skipped = geocode_911_records(dispatch)
        results["dispatch"] = enriched
        results["dispatch_skipped"] = skipped

    service = tool_input.get("service_records", [])
    if service:
        # 311 records have top-level lat/lon like weather
        results["service"] = geocode_weather_records(service)

    social = tool_input.get("social_posts", [])
    if social:
        results["social"] = geocode_social_media_posts(social)

    # Aggregate all geocoded records
    all_records = (
        results.get("weather", [])
        + results.get("dispatch", [])
        + results.get("service", [])
        + results.get("social", [])
    )
    aggregation = aggregate_by_hex(all_records)

    return json.dumps({
        "geocoded_counts": {
            "weather": len(results.get("weather", [])),
            "dispatch": len(results.get("dispatch", [])),
            "dispatch_skipped": results.get("dispatch_skipped", 0),
            "service": len(results.get("service", [])),
            "social_located": len([p for p in results.get("social", []) if "hex_id" in p]),
            "social_unlocated": len([p for p in results.get("social", []) if "hex_id" not in p]),
        },
        "unique_hexes": len(aggregation),
        "hex_aggregation": {
            hex_id: info["count"] for hex_id, info in aggregation.items()
        },
    })


# ---------------------------------------------------------------------------
# Tool Handler (dispatches tool calls from Claude)
# ---------------------------------------------------------------------------

def handle_tool(tool_name: str, tool_input: dict) -> str:
    """Execute a tool call from Agent 1 and return the result."""
    if tool_name == "get_weather_data":
        data = _load_weather()
        # Truncate to manageable size for Claude — send summary + sample
        summary = {
            "total_records": len(data),
            "stations": list({r["station_id"] for r in data}),
            "date_range": f"{data[0]['timestamp']} to {data[-1]['timestamp']}",
            "temp_range": f"{min(r['temp_f'] for r in data)}F to {max(r['temp_f'] for r in data)}F",
            "sample_records": data[:3],
            "critical_records": [r for r in data if r["temp_f"] >= 105][:20],
            "high_records_count": len([r for r in data if r["temp_f"] >= 100]),
        }
        return json.dumps(summary)

    elif tool_name == "get_911_records":
        data = _load_911()
        return json.dumps({
            "total_records": len(data),
            "sample_records": data[:3],
            "all_records": data,  # 1,035 records — manageable for Claude
        })

    elif tool_name == "get_311_records":
        data = _load_311()
        # Group by type for easier analysis
        by_type = {}
        for r in data:
            t = r.get("service_request_type", "unknown")
            by_type.setdefault(t, []).append(r)
        summary = {
            "total_records": len(data),
            "by_type": {t: len(recs) for t, recs in by_type.items()},
            "sample_per_type": {
                t: recs[:3] for t, recs in by_type.items()
            },
        }
        return json.dumps(summary)

    elif tool_name == "get_social_media":
        data = _load_social()
        return json.dumps({
            "total_posts": len(data),
            "posts": data,  # 300 posts — manageable for Claude
        })

    elif tool_name == "geocode_events":
        return _geocode_events(tool_input)

    else:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run(run_id: str = None) -> dict:
    """Execute Agent 1: Spatial Triage.

    Returns: {"hex_events": [...], "summary": {...}, "tokens_used": int}
    """
    result = run_agent(
        system_prompt=SYSTEM_PROMPT,
        tools=TOOLS,
        tool_handler=handle_tool,
        user_message=(
            "Analyze all available data sources for the Dallas August 2023 heat wave. "
            "Load each data source, identify heat-relevant signals, filter noise, "
            "geocode events to H3 hexagons, and produce the structured HexEvent output."
        ),
    )

    # Parse the agent's JSON response
    try:
        parsed = json.loads(result["response"])
    except json.JSONDecodeError:
        logger.warning("Agent 1 response was not valid JSON, returning raw")
        parsed = {"raw_response": result["response"]}

    parsed["tokens_used"] = result["tokens_used"]
    parsed["tool_calls"] = result["tool_calls"]
    return parsed
