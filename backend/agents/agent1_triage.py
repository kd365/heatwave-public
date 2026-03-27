"""Agent 1: Spatial Triage — ingest raw data, filter noise, geocode to H3 hex grid.

Architecture — LLM calls only where text judgment is required:
- Weather: DETERMINISTIC (Python classifies all 4,608 records by numeric thresholds)
- 911: DETERMINISTIC pre-filter → 1 LLM call to judge ~50 MO narrative candidates
- 311: DETERMINISTIC (no narrative field — type + date + temp = signal or not)
- Social media: 1 LLM call for all 300 posts (sarcasm/noise filtering, text analysis)
- Synthesis: 1 LLM call to combine all findings into unified HexEvent list

Total LLM calls: 3 (911 judgment + social media filtering + synthesis)
Estimated runtime: 2-3 minutes

Design rationale:
- Weather has numeric thresholds — no ambiguity for an LLM to resolve
- 311 records have no narrative/text field — only type, date, address, lat/lon.
  A "Homeless Encampment" report during 109F heat is a signal by definition.
  The LLM cannot add judgment beyond what Python can determine from type + temperature.
- 911 records HAVE MO narratives with ambiguous text ("hot" = temperature or stolen property?)
  This is where LLM judgment is essential.
- Social media REQUIRES LLM for sarcasm detection, noise filtering, and location extraction
  from unstructured text. This is the core value of using an LLM for triage.
"""

import json
import logging
import os
import time
from collections import defaultdict

import h3

