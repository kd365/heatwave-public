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
