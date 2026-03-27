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
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum

from backend.agents import agent1_triage, agent2_threat, agent3_dispatch
from backend.utils.logging_config import configure_logging
from backend.utils.metrics import emit_agent_metrics, emit_pipeline_metrics

configure_logging()
logger = logging.getLogger(__name__)

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

def _check_cancelled(run_id: str) -> bool:
    """Check if a run has been cancelled via the API."""
    table = _get_table()
    response = table.get_item(Key={"run_id": run_id}, ProjectionExpression="#st", ExpressionAttributeNames={"#st": "status"})
    return response.get("Item", {}).get("status") == "CANCELLED"


class PipelineCancelled(Exception):
    pass


def _run_pipeline(run_id: str, target_date: str = None):
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

        agent1_result = agent1_triage.run(run_id=run_id, target_date=target_date)
        a1_tokens = agent1_result.get("tokens_used", 0)
        a1_duration_ms = int((time.time() - start_time) * 1000)
        total_tokens += a1_tokens
        emit_agent_metrics("agent1_triage", run_id=run_id, duration_ms=a1_duration_ms, tokens_used=a1_tokens)

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
        logger.info("Cooling down 60s between Agent 1 and Agent 2...", extra={"run_id": run_id, "event": "agent.cooldown", "after_agent": 1})
        time.sleep(60)

        if _check_cancelled(run_id):
            raise PipelineCancelled(f"Run {run_id} was cancelled")

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
        a2_tokens = agent2_result.get("tokens_used", 0)
        a2_duration_ms = int((time.time() - start_time) * 1000) - a1_duration_ms - 60000
        total_tokens += a2_tokens
        emit_agent_metrics("agent2_threat", run_id=run_id, duration_ms=a2_duration_ms, tokens_used=a2_tokens)

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
        logger.info("Cooling down 60s between Agent 2 and Agent 3...", extra={"run_id": run_id, "event": "agent.cooldown", "after_agent": 2})
        time.sleep(60)

        if _check_cancelled(run_id):
            raise PipelineCancelled(f"Run {run_id} was cancelled")

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
        a3_tokens = agent3_result.get("tokens_used", 0)
        a3_duration_ms = int((time.time() - start_time) * 1000) - a1_duration_ms - a2_duration_ms - 120000
        total_tokens += a3_tokens
        emit_agent_metrics("agent3_dispatch", run_id=run_id, duration_ms=a3_duration_ms, tokens_used=a3_tokens)

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
            "pipeline.complete",
            extra={
                "event": "pipeline.complete",
                "run_id": run_id,
                "duration_ms": duration_ms,
                "tokens_used": total_tokens,
            },
        )
        emit_pipeline_metrics(run_id=run_id, duration_ms=duration_ms, tokens_used=total_tokens, success=True)

    except PipelineCancelled:
        logger.info("pipeline.cancelled", extra={"event": "pipeline.cancelled", "run_id": run_id})
        duration_ms = int((time.time() - start_time) * 1000)
        table.update_item(
            Key={"run_id": run_id},
            UpdateExpression="SET #st = :s, error_message = :e, duration_ms = :d, tokens_used = :t",
            ExpressionAttributeNames={"#st": "status"},
            ExpressionAttributeValues={
                ":s": "CANCELLED",
                ":e": "Cancelled by user",
                ":d": duration_ms,
                ":t": total_tokens,
            },
        )
        emit_pipeline_metrics(run_id=run_id, duration_ms=duration_ms, tokens_used=total_tokens, success=False)

    except Exception as e:
        logger.error(
            "pipeline.error",
            extra={"event": "pipeline.error", "run_id": run_id, "error": str(e)},
            exc_info=True,
        )
        emit_pipeline_metrics(run_id=run_id, duration_ms=int((time.time() - start_time) * 1000), tokens_used=total_tokens, success=False)
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
def analyze(target_date: str = "2023-08-18"):
    """Trigger the 3-agent pipeline for a specific day. Returns run_id immediately.

    Args:
        target_date: Date to analyze (YYYY-MM-DD). Defaults to Aug 18 (peak day, 109.3F).
    """
    run_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    # Create initial run record
    table = _get_table()
    table.put_item(Item={
        "run_id": run_id,
        "created_at": now,
        "status": "RUNNING",
        "target_date": target_date or "all",
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
        Payload=json.dumps({"pipeline_run": run_id, "target_date": target_date}),
    )

    return {"run_id": run_id, "status": "RUNNING", "created_at": now, "target_date": target_date or "all"}


@app.post("/api/v1/runs/{run_id}/cancel")
def cancel_run(run_id: str):
    """Cancel a running pipeline. Takes effect at the next agent boundary."""
    table = _get_table()
    response = table.get_item(Key={"run_id": run_id})
    item = response.get("Item")

    if not item:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    if item.get("status") != "RUNNING":
        raise HTTPException(status_code=409, detail=f"Run {run_id} is {item.get('status')} — can only cancel RUNNING runs")

    table.update_item(
        Key={"run_id": run_id},
        UpdateExpression="SET #st = :s",
        ExpressionAttributeNames={"#st": "status"},
        ExpressionAttributeValues={":s": "CANCELLED"},
    )

    return {"run_id": run_id, "status": "CANCELLED", "detail": "Cancellation requested — will stop at next agent boundary"}


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
        ProjectionExpression="run_id, #st, created_at, tokens_used, duration_ms, target_date, error_message",
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
        target_date = event.get("target_date")
        logger.info(
            "pipeline.start",
            extra={"event": "pipeline.start", "run_id": run_id, "target_date": target_date},
        )
        _run_pipeline(run_id, target_date=target_date)
        return {"statusCode": 200, "body": json.dumps({"run_id": run_id, "status": "complete"})}

    # Otherwise, route through Mangum/FastAPI
    return _mangum(event, context)
