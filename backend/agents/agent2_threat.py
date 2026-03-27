"""Agent 2: Threat Assessment — score hex cells using RAG medical knowledge.

Reads Agent 1's HexEvent output, queries the Bedrock Knowledge Base for
clinical heat thresholds (WBGT, heat index, physiological limits), and
produces a ThreatMap with risk levels per hex.
"""

import json
import logging
import os

import boto3

from backend.agents.base import run_agent

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System Prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are the Threat Assessment Analyst for HEATWAVE, a heat crisis response system for Dallas, TX during the August 2023 heat wave.

YOUR MISSION: Given a spatial event grid from Agent 1 (hex cells with heat-related events), query the medical knowledge base to determine which zones have crossed physiological danger thresholds. Output a threat map with risk levels.

YOUR PROCESS:
1. Use get_hex_events to load Agent 1's output. Each hex now includes:
   - max_temp_f, max_apparent_f, hot_days (temperature data — may be direct station or interpolated from nearest station)
   - dispatch_count + dispatch_incidents (911 heat incidents with descriptions like "unexplained death", "found unresponsive")
   - service_count + service_types (311 requests by type: Homeless Encampment, Dead Animal, etc.)
   - social_count + social_signals (social media text excerpts about heat)
   - weather_source: "direct_station" vs "interpolated_nearest_station"
2. Query the knowledge base 2-3 times for medical thresholds:
   - WBGT/heat stroke criteria (CDC/NIOSH)
   - Heat index danger levels (NWS — may CONFLICT with WBGT)
   - Dallas UHI vulnerability data
3. Score ALL hexes using score_hex_batch. Send ONE batch call at a time with 20-30 hexes per batch. Make one call, wait for the result, then make the next call. Do NOT make multiple parallel tool calls. You MUST score every hex — do not stop after scoring only the top ones. Use 6-9 sequential batch calls to cover all 170 hexes.
4. IMPORTANT: When you find conflicting thresholds between NWS Heat Index and OSHA/NIOSH WBGT, note the discrepancy. Use the incident descriptions to inform your judgment — "unexplained death during 109F heat" should weigh heavily.

SCORING CRITERIA:
- CRITICAL (0.85-1.0): temp >= 105F AND (911 heat incidents OR vulnerable population signals OR power outage reports)
- HIGH (0.65-0.84): temp >= 100F AND (any corroborating signals from 911/311/social media)
- MEDIUM (0.40-0.64): temp >= 95F OR isolated heat signals without weather corroboration
- LOW (0.0-0.39): below thresholds, minimal signals

AGGRAVATING FACTORS (increase score within band):
- Homeless encampment 311 reports in the hex (vulnerable population)
- Nighttime temperature remaining above 80F (no recovery period)
- Multiple data source corroboration (weather + 911 + social media all flagging same hex)
- South/SE Dallas neighborhoods (higher UHI effect per the Dallas UHI Study)

OUTPUT FORMAT: Return a JSON object:
{
  "threat_map": [
    {
      "hex_id": "string",
      "risk_level": "CRITICAL|HIGH|MEDIUM|LOW",
      "risk_score": 0.0-1.0,
      "justification": "Evidence-based explanation citing specific thresholds and data sources",
      "conditions": {
        "max_temp_f": float,
        "event_count": int,
        "event_types": ["weather", "dispatch_911", ...],
        "aggravating_factors": ["list of factors"]
      }
    }
  ],
  "summary": {
    "total_hexes_scored": int,
    "critical": int,
    "high": int,
    "medium": int,
    "low": int,
    "conflict_notes": "Description of any threshold conflicts found between NWS and OSHA/NIOSH"
  }
}