from backend.agents.base import run_agent
from backend.utils.h3_geocoding import (
    geocode_911_records,
    geocode_weather_records,
    geocode_social_media_posts,
    latlng_to_hex,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data Loaders
# ---------------------------------------------------------------------------

def _load_json(filename: str) -> list[dict]:
    """Load a JSON data file from the data directory or S3."""
    local_paths = [
        os.path.join("data", "raw", filename),
        os.path.join("data", "synthetic", filename),
        os.path.join("data", "reference", filename),
        os.path.join("/var/task", "data", "raw", filename),
        os.path.join("/var/task", "data", "synthetic", filename),
        os.path.join("/var/task", "data", "reference", filename),
    ]
    for path in local_paths:
        if os.path.exists(path):
            with open(path) as f:
                return json.load(f)
    try:
        import boto3
        bucket = os.environ.get("DATA_BUCKET")
        if bucket:
            s3 = boto3.client("s3")
            for prefix in ["raw/", "synthetic/"]:
                try:
                    obj = s3.get_object(Bucket=bucket, Key=f"{prefix}{filename}")
                    return json.loads(obj["Body"].read())
                except Exception:
                    continue
    except Exception as e:
        logger.warning("S3 fallback failed: %s", e)
    raise FileNotFoundError(f"Could not find {filename} locally or in S3")


# ---------------------------------------------------------------------------
# Sub-task 1a: Weather (DETERMINISTIC)
# ---------------------------------------------------------------------------

def _process_weather(target_date: str = None) -> dict:
    """Classify all weather records by numeric thresholds and geocode.

    No LLM needed — temperature thresholds are unambiguous:
    - CRITICAL: temp_f >= 105 OR apparent_temp_f >= 108
    - HIGH: temp_f >= 100
    - MEDIUM: temp_f >= 95
    """
    data = _load_json("dallas_weather_aug2023.json")
    if target_date:
        data = [r for r in data if r.get("timestamp", "")[:10] == target_date]

    # Aggregate to daily summary per station — one event per station-day.
    # Captures BOTH peak temperature AND duration of dangerous heat.
    # 8 hours at 105F is more dangerous than 1 hour at 105F (cumulative exposure).
    daily_station = {}
    for r in data:
        key = f"{r['station_id']}_{r['timestamp'][:10]}"
        temp = r.get("temp_f", 0)
        apparent = r.get("apparent_temp_f", temp)
        if key not in daily_station:
            daily_station[key] = {
                "station_id": r["station_id"],
                "lat": r["lat"],
                "lon": r["lon"],
                "date": r["timestamp"][:10],
                "max_temp": temp,
                "max_apparent": apparent,
                "min_temp": temp,
                "hours_above_95": 0,
                "hours_above_100": 0,
                "hours_above_105": 0,
            }
        ds = daily_station[key]
        ds["max_temp"] = max(ds["max_temp"], temp)
        ds["max_apparent"] = max(ds["max_apparent"], apparent)
        ds["min_temp"] = min(ds["min_temp"], temp)
        if temp >= 95:
            ds["hours_above_95"] += 1
        if temp >= 100:
            ds["hours_above_100"] += 1
        if temp >= 105:
            ds["hours_above_105"] += 1

    events = []
    for ds in daily_station.values():
        temp = ds["max_temp"]
        apparent = ds["max_apparent"]

        if temp < 95:
            continue

        # Base severity from peak temperature
        if temp >= 105 or apparent >= 108:
            severity = "CRITICAL"
            base_score = 0.85
        elif temp >= 100:
            severity = "HIGH"
            base_score = 0.65
        else:
            severity = "MEDIUM"
            base_score = 0.40

        # Duration bonus: prolonged exposure is more dangerous
        # Each hour above 100F adds to severity (capped at +0.15)
        duration_bonus = min(0.15, ds["hours_above_100"] * 0.015)
        score = min(1.0, base_score + duration_bonus)

        events.append({
            "station_id": ds["station_id"],
            "lat": ds["lat"],
            "lon": ds["lon"],
            "timestamp": ds["date"],
            "temp_f": temp,
            "apparent_temp_f": apparent,
            "hours_above_95": ds["hours_above_95"],
            "hours_above_100": ds["hours_above_100"],
            "hours_above_105": ds["hours_above_105"],
            "nighttime_above_80": ds["min_temp"] >= 80,
            "severity": severity,
            "severity_score": round(score, 3),
        })

    geocoded = geocode_weather_records(events)

    # Build daily max (across all stations) for 311 context
    daily_max = {}
    for r in data:
        key = r["timestamp"][:10]
        if key not in daily_max or r["temp_f"] > daily_max[key]:
            daily_max[key] = r["temp_f"]

    logger.info("Weather: %d/%d records above 95F threshold", len(events), len(data))
    return {
        "weather_events": geocoded,
        "total_records": len(data),
        "events_above_threshold": len(events),
        "daily_max_temps": daily_max,
        "by_severity": {
            "CRITICAL": len([e for e in events if e["severity"] == "CRITICAL"]),
            "HIGH": len([e for e in events if e["severity"] == "HIGH"]),
            "MEDIUM": len([e for e in events if e["severity"] == "MEDIUM"]),
        },
    }


# ---------------------------------------------------------------------------
# Sub-task 1b: 911 Dispatch (pre-filter + 1 LLM call for MO judgment)
# ---------------------------------------------------------------------------

DISPATCH_PROMPT = """You are analyzing Dallas 911 dispatch records from August 2023 — a month where Dallas experienced temperatures up to 109.3F with 21 days above 100F.

CRITICAL CONTEXT: During extreme heat waves, many heat deaths are recorded as "UNEXPLAINED DEATH" in police records because the medical examiner determines cause of death later. "Found unresponsive" during 109F heat is very likely heat-related. You must consider the extreme weather context when evaluating these records.

These records were pre-filtered from 1,276 total police dispatch records. Your job:

1. CONFIRM as heat-related (assign severity score):
   - "HEAT RELATED" explicitly mentioned → 0.95
   - "UNEXPLAINED DEATH" during Aug 2023 heat wave → 0.70 (probable heat death pending ME determination)
   - "FOUND UNRESPONSIVE" / "FOUND DECEASED" → 0.75 (likely heat exposure)
   - "PASSED OUT" outdoors or in vehicle → 0.65 (probable heat exhaustion)
   - "INJURED PERSON" without clear non-heat cause → 0.50 (possible heat-related)

2. REJECT only if there is a CLEAR non-heat cause:
   - Shooting, stabbing, assault with weapon → REJECT
   - Traffic accident with clear mechanism → REJECT
   - Drug-related (overdose, possession) → REJECT
   - Theft/burglary where "injured" is the victim of crime → REJECT

3. When in doubt, INCLUDE the record with a lower severity score. It is better to flag a possible heat death for Agent 2 to evaluate than to miss a real one.

IMPORTANT: Keep your response CONCISE to avoid truncation. For each incident use max 10 words in the reason field.

OUTPUT: Return JSON:
{
  "confirmed_heat_incidents": [
    {
      "incidentnum": "string",
      "date1": "string",
      "incident_address": "string",
      "zip_code": "string",
      "severity_score": float,
      "reason": "max 10 words",
      "geocoded_column": {"latitude": "string", "longitude": "string"}
    }
  ],
  "rejected_count": int,
  "summary": "one sentence"
}
Return ONLY the JSON object. No markdown, no code blocks, no preamble."""

DISPATCH_TOOLS = [{
    "toolSpec": {
        "name": "get_911_candidates",
        "description": "Load pre-filtered 911 records that matched heat keywords in MO narratives.",
        "inputSchema": {"json": {"type": "object", "properties": {}}},
    }
}]


def _process_911(target_date: str = None) -> dict:
    """Pre-filter by keywords, send MO narrative candidates to LLM for judgment.

    The LLM is essential here because MO narratives contain ambiguous language
    that only contextual reading can resolve (e.g., "hot" = temperature vs stolen property).
    """
    data = _load_json("dallas_911_aug2023.json")
    if target_date:
        data = [r for r in data if (r.get("date1") or "")[:10] == target_date]

    heat_keywords = ["heat related", "heat stroke", "heat exhaust", "dehydrat",
                     "unresponsive", "collapse", "pass out", "passed out",
                     "unconscious", "welfare", "found down", "found deceased",
                     "unexplained death", "overheat", "injured person"]
    candidates = []
    for r in data:
        mo = (r.get("mo") or "").lower()
        signal = (r.get("signal") or "").lower()
        offincident = (r.get("offincident") or "").lower()
        if any(kw in text for kw in heat_keywords for text in [mo, signal, offincident]):
            candidates.append(r)

    logger.info("911: %d/%d records matched heat keywords", len(candidates), len(data))

    if not candidates:
        return {"heat_dispatches": [], "total_records": len(data), "candidates": 0, "tokens_used": 0}

    def handle_tool(tool_name, tool_input):
        return json.dumps({
            "total_records": len(data),
            "candidates": candidates,
            "candidate_count": len(candidates),
        })

    result = run_agent(
        system_prompt=DISPATCH_PROMPT,
        tools=DISPATCH_TOOLS,
        tool_handler=handle_tool,
        user_message="Load and analyze the pre-filtered 911 dispatch records. Use your judgment on the MO narratives to confirm which are genuinely heat-related.",
    )

    logger.info("911 LLM response length: %d chars", len(result["response"]))
    logger.info("911 LLM response preview: %s", result["response"][:500])

    try:
        parsed = json.loads(result["response"])
    except json.JSONDecodeError:
        logger.warning("911 LLM response failed JSON parse: %s", result["response"][:300])
        parsed = {"confirmed_heat_incidents": [], "error": "parse_failed"}

    confirmed = parsed.get("confirmed_heat_incidents", [])
    logger.info("911 confirmed heat incidents: %d", len(confirmed))
    geocoded, skipped = geocode_911_records(confirmed)

    return {
        "heat_dispatches": geocoded,
        "total_records": len(data),
        "candidates": len(candidates),
        "confirmed": len(confirmed),
        "rejected": len(parsed.get("rejected", [])),
        "skipped_geocoding": skipped,
        "tokens_used": result["tokens_used"],
    }


# ---------------------------------------------------------------------------
# Sub-task 1c: 311 Service Requests (DETERMINISTIC)
# ---------------------------------------------------------------------------

# Severity scores by 311 type, scaled by daily max temperature.
# These are base scores — multiplied by a heat factor (temp/110) to reflect
# that the same report type is more dangerous on hotter days.
SERVICE_TYPE_SCORES = {
    "Homeless Encampment - OHS": 0.70,       # vulnerable population directly exposed
    "Dead Animal Pick Up - DAS": 0.35,        # environmental heat mortality indicator
    "Animal Lack of Care - DAS": 0.30,        # heat-related neglect indicator
    "Water/Wastewater Line Locate - 311": 0.40,  # infrastructure stress
    "Water Pollution Urgent - DWU": 0.45,     # infrastructure failure
}

# Minimum temperature for a 311 request to be considered heat-related.
# Below this, a homeless encampment report is routine, not a heat signal.
MIN_HEAT_TEMP_F = 95


def _process_311(daily_max_temps: dict, target_date: str = None) -> dict:
    """Classify 311 records deterministically using type + date temperature.

    No LLM needed — 311 records have no narrative/text field. The only data
    is type, date, address, and lat/lon. A "Homeless Encampment" report is
    a heat signal if and only if the temperature that day was dangerous.
    Python can make this determination as well as an LLM can.

    Severity is scaled by temperature: same report type scores higher on
    hotter days (109F homeless encampment > 96F homeless encampment).
    """
    data = _load_json("dallas_311_aug2023.json")
    if target_date:
        data = [r for r in data if (r.get("created_date") or "")[:10] == target_date]

    events = []
    skipped_cool_day = 0
    skipped_irrelevant_type = 0

    for r in data:
        rtype = r.get("service_request_type", "")
        date = r.get("created_date", "")[:10]

        # Check if this type is heat-relevant
        base_score = None
        for type_key, score in SERVICE_TYPE_SCORES.items():
            if type_key in rtype:
                base_score = score
                break

        if base_score is None:
            skipped_irrelevant_type += 1
            continue

        # Check if the temperature that day was dangerous
        day_temp = daily_max_temps.get(date, 0)
        if day_temp < MIN_HEAT_TEMP_F:
            skipped_cool_day += 1
            continue

        # Scale severity by temperature (hotter day = more dangerous)
        heat_factor = min(1.0, day_temp / 110)
        severity_score = round(base_score * heat_factor, 3)

        event = {
            "service_request_type": rtype,
            "date": date,
            "address": r.get("address"),
            "severity_score": severity_score,
            "day_temp_f": day_temp,
        }

        # Geocode if lat/lon available
        lat = r.get("lat")
        lon = r.get("lon")
        if lat and lon:
            try:
                event["lat"] = float(lat)
                event["lon"] = float(lon)
                event["hex_id"] = latlng_to_hex(float(lat), float(lon))
            except (ValueError, TypeError):
                pass

        events.append(event)

    # Aggregate by type for summary
    by_type = defaultdict(int)
    for e in events:
        by_type[e["service_request_type"]] += 1

    logger.info(
        "311: %d heat signals from %d records (skipped: %d cool-day, %d irrelevant-type)",
        len(events), len(data), skipped_cool_day, skipped_irrelevant_type,
    )

    return {
        "service_events": events,
        "total_records": len(data),
        "heat_signals": len(events),
        "by_type": dict(by_type),
        "skipped_cool_day": skipped_cool_day,
        "skipped_irrelevant_type": skipped_irrelevant_type,
        "tokens_used": 0,  # deterministic — no LLM
    }


# ---------------------------------------------------------------------------
# Sub-task 1d: Social Media (1 LLM call)
# ---------------------------------------------------------------------------

SOCIAL_PROMPT = """You are analyzing social media posts from Dallas during the August 2023 heat wave.

This is where your judgment as an LLM is essential — these posts contain sarcasm, noise, and ambiguity that only contextual reading can resolve.

FILTER RULES:
- DISCARD sarcasm ("oh wow sooo hot today" with eye-roll tone, jokes about cooking eggs on sidewalks)
- DISCARD irrelevant posts (sports scores, restaurant recommendations, job announcements, ads)
- DISCARD vague complaints that aren't actionable ("summer sucks")
- KEEP genuine heat signals:
  * Power outages during heat ("Oncor confirms 12,000+ without power")
  * AC failures affecting vulnerable people ("elderly mom wont leave his house. no AC. temp inside is 98")
  * Heat illness reports ("coworker collapsed at the construction site")
  * Cooling center needs ("where can homeless people go to cool off?")
  * Infrastructure failures ("water pressure is gone in our whole neighborhood")

LOCATION EXTRACTION (for posts without zip codes):
- Look for neighborhood names: SE Dallas, Oak Cliff, Pleasant Grove, Deep Ellum, Fair Park
- Street references: I-35, LBJ Freeway, Greenville Ave
- Landmarks: Fair Park, Reunion Tower, Trinity River
- Zip codes mentioned in text
- If no location clues exist, set zip to null

OUTPUT: Return JSON:
{
  "heat_signals": [
    {
      "id": "string",
      "timestamp": "string",
      "text": "original post text",
      "platform": "string",
      "zip": "string or null",
      "severity_score": 0.0-1.0,
      "signal_type": "power_outage|ac_failure|vulnerable_person|heat_illness|infrastructure|other",
      "location_source": "zip_field|text_extraction|unknown"
    }
  ],
  "discarded": {"sarcasm": int, "irrelevant": int, "total": int},
  "summary": "brief description of heat signals found and noise filtered"
}
Return ONLY JSON."""

SOCIAL_TOOLS = [{
    "toolSpec": {
        "name": "get_social_media",
        "description": "Load all social media posts for analysis. Posts have id, timestamp, text, platform, and optional zip field.",
        "inputSchema": {"json": {"type": "object", "properties": {}}},
    }
}]


def _process_social(target_date: str = None) -> dict:
    """Send posts to LLM for sarcasm/noise filtering and location extraction.

    The LLM is essential here because social media text requires:
    - Sarcasm detection ("sooo hot" = genuine or mocking?)
    - Relevance classification (sports post mentioning "heat" = Dallas Heat basketball?)
    - Location extraction from unstructured text (neighborhood names, landmarks)
    These are judgment calls that code cannot make reliably.
    """
    data = _load_json("social_media_posts.json")
    if target_date:
        data = [p for p in data if (p.get("timestamp") or "")[:10] == target_date]
    elif len(data) > 300:
        # When running all days, sample to keep within context limits:
        # Take all posts from peak days + random sample from other days
        peak_days = {"2023-08-17", "2023-08-18", "2023-08-19", "2023-08-20"}
        peak_posts = [p for p in data if (p.get("timestamp") or "")[:10] in peak_days]
        other_posts = [p for p in data if (p.get("timestamp") or "")[:10] not in peak_days]
        import random
        sample_size = max(0, 300 - len(peak_posts))
        sampled = random.sample(other_posts, min(sample_size, len(other_posts)))
        data = peak_posts + sampled
        logger.info("Social: sampled %d posts (all %d peak + %d other)", len(data), len(peak_posts), len(sampled))

    trimmed = []
    for p in data:
        trimmed.append({
            "id": p.get("id"),
            "timestamp": p.get("timestamp"),
            "text": p.get("text", "")[:280],
            "platform": p.get("platform"),
            "zip": p.get("zip"),
        })

    def handle_tool(tool_name, tool_input):
        return json.dumps({"total_posts": len(trimmed), "posts": trimmed})

    result = run_agent(
        system_prompt=SOCIAL_PROMPT,
        tools=SOCIAL_TOOLS,
        tool_handler=handle_tool,
        user_message="Load and analyze all social media posts. Apply your judgment to filter sarcasm and noise. Extract heat signals and location clues from the text.",
    )

    try:
        parsed = json.loads(result["response"])
    except json.JSONDecodeError:
        parsed = {"heat_signals": [], "error": "parse_failed"}

    signals = parsed.get("heat_signals", [])
    logger.info("Social LLM response length: %d chars", len(result["response"]))
    logger.info("Social LLM response preview: %s", result["response"][:500])
    logger.info("Social heat signals found: %d", len(signals))
    geocoded = geocode_social_media_posts(signals)

    return {
        "social_events": geocoded,
        "total_posts": len(data),
        "heat_signals": len(signals),
        "discarded": parsed.get("discarded", {}),
        "tokens_used": result["tokens_used"],
    }


# ---------------------------------------------------------------------------
# Synthesis (DETERMINISTIC hex grid + 1 LLM call for narrative only)
# ---------------------------------------------------------------------------

SYNTHESIS_PROMPT = """You are the Spatial Triage Analyst writing an operational summary for the Dallas August 2023 heat wave analysis.

You are receiving aggregated statistics from 4 data sources across {hex_count} H3 hex cells.
The hex grid and severity scores are already computed deterministically — your job is ONLY to write the narrative summary.

Describe:
1. Overall heat situation (how many hexes, severity distribution)
2. Which areas of Dallas are most affected and why
3. Multi-source corroboration patterns (hexes with weather + 311 are higher priority)
4. Data quality notes (what was deterministic vs LLM-judged, any gaps)

OUTPUT: Return JSON:
{{
  "narrative": "2-3 paragraph operational summary",
  "top_concerns": ["list of 3-5 most critical findings"],
  "data_quality": "processing notes"
}}
Return ONLY JSON."""


def _synthesize(weather, dispatch, service, social) -> dict:
    """Build complete hex grid DETERMINISTICALLY, use LLM only for narrative.

    The hex grid must contain ALL hexes with events — not a summary.
    Agent 2 needs descriptive data (temps, incident types, counts) to make
    RAG-informed risk judgments. We do NOT pre-score severity here.
    """
    # Build weather station lookup for nearest-station interpolation
    station_hexes = {}  # hex_id -> {max_temp_f, hot_days, apparent_temp_f, ...}
    for e in weather.get("weather_events", []):
        hid = e.get("hex_id")
        if not hid:
            continue
        if hid not in station_hexes:
            station_hexes[hid] = {
                "max_temp_f": 0, "max_apparent_f": 0,
                "hot_days": 0, "temps_by_day": {},
            }
        sh = station_hexes[hid]
        sh["max_temp_f"] = max(sh["max_temp_f"], e.get("max_temp_f", e.get("temp_f", 0)))
        sh["max_apparent_f"] = max(sh["max_apparent_f"], e.get("max_apparent_f", e.get("apparent_temp_f", 0)))
        day = e.get("date") or e.get("timestamp", "")[:10]
        if day:
            sh["temps_by_day"][day] = max(sh["temps_by_day"].get(day, 0), e.get("max_temp_f", e.get("temp_f", 0)))

    # Finalize station data
    for sh in station_hexes.values():
        sh["hot_days"] = len([t for t in sh["temps_by_day"].values() if t >= 100])
        del sh["temps_by_day"]

    # Nearest-station interpolation + UHI adjustment
    # Dallas UHI Study (Texas Trees Foundation, 2017) found:
    # - Downtown/South Dallas: up to +5F above suburban baseline
    # - Industrial corridors (SE): +3-4F
    # - Northern suburbs (tree canopy): baseline or -1F
    # We model this as a latitude gradient + impervious surface proxy.
    # Dallas center: ~32.78 lat. South = hotter, north = cooler.
    DALLAS_CENTER_LAT = 32.78
    UHI_MAX_ADJUSTMENT = 5.0  # max degrees F added in hottest urban core

    def _uhi_adjustment(hex_id):
        """Estimate UHI temperature offset based on location within Dallas.

        Based on Dallas UHI Study findings. South/central Dallas has higher
        impervious surface and less tree canopy = hotter. This is an
        approximation — documented as a limitation.
        """
        lat, lon = h3.cell_to_latlng(hex_id)
        # Latitude factor: south of center = positive adjustment
        lat_factor = max(0, min(1.0, (DALLAS_CENTER_LAT - lat + 0.05) / 0.25))
        # Longitude factor: central Dallas (around -96.80) is denser
        lon_center = -96.80
        lon_factor = max(0, min(1.0, 1.0 - abs(lon - lon_center) / 0.15))
        # Combined: multiply factors, scale by max adjustment
        return round(UHI_MAX_ADJUSTMENT * lat_factor * lon_factor, 1)

    station_hex_list = list(station_hexes.keys())

    def _nearest_station_weather(hex_id):
        """Assign weather from nearest station + UHI adjustment. Returns (data, source_type)."""
        if hex_id in station_hexes:
            data = dict(station_hexes[hex_id])
            data["uhi_adjustment_f"] = _uhi_adjustment(hex_id)
            data["max_temp_f"] = round(data["max_temp_f"] + data["uhi_adjustment_f"], 1)
            data["max_apparent_f"] = round(data["max_apparent_f"] + data["uhi_adjustment_f"], 1)
            return data, "direct_station_uhi_adjusted"
        if not station_hex_list:
            return {"max_temp_f": 0, "max_apparent_f": 0, "hot_days": 0, "uhi_adjustment_f": 0}, "none"
        best_dist = float("inf")
        best_hex = station_hex_list[0]
        for sh in station_hex_list:
            try:
                d = h3.grid_distance(hex_id, sh)
            except Exception:
                d = 999
            if d < best_dist:
                best_dist = d
                best_hex = sh
        data = dict(station_hexes[best_hex])
        data["uhi_adjustment_f"] = _uhi_adjustment(hex_id)
        data["max_temp_f"] = round(data["max_temp_f"] + data["uhi_adjustment_f"], 1)
        data["max_apparent_f"] = round(data["max_apparent_f"] + data["uhi_adjustment_f"], 1)
        return data, "interpolated_nearest_station_uhi_adjusted"

    # Load census data for population per hex
    census_lookup = {}
    try:
        census_data = _load_json("dallas_census_by_hex.json")
        for c in census_data:
            census_lookup[c["hex_id"]] = {
                "population": c["population"],
                "elderly_65plus": c["elderly_65plus"],
                "pct_elderly": c["pct_elderly"],
            }
        logger.info("Census: loaded population for %d hexes", len(census_lookup))
    except FileNotFoundError:
        logger.warning("Census data not found — population will not be included in hex grid")

    # Collect all hexes: start with full Dallas grid, then add any from data sources
    all_hex_ids = set()
    try:
        dallas_grid = _load_json("dallas_hex_grid.json")
        all_hex_ids.update(dallas_grid)
        logger.info("Loaded full Dallas hex grid: %d hexes", len(dallas_grid))
    except FileNotFoundError:
        logger.warning("Dallas hex grid not found — using only hexes with data")

    for e in weather.get("weather_events", []):
        if e.get("hex_id"):
            all_hex_ids.add(e["hex_id"])
    for e in dispatch.get("heat_dispatches", []):
        if e.get("hex_id"):
            all_hex_ids.add(e["hex_id"])
    for e in service.get("service_events", []):
        if e.get("hex_id"):
            all_hex_ids.add(e["hex_id"])
    for e in social.get("social_events", []):
        if e.get("hex_id"):
            all_hex_ids.add(e["hex_id"])

    # Build descriptive data per hex (for Agent 2 to judge with RAG)
    hex_data = {}
    for hid in all_hex_ids:
        wx, wx_source = _nearest_station_weather(hid)
        census = census_lookup.get(hid, {})
        hex_data[hid] = {
            "max_temp_f": wx["max_temp_f"],
            "max_apparent_f": wx["max_apparent_f"],
            "hot_days": wx["hot_days"],
            "weather_source": wx_source,
            "population": census.get("population", 0),
            "elderly_65plus": census.get("elderly_65plus", 0),
            "pct_elderly": census.get("pct_elderly", 0),
            "dispatch_incidents": [],
            "dispatch_count": 0,
            "service_types": defaultdict(int),
            "service_count": 0,
            "social_signals": [],
            "social_count": 0,
            "sources": set(),
        }

    # Weather — mark hexes with direct station data
    for e in weather.get("weather_events", []):
        hid = e.get("hex_id")
        if hid and hid in hex_data:
            hex_data[hid]["sources"].add("weather")

    # 911 dispatches — include incident descriptions
    for e in dispatch.get("heat_dispatches", []):
        hid = e.get("hex_id")
        if not hid or hid not in hex_data:
            continue
        h = hex_data[hid]
        h["dispatch_count"] += 1
        reason = e.get("reason", e.get("mo", "heat-related incident"))
        h["dispatch_incidents"].append(reason[:80])
        h["sources"].add("dispatch_911")

    # 311 service events — group by type
    for e in service.get("service_events", []):
        hid = e.get("hex_id")
        if not hid or hid not in hex_data:
            continue
        h = hex_data[hid]
        h["service_count"] += 1
        stype = e.get("service_type", "unknown")
        h["service_types"][stype] += 1
        h["sources"].add("service_311")

    # Social media — include signal text
    for e in social.get("social_events", []):
        hid = e.get("hex_id")
        if not hid or hid not in hex_data:
            continue
        h = hex_data[hid]
        h["social_count"] += 1
        text = e.get("text", e.get("content", "social media signal"))
        h["social_signals"].append(text[:100])
        h["sources"].add("social_media")

    # Build hex_events list — descriptive, no pre-scored severity
    hex_events = []
    for hex_id, h in hex_data.items():
        sources = h["sources"]
        total_incidents = h["dispatch_count"] + h["service_count"] + h["social_count"]

        hex_events.append({
            "hex_id": hex_id,
            "max_temp_f": h["max_temp_f"],
            "max_apparent_f": h["max_apparent_f"],
            "hot_days": h["hot_days"],
            "weather_source": h["weather_source"],
            "population": h["population"],
            "elderly_65plus": h["elderly_65plus"],
            "pct_elderly": h["pct_elderly"],
            "dispatch_count": h["dispatch_count"],
            "dispatch_incidents": h["dispatch_incidents"],
            "service_count": h["service_count"],
            "service_types": dict(h["service_types"]),
            "social_count": h["social_count"],
            "social_signals": h["social_signals"],
            "total_incident_count": total_incidents,
            "source_count": len(sources),
            "sources": sorted(sources),
        })

    # Sort by total incident count (highest first)
    hex_events.sort(key=lambda x: x["total_incident_count"], reverse=True)

    # Summary counts
    multi_source = len([e for e in hex_events if e["source_count"] >= 2])

    summary = {
        "total_hexes": len(hex_events),
        "multi_source_hexes": multi_source,
        "hexes_with_dispatch": len([e for e in hex_events if e["dispatch_count"] > 0]),
        "hexes_with_service": len([e for e in hex_events if e["service_count"] > 0]),
        "hexes_with_social": len([e for e in hex_events if e["social_count"] > 0]),
        "hexes_with_direct_weather": len([e for e in hex_events if e["weather_source"] == "direct_station"]),
        "hexes_with_interpolated_weather": len([e for e in hex_events if e["weather_source"] == "interpolated_nearest_station"]),
        "total_weather_events": weather.get("events_above_threshold", 0),
        "total_dispatch_confirmed": dispatch.get("confirmed", 0),
        "total_service_signals": service.get("heat_signals", 0),
        "total_social_signals": social.get("heat_signals", 0),
        "note": "Severity scoring is deferred to Agent 2 (RAG-informed). Weather for hexes without stations is interpolated from nearest station.",
    }

    # LLM narrative (optional — if it fails, the hex grid is still complete)
    try:
        narrative_input = json.dumps({
            "hex_count": len(hex_events),
            "multi_source_hexes": multi_source,
            "top_5_hexes": hex_events[:5],
            "weather_note": f"{summary['hexes_with_direct_weather']} hexes with direct station data, {summary['hexes_with_interpolated_weather']} interpolated from nearest station",
            "dispatch_summary": f"{dispatch.get('confirmed', 0)} confirmed heat incidents across {summary['hexes_with_dispatch']} hexes",
            "service_summary": f"{service.get('heat_signals', 0)} heat-related 311 requests across {summary['hexes_with_service']} hexes",
            "social_summary": f"{social.get('heat_signals', 0)} social media signals across {summary['hexes_with_social']} hexes",
        })

        prompt = SYNTHESIS_PROMPT.format(hex_count=len(hex_events))
        result = run_agent(
            system_prompt=prompt,
            tools=[],
            tool_handler=lambda n, i: "{}",
            user_message=f"Write the operational summary:\n\n{narrative_input}",
            model="lite",  # Haiku — summarization only, no judgment needed
        )

        try:
            narrative = json.loads(result["response"])
        except json.JSONDecodeError:
            narrative = {"narrative": result["response"]}

        summary["narrative"] = narrative.get("narrative", "")
        summary["top_concerns"] = narrative.get("top_concerns", [])
        synthesis_tokens = result["tokens_used"]
    except Exception as e:
        logger.warning("Synthesis narrative failed (hex grid still complete): %s", e)
        summary["narrative"] = "Narrative generation failed — hex grid data is complete."
        synthesis_tokens = 0

    return {
        "hex_events": hex_events,
        "summary": summary,
        "tokens_used": synthesis_tokens,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run(run_id: str = None, target_date: str = None) -> dict:
    """Execute Agent 1: Spatial Triage.

    Args:
        run_id: Pipeline run ID.
        target_date: Optional date filter (YYYY-MM-DD). If provided, only
                     processes data from that specific day.

    Pipeline: 3 LLM calls + 2 deterministic steps
    1. Weather — deterministic (no LLM)
    2. 911 — keyword pre-filter + 1 LLM call for MO narrative judgment
    3. 311 — deterministic (no narrative, type + temp = signal)
    4. Social media — 1 LLM call for sarcasm/noise/location
    5. Synthesis — 1 LLM call to produce unified HexEvent list

    Returns: {"hex_events": [...], "summary": {...}, "tokens_used": int}
    """
    if target_date:
        logger.info("Agent 1 — filtering to target_date: %s", target_date)
    total_tokens = 0

    # 1. Weather (deterministic)
    logger.info("Agent 1 — Weather: classifying all records by thresholds...")
    weather = _process_weather(target_date=target_date)

    # 2. 911 Dispatch (1 LLM call)
    logger.info("Agent 1 — 911: analyzing MO narratives...")
    dispatch = _process_911(target_date=target_date)
    total_tokens += dispatch.get("tokens_used", 0)

    # 3. 311 Service (deterministic)
    logger.info("Agent 1 — 311: classifying by type + temperature...")
    service = _process_311(weather.get("daily_max_temps", {}), target_date=target_date)

    # Rate limit cooldown between LLM calls
    logger.info("Agent 1 — cooling down 30s before social media LLM call...")
    time.sleep(30)

    # 4. Social Media (1 LLM call)
    logger.info("Agent 1 — Social: filtering sarcasm and noise...")
    social = _process_social(target_date=target_date)
    total_tokens += social.get("tokens_used", 0)

    # Rate limit cooldown before synthesis LLM call
    logger.info("Agent 1 — cooling down 30s before synthesis LLM call...")
    time.sleep(30)

    # 5. Synthesis (1 LLM call)
    logger.info("Agent 1 — Synthesis: combining all findings...")
    synthesis = _synthesize(weather, dispatch, service, social)
    total_tokens += synthesis.get("tokens_used", 0)

    result = synthesis
    result["tokens_used"] = total_tokens
    result["sub_task_summary"] = {
        "weather": f"{weather['events_above_threshold']}/{weather['total_records']} above threshold (deterministic)",
        "dispatch": f"{dispatch['confirmed']}/{dispatch['total_records']} confirmed heat incidents (LLM-judged)",
        "service": f"{service['heat_signals']}/{service['total_records']} heat signals (deterministic: type + temp)",
        "social": f"{social['heat_signals']}/{social['total_posts']} heat signals (LLM: sarcasm filtered)",
    }
    return result


# ---------------------------------------------------------------------------
# Legacy handle_tool for test compatibility
# ---------------------------------------------------------------------------

def handle_tool(tool_name: str, tool_input: dict) -> str:
    """Execute a tool call (used by tests)."""
    if tool_name == "get_weather_data":
        return json.dumps(_process_weather())
    elif tool_name == "get_911_records":
        data = _load_json("dallas_911_aug2023.json")
        heat_keywords = ["heat related", "heat stroke", "heat exhaust", "dehydrat",
                         "unresponsive", "collapse", "pass out", "passed out",
                         "unconscious", "welfare", "found down", "found deceased",
                         "unexplained death", "overheat", "injured person"]
        candidates = []
        for r in data:
            mo = (r.get("mo") or "").lower()
            signal = (r.get("signal") or "").lower()
            offincident = (r.get("offincident") or "").lower()
            if any(kw in text for kw in heat_keywords for text in [mo, signal, offincident]):
                candidates.append(r)
        return json.dumps({
            "total_records": len(data),
            "pre_filtered_count": len(candidates),
            "heat_candidate_records": candidates,
        })
    elif tool_name == "get_311_records":
        data = _load_json("dallas_311_aug2023.json")
        return json.dumps({"total_311_records": len(data)})
    elif tool_name == "get_social_media":
        data = _load_json("social_media_posts.json")
        return json.dumps({"total_posts": len(data), "posts": data})
    else:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})
