"""Agent 3: Dispatch Commander — autonomous strategy selection and resource optimization.

Reads Agent 2's ThreatMap, loads asset inventory, queries RAG for FEMA/DFR
fleet constraints, autonomously selects one of three dispatch strategies,
executes it, and writes orders to DynamoDB.
"""

import json
import logging
import os

import boto3
import h3

from backend.agents.base import run_agent
from backend.utils.optimization import (
    RiskLevel,
    ThreatHex,
    Asset,
    optimize_coverage,
    optimize_response_time,
    optimize_staged_reserve,
)
from backend.utils.h3_geocoding import latlng_to_hex

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System Prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are the Dispatch Commander for HEATWAVE, a heat crisis response system for Dallas, TX during the August 2023 heat wave.

YOUR MISSION: Given a threat map from Agent 2, autonomously select the optimal dispatch strategy and deploy Dallas Fire-Rescue assets to maximize life safety coverage.

YOUR PROCESS:
1. Use get_threat_map to load Agent 2's scored hex grid.
2. Use get_available_assets to load the DFR asset inventory (101 assets across 11 types).
3. Use query_knowledge_base to understand DFR fleet capabilities and FEMA NIMS resource typing constraints.
4. ANALYZE the threat map and decide which strategy to use:

   STRATEGY SELECTION LOGIC (you must reason about this, not follow a hardcoded rule):

   a) optimize_coverage — Use when there are MANY critical/high hexes relative to available assets.
      You can't cover everything, so maximize the total threat weight covered.
      Example: 15 CRITICAL hexes but only 6 available ambulances.

   b) optimize_response_time — Use when there are FEW critical hexes and PLENTY of assets.
      The problem isn't which hexes to cover — it's getting there fast.
      Example: 2 CRITICAL hexes and 8 available ambulances.

   c) optimize_staged_reserve — Use when the situation is EVOLVING or UNCERTAIN.
      Deploy to CRITICAL now, stage reserves near HIGH hexes for escalation.
      Set staging_radius (how close to stage) and reserve_ratio (how much to hold back).
      Example: 5 CRITICAL now, 10 HIGH trending up, afternoon temperatures still climbing.

5. Execute your chosen strategy using the run_optimization tool.
6. Use dispatch_orders to write the final plan to the system.

ASSET TYPES IN YOUR INVENTORY:
- ambulance_als (47): Front-line ALS rescue units, 24hr, radius 3 hexes
- ambulance_als_peak (8): Peak-demand 10am-10pm, radius 3 hexes
- special_event_rescue (8): Redeployable from events, radius 3 hexes
- mini_ambulance (4): Compact units for access-limited areas, radius 4 hexes
- mobile_medical_unit (4): Field triage capability, radius 3 hexes, capacity 2
- right_care_unit (4): Behavioral health + welfare checks, radius 4 hexes, capacity 2
- dart_cares_unit (4): Transit-based outreach for vulnerable populations, radius 3 hexes
- medic1_suv (1): Low-acuity CBD response, weekdays only, radius 2 hexes
- modss_outreach (1): Severe weather shelter staffing, radius 5 hexes, capacity 3
- cooling_center_library (10): Fixed facilities, dispatch destinations (radius 0)
- cooling_center_recreation (10): Fixed facilities, dispatch destinations (radius 0)

NOTE: Cooling centers are FIXED — they don't move. Use them as destinations for directing citizens, not as deployable units. Filter them OUT before running optimization on mobile assets. But mention them in your dispatch plan as citizen-facing resources.

OUTPUT FORMAT: Return a JSON object:
{
  "strategy_used": "optimize_coverage|optimize_response_time|optimize_staged_reserve",
  "strategy_justification": "2-3 sentences explaining WHY you chose this strategy based on the threat map shape",
  "dispatch_plan": {
    "orders": [
      {
        "asset_id": "string",
        "asset_type": "string",
        "from_hex": "string",
        "to_hex": "string",
        "distance": int,
        "role": "deploy|stage"
      }
    ],
    "unassigned_hexes": ["hex_ids that couldn't be covered"],
    "summary": {
      "total_deployed": int,
      "total_staged": int,
      "critical_covered": int,
      "critical_total": int
    }
  },
  "cooling_centers_activated": ["list of cooling center IDs near high-threat hexes"],
  "recommendations": "Brief operational recommendations for incident commander"
}