CRITICAL RULES:
- Every risk_level assignment MUST have a justification citing specific evidence from the knowledge base.
- You MUST use query_knowledge_base at least twice — once for heat thresholds and once for Dallas-specific vulnerability.
- Do NOT fabricate medical thresholds. If the KB doesn't return relevant info, say so.
- Return ONLY the JSON output. No preamble, no commentary."""

# ---------------------------------------------------------------------------
# Tool Definitions
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "toolSpec": {
            "name": "get_hex_events",
            "description": "Load Agent 1's output — hex cells with heat-related events, counts, and conditions. Returns the full HexEvent list produced by the Spatial Triage agent.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "run_id": {
                            "type": "string",
                            "description": "Pipeline run ID to load results for",
                        }
                    },
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "query_knowledge_base",
            "description": "Query the HEATWAVE RAG knowledge base containing medical/regulatory reference documents: CDC/NIOSH heat stress criteria (WBGT thresholds), OSHA heat hazard assessment, NWS heat index safety (CONFLICT DOC), FEMA NIMS doctrine, DFR EMS Annual Report, and Dallas Urban Heat Island Study. Returns relevant text chunks with source attribution.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Natural language query about heat thresholds, medical criteria, or Dallas-specific conditions",
                        },
                        "num_results": {
                            "type": "integer",
                            "description": "Number of relevant chunks to return (default 5)",
                        },
                    },
                    "required": ["query"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "score_hex_threat",
            "description": "Score a SINGLE hex cell. Prefer score_hex_batch for efficiency.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "hex_id": {"type": "string"},
                        "max_temp_f": {"type": "number"},
                        "apparent_temp_f": {"type": "number"},
                        "dispatch_count": {"type": "integer"},
                        "service_count": {"type": "integer"},
                        "social_count": {"type": "integer"},
                        "has_vulnerable_population": {"type": "boolean"},
                        "nighttime_temp_above_80": {"type": "boolean"},
                        "multi_source_corroboration": {"type": "boolean"},
                    },
                    "required": ["hex_id", "max_temp_f"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "score_hex_batch",
            "description": "Score MULTIPLE hex cells in one call. Pass an array of hex objects. Each hex needs: hex_id, max_temp_f, and optionally apparent_temp_f, dispatch_count, service_count, social_count, has_vulnerable_population, nighttime_temp_above_80, multi_source_corroboration. Returns all scores at once. USE THIS to score all 170 hexes efficiently in batches of 20-30.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "hexes": {
                            "type": "array",
                            "description": "Array of hex objects to score",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "hex_id": {"type": "string"},
                                    "max_temp_f": {"type": "number"},
                                    "apparent_temp_f": {"type": "number"},
                                    "dispatch_count": {"type": "integer"},
                                    "service_count": {"type": "integer"},
                                    "social_count": {"type": "integer"},
                                    "has_vulnerable_population": {"type": "boolean"},
                                    "nighttime_temp_above_80": {"type": "boolean"},
                                    "multi_source_corroboration": {"type": "boolean"},
                                },
                                "required": ["hex_id", "max_temp_f"],
                            },
                        },
                    },
                    "required": ["hexes"],
                }
            },
        }
    },
]

# ---------------------------------------------------------------------------
# Tool Handlers
# ---------------------------------------------------------------------------

def _query_knowledge_base(query: str, num_results: int = 5) -> str:
    """Query the Bedrock Knowledge Base for relevant document chunks."""
    kb_id = os.environ.get("KNOWLEDGE_BASE_ID")

    if not kb_id:
        # Local fallback — return a note that KB is not configured
        return json.dumps({
            "results": [],
            "note": "Knowledge Base not configured (KNOWLEDGE_BASE_ID not set). "
                    "In production, this queries CDC/NIOSH, OSHA, NWS, FEMA, DFR, and UHI documents.",
        })

    try:
        client = boto3.client(
            "bedrock-agent-runtime",
            region_name=os.environ.get("AWS_REGION", "us-east-1"),
        )
        response = client.retrieve(
            knowledgeBaseId=kb_id,
            retrievalQuery={"text": query},
            retrievalConfiguration={
                "vectorSearchConfiguration": {"numberOfResults": num_results}
            },
        )

        results = []
        for r in response.get("retrievalResults", []):
            results.append({
                "text": r["content"]["text"],
                "source": r.get("location", {}).get("s3Location", {}).get("uri", "unknown"),
                "score": r.get("score", 0),
            })

        return json.dumps({"results": results})

    except Exception as e:
        logger.error("Knowledge Base query failed: %s", e)
        return json.dumps({"error": str(e), "results": []})


def _score_hex_threat(tool_input: dict) -> str:
    """Deterministic threat scoring formula."""
    max_temp = tool_input.get("max_temp_f", 0)
    apparent_temp = tool_input.get("apparent_temp_f", max_temp)
    dispatch_count = tool_input.get("dispatch_count", 0)
    service_count = tool_input.get("service_count", 0)
    social_count = tool_input.get("social_count", 0)
    vulnerable = tool_input.get("has_vulnerable_population", False)
    hot_night = tool_input.get("nighttime_temp_above_80", False)
    multi_source = tool_input.get("multi_source_corroboration", False)

    # Weather component (40%): use apparent temp (heat index) — scale 85-115F to 0.0-1.0
    weather_score = max(0.0, min(1.0, (apparent_temp - 85) / 30))

    # Dispatch component (25%): each incident adds weight, cap at 5
    dispatch_score = min(1.0, dispatch_count / 5)

    # 311 component (15%): each request adds weight, cap at 10
    service_score = min(1.0, service_count / 10)

    # Social component (10%): each post adds weight, cap at 5
    social_score = min(1.0, social_count / 5)

    # Aggravating factors (10%): each adds 0.33
    agg_score = 0.0
    factors = []
    if vulnerable:
        agg_score += 0.33
        factors.append("vulnerable_population")
    if hot_night:
        agg_score += 0.33
        factors.append("no_nighttime_recovery")
    if multi_source:
        agg_score += 0.34
        factors.append("multi_source_corroboration")
    agg_score = min(1.0, agg_score)

    # Weighted total
    total = (
        weather_score * 0.40
        + dispatch_score * 0.25
        + service_score * 0.15
        + social_score * 0.10
        + agg_score * 0.10
    )

    # Map to risk level
    if total >= 0.85:
        level = "CRITICAL"
    elif total >= 0.65:
        level = "HIGH"
    elif total >= 0.40:
        level = "MEDIUM"
    else:
        level = "LOW"

    return json.dumps({
        "hex_id": tool_input["hex_id"],
        "risk_score": round(total, 3),
        "risk_level": level,
        "component_scores": {
            "weather": round(weather_score, 3),
            "dispatch": round(dispatch_score, 3),
            "service": round(service_score, 3),
            "social": round(social_score, 3),
            "aggravating": round(agg_score, 3),
        },
        "aggravating_factors": factors,
    })


def _score_hex_batch(tool_input: dict) -> str:
    """Score multiple hexes in one call."""
    hexes = tool_input.get("hexes", [])
    results = []
    for h in hexes:
        result = json.loads(_score_hex_threat(h))
        results.append(result)
    return json.dumps({"scored": results, "count": len(results)})


def _load_hex_events(run_id: str = None) -> str:
    """Load Agent 1's output from S3 or local file."""
    # Try S3 first if run_id provided
    if run_id:
        try:
            bucket = os.environ.get("DATA_BUCKET")
            if bucket:
                s3 = boto3.client("s3")
                key = f"results/{run_id}/agent1.json"
                obj = s3.get_object(Bucket=bucket, Key=key)
                return obj["Body"].read().decode("utf-8")
        except Exception as e:
            logger.warning("Could not load from S3: %s", e)

    return json.dumps({
        "error": "No hex_events available. Run Agent 1 first.",
        "note": "In the pipeline, this loads Agent 1's output from S3 via run_id.",
    })


