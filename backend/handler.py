"""HEATWAVE FastAPI backend — Lambda entry point via Mangum.

Routes:
  GET  /health                       — health check
  POST /api/v1/analyze               — trigger 3-agent pipeline
  GET  /api/v1/runs/{run_id}/status  — poll pipeline status
  GET  /api/v1/runs/{run_id}/result  — fetch final results
  GET  /api/v1/runs                  — list recent runs
"""

import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone

import boto3
import threading
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum

from backend.agents import agent1_triage, agent2_threat, agent3_dispatch

logger = logging.getLogger(__name__)
logging.basicConfig(level=os.environ.get("POWERTOOLS_LOG_LEVEL", "INFO"))

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(title="HEATWAVE", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tighten to CloudFront domain in production
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

# AWS clients (lazy init for Lambda reuse)
_dynamodb = None
_s3 = None

DATA_BUCKET = os.environ.get("DATA_BUCKET", "heatwave-dev-data-388691194728")
PIPELINE_TABLE = os.environ.get("PIPELINE_TABLE", "heatwave-dev-pipeline-runs")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")


def _get_dynamodb():
    global _dynamodb
    if _dynamodb is None:
        _dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
    return _dynamodb


def _get_s3():
    global _s3
    if _s3 is None:
        _s3 = boto3.client("s3", region_name=AWS_REGION)
    return _s3


def _get_table():
    return _get_dynamodb().Table(PIPELINE_TABLE)


# ---------------------------------------------------------------------------
# Pipeline execution (runs as background task)
# ---------------------------------------------------------------------------

def _run_pipeline(run_id: str):
    """Execute the 3-agent pipeline sequentially."""
    table = _get_table()
    s3 = _get_s3()
    start_time = time.time()
    total_tokens = 0

    try:
        # ── Agent 1: Spatial Triage ──
        table.update_item(
            Key={"run_id": run_id},
            UpdateExpression="SET agent_1_status = :s",
            ExpressionAttributeValues={":s": "RUNNING"},
        )

        agent1_result = agent1_triage.run(run_id=run_id)
        total_tokens += agent1_result.get("tokens_used", 0)

        # Save Agent 1 output to S3
        s3.put_object(
            Bucket=DATA_BUCKET,
            Key=f"results/{run_id}/agent1.json",
            Body=json.dumps(agent1_result),
            ContentType="application/json",
        )

        table.update_item(
            Key={"run_id": run_id},
            UpdateExpression="SET agent_1_status = :s, hex_events_key = :k",
            ExpressionAttributeValues={
                ":s": "COMPLETE",
                ":k": f"results/{run_id}/agent1.json",
            },
        )

        # Rate limit cooldown between agents
        logger.info("Cooling down 60s between Agent 1 and Agent 2...")
        time.sleep(60)

        # ── Agent 2: Threat Assessment ──
        table.update_item(
            Key={"run_id": run_id},
            UpdateExpression="SET agent_2_status = :s",
            ExpressionAttributeValues={":s": "RUNNING"},
        )

        agent2_result = agent2_threat.run(
            run_id=run_id,
            hex_events=agent1_result,
        )
        total_tokens += agent2_result.get("tokens_used", 0)

        s3.put_object(
            Bucket=DATA_BUCKET,
            Key=f"results/{run_id}/agent2.json",
            Body=json.dumps(agent2_result),
            ContentType="application/json",
        )

        table.update_item(
            Key={"run_id": run_id},
            UpdateExpression="SET agent_2_status = :s, threat_map_key = :k",
            ExpressionAttributeValues={
                ":s": "COMPLETE",
                ":k": f"results/{run_id}/agent2.json",
            },
        )

        # Rate limit cooldown between agents
        logger.info("Cooling down 60s between Agent 2 and Agent 3...")
        time.sleep(60)

        # ── Agent 3: Dispatch Commander ──
        table.update_item(
            Key={"run_id": run_id},
            UpdateExpression="SET agent_3_status = :s",
            ExpressionAttributeValues={":s": "RUNNING"},
        )

        agent3_result = agent3_dispatch.run(
            run_id=run_id,
            threat_map=agent2_result,
        )
        total_tokens += agent3_result.get("tokens_used", 0)

        s3.put_object(
            Bucket=DATA_BUCKET,
            Key=f"results/{run_id}/agent3.json",
            Body=json.dumps(agent3_result),
            ContentType="application/json",
        )

        # ── Pipeline complete ──
        duration_ms = int((time.time() - start_time) * 1000)

        table.update_item(
            Key={"run_id": run_id},
            UpdateExpression=(
                "SET agent_3_status = :s, dispatch_plan_key = :k, "
                "#st = :complete, tokens_used = :t, duration_ms = :d"
            ),
            ExpressionAttributeNames={"#st": "status"},
            ExpressionAttributeValues={
                ":s": "COMPLETE",
                ":k": f"results/{run_id}/agent3.json",
                ":complete": "COMPLETE",
                ":t": total_tokens,
                ":d": duration_ms,
            },
        )

        logger.info(
            "Pipeline %s complete: %d tokens, %d ms",
            run_id, total_tokens, duration_ms,
        )

    except Exception as e:
        logger.error("Pipeline %s failed: %s", run_id, e)
        table.update_item(
            Key={"run_id": run_id},
            UpdateExpression="SET #st = :s, error_message = :e",
            ExpressionAttributeNames={"#st": "status"},
            ExpressionAttributeValues={
                ":s": "ERROR",
                ":e": str(e),
            },
        )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok", "service": "heatwave", "version": "1.0.0"}


@app.post("/api/v1/analyze")
def analyze():
    """Trigger the 3-agent pipeline. Returns run_id immediately.

    Creates a DynamoDB record, then invokes this same Lambda asynchronously
    with a pipeline_run event. The async invocation runs the full pipeline
    (up to 900s) without blocking the API Gateway response.
    """
    run_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    # Create initial run record
    table = _get_table()
    table.put_item(Item={
        "run_id": run_id,
        "created_at": now,
        "status": "RUNNING",
        "agent_1_status": "IDLE",
        "agent_2_status": "IDLE",
        "agent_3_status": "IDLE",
        "tokens_used": 0,
        "expires_at": int(time.time()) + (7 * 86400),  # TTL: 7 days
    })

    # Invoke this Lambda asynchronously to run the pipeline
    lambda_client = boto3.client("lambda", region_name=AWS_REGION)
    lambda_client.invoke(
        FunctionName=os.environ.get("AWS_LAMBDA_FUNCTION_NAME", "heatwave-dev-backend"),
        InvocationType="Event",  # async — returns immediately
        Payload=json.dumps({"pipeline_run": run_id}),
    )

    return {"run_id": run_id, "status": "RUNNING", "created_at": now}


@app.get("/api/v1/runs/{run_id}/status")
def run_status(run_id: str):
    """Poll pipeline status."""
    table = _get_table()
    response = table.get_item(Key={"run_id": run_id})
    item = response.get("Item")

    if not item:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    return {
        "run_id": run_id,
        "status": item.get("status", "UNKNOWN"),
        "agent_1_status": item.get("agent_1_status", "IDLE"),
        "agent_2_status": item.get("agent_2_status", "IDLE"),
        "agent_3_status": item.get("agent_3_status", "IDLE"),
        "tokens_used": item.get("tokens_used", 0),
        "duration_ms": item.get("duration_ms"),
        "error_message": item.get("error_message"),
        "created_at": item.get("created_at"),
    }


@app.get("/api/v1/runs/{run_id}/result")
def run_result(run_id: str):
    """Fetch final results (threat map + dispatch plan)."""
    table = _get_table()
    response = table.get_item(Key={"run_id": run_id})
    item = response.get("Item")

    if not item:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    if item.get("status") != "COMPLETE":
        raise HTTPException(
            status_code=409,
            detail=f"Run {run_id} is {item.get('status', 'UNKNOWN')} — not yet complete",
        )

    s3 = _get_s3()
    result = {"run_id": run_id}

    # Load each agent's output from S3
    for key_field, result_field in [
        ("hex_events_key", "hex_events"),
        ("threat_map_key", "threat_map"),
        ("dispatch_plan_key", "dispatch_plan"),
    ]:
        s3_key = item.get(key_field)
        if s3_key:
            try:
                obj = s3.get_object(Bucket=DATA_BUCKET, Key=s3_key)
                result[result_field] = json.loads(obj["Body"].read())
            except Exception as e:
                logger.error("Failed to load %s: %s", s3_key, e)
                result[result_field] = {"error": str(e)}

    result["tokens_used"] = item.get("tokens_used", 0)
    result["duration_ms"] = item.get("duration_ms")

    return result


@app.get("/api/v1/runs")
def list_runs():
    """List recent pipeline runs."""
    table = _get_table()
    response = table.scan(
        Limit=20,
        ProjectionExpression="run_id, #st, created_at, tokens_used, duration_ms",
        ExpressionAttributeNames={"#st": "status"},
    )

    runs = sorted(
        response.get("Items", []),
        key=lambda x: x.get("created_at", ""),
        reverse=True,
    )

    return {"runs": runs}


# ---------------------------------------------------------------------------
# Lambda entry point
# ---------------------------------------------------------------------------

_mangum = Mangum(app)


def handler(event, context):
    """Lambda entry point. Routes between API Gateway requests and async pipeline runs.

    - API Gateway events → Mangum → FastAPI
    - Async pipeline events (from self-invocation) → _run_pipeline directly
    """
    # Check if this is an async pipeline invocation
    if isinstance(event, dict) and "pipeline_run" in event:
        run_id = event["pipeline_run"]
        logger.info("Async pipeline invocation for run_id: %s", run_id)
        _run_pipeline(run_id)
        return {"statusCode": 200, "body": json.dumps({"run_id": run_id, "status": "complete"})}

    # Otherwise, route through Mangum/FastAPI
    return _mangum(event, context)