CRITICAL RULES:
- You MUST justify your strategy choice. "I chose optimize_coverage because..." with specific numbers.
- You MUST query the knowledge base for DFR fleet information to validate your asset assumptions.
- Filter out cooling centers (coverage_radius 0) before running optimization — they are fixed facilities.
- Include cooling centers in your recommendations section as citizen-facing resources.
- Return ONLY the JSON output. No preamble, no commentary."""

# ---------------------------------------------------------------------------
# Tool Definitions
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "toolSpec": {
            "name": "get_threat_map",
            "description": "Load Agent 2's threat map — hex cells with risk levels (CRITICAL/HIGH/MEDIUM/LOW), risk scores, and justifications.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "run_id": {
                            "type": "string",
                            "description": "Pipeline run ID to load Agent 2 results",
                        }
                    },
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "get_available_assets",
            "description": "Load the Dallas Fire-Rescue asset inventory. Returns 101 assets across 11 NIMS-typed categories with home locations, coverage radius, capacity, and shift constraints.",
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
            "name": "query_knowledge_base",
            "description": "Query the HEATWAVE RAG knowledge base. Useful for: DFR EMS fleet details, FEMA NIMS resource typing standards, Dallas UHI neighborhood vulnerability data.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Natural language query about fleet capabilities, resource typing, or Dallas conditions",
                        },
                    },
                    "required": ["query"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "run_optimization",
            "description": "Execute one of the three dispatch optimization strategies. Returns a DispatchPlan with asset assignments.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "strategy": {
                            "type": "string",
                            "enum": ["optimize_coverage", "optimize_response_time", "optimize_staged_reserve"],
                            "description": "Which strategy to execute",
                        },
                        "threat_hexes": {
                            "type": "array",
                            "description": "List of {hex_id, risk_level, risk_score} objects from the threat map",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "hex_id": {"type": "string"},
                                    "risk_level": {"type": "string"},
                                    "risk_score": {"type": "number"},
                                },
                            },
                        },
                        "assets": {
                            "type": "array",
                            "description": "List of available asset objects (filtered — no cooling centers)",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "id": {"type": "string"},
                                    "asset_type": {"type": "string"},
                                    "hex_id": {"type": "string"},
                                    "coverage_radius": {"type": "integer"},
                                    "capacity": {"type": "integer"},
                                },
                            },
                        },
                        "staging_radius": {
                            "type": "integer",
                            "description": "For staged_reserve only: hex rings from HIGH cluster to stage reserves",
                        },
                        "reserve_ratio": {
                            "type": "number",
                            "description": "For staged_reserve only: fraction of assets to hold as reserves (0.0-1.0)",
                        },
                    },
                    "required": ["strategy", "threat_hexes", "assets"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "dispatch_orders",
            "description": "Write the final dispatch plan to the system (DynamoDB). This is the AUTONOMOUS ACTION — once called, orders are live.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "run_id": {"type": "string"},
                        "dispatch_plan": {
                            "type": "object",
                            "description": "The complete dispatch plan to persist",
                        },
                    },
                    "required": ["dispatch_plan"],
                }
            },
        }
    },
]

# ---------------------------------------------------------------------------
# Tool Handlers
# ---------------------------------------------------------------------------

def _load_asset_inventory() -> str:
    """Load the typed asset inventory."""
    try:
        # Try local first
        local_path = os.path.join("data", "synthetic", "dallas_asset_inventory.json")
        if os.path.exists(local_path):
            with open(local_path) as f:
                assets = json.load(f)
        else:
            # S3 fallback
            bucket = os.environ.get("DATA_BUCKET")
            s3 = boto3.client("s3")
            obj = s3.get_object(Bucket=bucket, Key="raw/dallas_asset_inventory.json")
            assets = json.loads(obj["Body"].read())

        # Summarize for Claude
        type_counts = {}
        for a in assets:
            t = a["asset_type"]
            type_counts[t] = type_counts.get(t, 0) + 1

        return json.dumps({
            "total_assets": len(assets),
            "by_type": type_counts,
            "mobile_assets": [a for a in assets if a.get("coverage_radius", 0) > 0],
            "fixed_facilities": [a for a in assets if a.get("coverage_radius", 0) == 0],
        })

    except Exception as e:
        logger.error("Failed to load asset inventory: %s", e)
        return json.dumps({"error": str(e)})


def _load_threat_map(run_id: str = None) -> str:
    """Load Agent 2's threat map from S3."""
    if run_id:
        try:
            bucket = os.environ.get("DATA_BUCKET")
            if bucket:
                s3 = boto3.client("s3")
                key = f"results/{run_id}/agent2.json"
                obj = s3.get_object(Bucket=bucket, Key=key)
                return obj["Body"].read().decode("utf-8")
        except Exception as e:
            logger.warning("Could not load threat map from S3: %s", e)

    return json.dumps({
        "error": "No threat_map available. Run Agent 2 first.",
    })


