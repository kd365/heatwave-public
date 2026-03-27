# ── CloudWatch — Log Groups ───────────────────────────────────────────────────
# Lambda auto-creates /aws/lambda/<function> on first invocation, but managing
# it here gives us retention control and prevents orphaned log groups.

resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${local.prefix}-backend"
  retention_in_days = 30

  tags = {
    Project     = var.project
    Environment = var.environment
  }
}

# ── CloudWatch — Dashboard ────────────────────────────────────────────────────
# Custom metrics emitted via Embedded Metric Format (EMF) from
# backend/utils/metrics.py — structured JSON logged to CloudWatch Logs that
# Lambda auto-converts to metrics under the "HeatwavePipeline" namespace.
# No PutMetricData API call needed.

resource "aws_cloudwatch_dashboard" "heatwave" {
  dashboard_name = "HEATWAVE-Observability"

  dashboard_body = jsonencode({
    widgets = [
      # ── Pipeline Duration ──────────────────────────────────────────────────
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 12
        height = 6
        properties = {
          title  = "Pipeline Duration (ms)"
          view   = "timeSeries"
          stat   = "Average"
          period = 300
          metrics = [
            ["HeatwavePipeline", "PipelineDurationMs", { label = "Avg Duration", color = "#2196F3" }],
          ]
          region = var.aws_region
        }
      },
      # ── Tokens Used ───────────────────────────────────────────────────────
      {
        type   = "metric"
        x      = 12
        y      = 0
        width  = 12
        height = 6
        properties = {
          title  = "Tokens Used per Run"
          view   = "timeSeries"
          stat   = "Sum"
          period = 300
          metrics = [
            ["HeatwavePipeline", "TokensUsed", { label = "Tokens", color = "#FF9800" }],
          ]
          region = var.aws_region
        }
      },
      # ── Per-Agent Duration ────────────────────────────────────────────────
      {
        type   = "metric"
        x      = 0
        y      = 6
        width  = 12
        height = 6
        properties = {
          title  = "Agent Duration by Agent (ms)"
          view   = "timeSeries"
          stat   = "Average"
          period = 300
          metrics = [
            ["HeatwavePipeline", "AgentDurationMs", "agent", "agent1_triage",   { label = "A1 Triage" }],
            ["HeatwavePipeline", "AgentDurationMs", "agent", "agent2_threat",   { label = "A2 Threat" }],
            ["HeatwavePipeline", "AgentDurationMs", "agent", "agent3_dispatch", { label = "A3 Dispatch" }],
          ]
          region = var.aws_region
        }
      },
      # ── Pipeline Errors ───────────────────────────────────────────────────
      {
        type   = "metric"
        x      = 12
        y      = 6
        width  = 12
        height = 6
        properties = {
          title  = "Pipeline Errors"
          view   = "timeSeries"
          stat   = "Sum"
          period = 300
          metrics = [
            ["HeatwavePipeline", "PipelineError", { label = "Errors", color = "#F44336" }],
          ]
          region = var.aws_region
        }
      },
      # ── Logs Insights: recent completions ────────────────────────────────
      {
        type   = "log"
        x      = 0
        y      = 12
        width  = 24
        height = 6
        properties = {
          title  = "Recent Pipeline Completions"
          region = var.aws_region
          view   = "table"
          query  = "SOURCE '/aws/lambda/heatwave-dev-backend' | fields @timestamp, run_id, duration_ms, tokens_used | filter message = \"pipeline.complete\" | sort @timestamp desc | limit 10"
        }
      },
    ]
  })
}
