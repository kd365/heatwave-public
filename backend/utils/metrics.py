"""Embedded Metric Format (EMF) emitter for CloudWatch custom metrics.

EMF works by printing a specially structured JSON line to stdout/stderr.
Lambda's log agent picks it up and publishes the metrics to CloudWatch
without any PutMetricData API calls.

Usage:
    from backend.utils.metrics import emit_agent_metrics, emit_pipeline_metrics

    emit_agent_metrics("agent1_triage", run_id=run_id, duration_ms=12345, tokens_used=50000)
    emit_pipeline_metrics(run_id=run_id, duration_ms=552315, tokens_used=878788, success=True)

Metrics published under namespace "HeatwavePipeline":
    AgentDurationMs   — dimension: agent
    AgentTokensUsed   — dimension: agent
    PipelineDurationMs
    PipelineTokensUsed
    PipelineError     — 1 on failure, 0 on success
"""

import json
import time


def emit_agent_metrics(agent: str, *, run_id: str, duration_ms: int, tokens_used: int) -> None:
    """Emit per-agent duration and token metrics via EMF."""
    payload = {
        "_aws": {
            "Timestamp": int(time.time() * 1000),
            "CloudWatchMetrics": [
                {
                    "Namespace": "HeatwavePipeline",
                    "Dimensions": [["agent"]],
                    "Metrics": [
                        {"Name": "AgentDurationMs", "Unit": "Milliseconds"},
                        {"Name": "AgentTokensUsed", "Unit": "Count"},
                    ],
                }
            ],
        },
        "agent": agent,
        "run_id": run_id,
        "AgentDurationMs": duration_ms,
        "AgentTokensUsed": tokens_used,
    }
    print(json.dumps(payload), flush=True)


def emit_pipeline_metrics(*, run_id: str, duration_ms: int, tokens_used: int, success: bool) -> None:
    """Emit pipeline-level completion metrics via EMF."""
    payload = {
        "_aws": {
            "Timestamp": int(time.time() * 1000),
            "CloudWatchMetrics": [
                {
                    "Namespace": "HeatwavePipeline",
                    "Dimensions": [[]],
                    "Metrics": [
                        {"Name": "PipelineDurationMs", "Unit": "Milliseconds"},
                        {"Name": "PipelineTokensUsed", "Unit": "Count"},
                        {"Name": "PipelineError",      "Unit": "Count"},
                    ],
                }
            ],
        },
        "run_id": run_id,
        "PipelineDurationMs": duration_ms,
        "PipelineTokensUsed": tokens_used,
        "PipelineError": 0 if success else 1,
    }
    print(json.dumps(payload), flush=True)