def _run_optimization(tool_input: dict) -> str:
    """Execute the selected optimization strategy."""
    strategy = tool_input["strategy"]

    # Convert threat hex dicts to ThreatHex objects
    risk_map = {
        "CRITICAL": RiskLevel.CRITICAL,
        "HIGH": RiskLevel.HIGH,
        "MEDIUM": RiskLevel.MEDIUM,
        "LOW": RiskLevel.LOW,
    }
    threat_map = []
    for t in tool_input.get("threat_hexes", []):
        level_str = t.get("risk_level", "LOW").upper()
        threat_map.append(ThreatHex(
            hex_id=t["hex_id"],
            risk_level=risk_map.get(level_str, RiskLevel.LOW),
            risk_score=t.get("risk_score", 0.5),
        ))

    # Convert asset dicts to Asset objects
    assets = []
    for a in tool_input.get("assets", []):
        assets.append(Asset(
            id=a["id"],
            asset_type=a.get("asset_type", "unknown"),
            hex_id=a.get("hex_id", ""),
            status=a.get("status", "available"),
            coverage_radius=a.get("coverage_radius", 1),
            capacity=a.get("capacity", 1),
        ))

    # Execute strategy
    if strategy == "optimize_coverage":
        plan = optimize_coverage(threat_map, assets)
    elif strategy == "optimize_response_time":
        plan = optimize_response_time(threat_map, assets)
    elif strategy == "optimize_staged_reserve":
        plan = optimize_staged_reserve(
            threat_map,
            assets,
            staging_radius=tool_input.get("staging_radius", 2),
            reserve_ratio=tool_input.get("reserve_ratio", 0.3),
        )
    else:
        return json.dumps({"error": f"Unknown strategy: {strategy}"})

    # Serialize the plan
    return json.dumps({
        "strategy_used": plan.strategy_used,
        "orders": [
            {
                "asset_id": o.asset_id,
                "from_hex": o.from_hex,
                "to_hex": o.to_hex,
                "distance": o.distance,
                "role": o.role,
            }
            for o in plan.orders
        ],
        "unassigned_hexes": plan.unassigned_hexes,
        "summary": plan.summary,
    })


def _dispatch_orders(tool_input: dict) -> str:
    """Write dispatch orders to DynamoDB (autonomous action)."""
    run_id = tool_input.get("run_id", "local-test")
    plan = tool_input.get("dispatch_plan", {})

    # Try DynamoDB
    table_name = os.environ.get("PIPELINE_TABLE")
    if table_name:
        try:
            dynamodb = boto3.resource(
                "dynamodb",
                region_name=os.environ.get("AWS_REGION", "us-east-1"),
            )
            table = dynamodb.Table(table_name)
            table.update_item(
                Key={"run_id": run_id},
                UpdateExpression="SET dispatch_plan = :plan, agent_3_status = :status",
                ExpressionAttributeValues={
                    ":plan": json.dumps(plan),
                    ":status": "COMPLETE",
                },
            )
            return json.dumps({"status": "dispatched", "run_id": run_id, "persisted_to": "dynamodb"})
        except Exception as e:
            logger.error("DynamoDB write failed: %s", e)
            return json.dumps({"status": "dispatched", "run_id": run_id, "error": str(e)})

    # Local fallback
    logger.info("Dispatch orders (local): %s", json.dumps(plan)[:200])
    return json.dumps({"status": "dispatched", "run_id": run_id, "persisted_to": "local_log"})


def _query_kb(query: str) -> str:
    """Reuse Agent 2's KB query logic."""
    from backend.agents.agent2_threat import _query_knowledge_base
    return _query_knowledge_base(query)