def handle_tool(tool_name: str, tool_input: dict) -> str:
    """Execute a tool call from Agent 2."""
    if tool_name == "get_hex_events":
        return _load_hex_events(tool_input.get("run_id"))

    elif tool_name == "query_knowledge_base":
        return _query_knowledge_base(
            tool_input["query"],
            tool_input.get("num_results", 5),
        )

    elif tool_name == "score_hex_threat":
        return _score_hex_threat(tool_input)

    elif tool_name == "score_hex_batch":
        return _score_hex_batch(tool_input)

    else:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run(run_id: str, hex_events: dict = None) -> dict:
    """Execute Agent 2: Threat Assessment.

    Args:
        run_id: Pipeline run ID (to load Agent 1 output from S3).
        hex_events: Optional — pass Agent 1 output directly (for local testing).

    Returns: {"threat_map": [...], "summary": {...}, "tokens_used": int}
    """
    user_message = (
        "Analyze the hex event grid from Agent 1 for the Dallas August 2023 heat wave. "
        "Query the knowledge base for medical heat thresholds and Dallas-specific vulnerability data. "
        "Score each hex cell and produce the threat map.\n\n"
    )

    # If hex_events passed directly, include them in the message
    if hex_events:
        user_message += f"Agent 1 output:\n{json.dumps(hex_events)}\n\n"
    else:
        user_message += f"Use get_hex_events with run_id '{run_id}' to load Agent 1's output.\n\n"

    # Collect all scored hexes from batch tool calls
    all_scored = []

    def tracking_handler(tool_name, tool_input):
        result = handle_tool(tool_name, tool_input)
        if tool_name in ("score_hex_batch", "score_hex_threat"):
            try:
                parsed_result = json.loads(result)
                if "scored" in parsed_result:
                    all_scored.extend(parsed_result["scored"])
                elif "hex_id" in parsed_result:
                    all_scored.append(parsed_result)
            except json.JSONDecodeError:
                pass
        return result

    result = run_agent(
        system_prompt=SYSTEM_PROMPT,
        tools=TOOLS,
        tool_handler=tracking_handler,
        user_message=user_message,
        max_turns=25,
        model="lite",  # Haiku — scoring uses deterministic formula, LLM just orchestrates
        use_guardrail=True,
    )

    try:
        parsed = json.loads(result["response"])
    except json.JSONDecodeError:
        logger.warning("Agent 2 response was not valid JSON, using collected scores")
        parsed = {"raw_response": result["response"]}

    # Always use the collected scores — they're complete even if the LLM text was truncated
    if all_scored:
        parsed["threat_map"] = all_scored
        by_level = {}
        for s in all_scored:
            lvl = s.get("risk_level", "UNKNOWN")
            by_level[lvl] = by_level.get(lvl, 0) + 1
        parsed["summary"] = {
            "total_hexes_scored": len(all_scored),
            **by_level,
        }
        logger.info("Agent 2 scored %d hexes: %s", len(all_scored), by_level)

    parsed["tokens_used"] = result["tokens_used"]
    parsed["tool_calls"] = result["tool_calls"]
    return parsed