def _compute_cooling_activations(parsed: dict) -> list[str]:
    """Deterministically compute which cooling centers should be activated.

    A cooling center is activated if it sits within ACTIVATION_RADIUS hex rings
    of any CRITICAL or HIGH threat hex that was covered by a dispatch order.
    Falls back to checking all dispatch order destinations if threat level info
    is unavailable.

    This runs as a post-processing step after Agent 3 LLM output to guarantee
    correct activation regardless of what the LLM included in its response.
    """
    ACTIVATION_RADIUS = 2  # hex rings — ~1.5km at H3 resolution 8

    # Gather all to_hex destinations from the dispatch plan
    orders = parsed.get("dispatch_plan", {}).get("orders", [])
    covered_hexes: set[str] = {o["to_hex"] for o in orders if "to_hex" in o}

    if not covered_hexes:
        return []

    # Build a disk of all hexes within activation radius of any covered hex
    activation_zone: set[str] = set()
    for hex_id in covered_hexes:
        try:
            activation_zone.update(h3.grid_disk(hex_id, ACTIVATION_RADIUS))
        except Exception:
            pass  # invalid hex_id — skip

    if not activation_zone:
        return []

    # Load asset inventory to find cooling center hex locations
    try:
        local_path = os.path.join("data", "synthetic", "dallas_asset_inventory.json")
        if os.path.exists(local_path):
            with open(local_path) as f:
                assets = json.load(f)
        else:
            bucket = os.environ.get("DATA_BUCKET")
            s3 = boto3.client("s3")
            obj = s3.get_object(Bucket=bucket, Key="synthetic/dallas_asset_inventory.json")
            assets = json.loads(obj["Body"].read())
    except Exception as e:
        logger.warning("Could not load assets for cooling activation: %s", e)
        return []

    activated = []
    for asset in assets:
        if not asset.get("asset_type", "").startswith("cooling_center"):
            continue
        lat, lon = asset.get("home_lat"), asset.get("home_lon")
        if lat is None or lon is None:
            continue
        try:
            cc_hex = latlng_to_hex(float(lat), float(lon))
            if cc_hex in activation_zone:
                activated.append(asset["id"])
        except Exception:
            pass

    return activated


def handle_tool(tool_name: str, tool_input: dict) -> str:
    """Execute a tool call from Agent 3."""
    if tool_name == "get_threat_map":
        return _load_threat_map(tool_input.get("run_id"))

    elif tool_name == "get_available_assets":
        return _load_asset_inventory()

    elif tool_name == "query_knowledge_base":
        return _query_kb(tool_input["query"])

    elif tool_name == "run_optimization":
        return _run_optimization(tool_input)

    elif tool_name == "dispatch_orders":
        return _dispatch_orders(tool_input)

    else:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run(run_id: str, threat_map: dict = None) -> dict:
    """Execute Agent 3: Dispatch Commander.

    Args:
        run_id: Pipeline run ID (to load Agent 2 output from S3).
        threat_map: Optional — pass Agent 2 output directly (for local testing).

    Returns: {"dispatch_plan": {...}, "strategy_used": str, "tokens_used": int}
    """
    user_message = (
        "You are commanding the Dallas heat crisis response for August 2023. "
        "Load the threat map, assess the situation, load available DFR assets, "
        "query the knowledge base for fleet capabilities, select the optimal "
        "dispatch strategy, execute it, and dispatch the orders.\n\n"
    )

    if threat_map:
        user_message += f"Agent 2 threat map:\n{json.dumps(threat_map)}\n\n"
    else:
        user_message += f"Use get_threat_map with run_id '{run_id}' to load Agent 2's output.\n\n"

    # Capture optimization results from the tool handler
    optimization_result = {}

    def tracking_handler(tool_name, tool_input):
        result = handle_tool(tool_name, tool_input)
        if tool_name == "run_optimization":
            try:
                optimization_result.update(json.loads(result))
            except json.JSONDecodeError:
                pass
        return result

    result = run_agent(
        system_prompt=SYSTEM_PROMPT,
        tools=TOOLS,
        tool_handler=tracking_handler,
        user_message=user_message,
        max_turns=15,
        model="lite",  # Haiku — strategy selection + tool orchestration
    )

    try:
        parsed = json.loads(result["response"])
    except json.JSONDecodeError:
        logger.warning("Agent 3 response was not valid JSON, returning raw")
        parsed = {"raw_response": result["response"]}

    # Use optimization result directly — the LLM text may truncate or omit orders
    if optimization_result.get("orders"):
        parsed["orders"] = optimization_result["orders"]
        parsed.setdefault("strategy_used", optimization_result.get("strategy_used"))
        parsed.setdefault("unassigned_hexes", optimization_result.get("unassigned_hexes", []))
        parsed.setdefault("optimization_summary", optimization_result.get("summary", {}))
        logger.info("Agent 3 dispatched %d orders via %s",
                     len(optimization_result["orders"]),
                     optimization_result.get("strategy_used"))

    # Also extract justification from tool calls
    for tc in result["tool_calls"]:
        if tc["tool"] == "dispatch_orders":
            plan = tc["input"].get("dispatch_plan", {})
            parsed.setdefault("strategy_justification", plan.get("strategy_justification"))

    parsed["tokens_used"] = result["tokens_used"]
    parsed["tool_calls"] = result["tool_calls"]

    # Deterministic fallback: ensure cooling activations are populated even if LLM omitted them
    if not parsed.get("cooling_centers_activated"):
        parsed["cooling_centers_activated"] = _compute_cooling_activations(parsed)

    return parsed
