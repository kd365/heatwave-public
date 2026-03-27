# ── Lambda — FastAPI Backend ──────────────────────────────────────────────────
# Terraform owns the function configuration; GitHub Actions owns the code.
# On first apply a minimal placeholder is deployed. The deploy-backend workflow
# calls lambda:UpdateFunctionCode to push the real package — Terraform won't
# revert it because filename and source_code_hash are in lifecycle.ignore_changes.

# Placeholder ZIP — a stub handler so Terraform can create the function.
# Replaced on every push to main by .github/workflows/deploy-backend.yml.
data "archive_file" "lambda_placeholder" {
  type        = "zip"
  output_path = "/tmp/${local.prefix}-lambda-placeholder.zip"

  source {
    content  = "def handler(event, context): return {'statusCode': 200, 'body': 'deploying'}"
    filename = "handler.py"
  }
}

# CloudWatch Log Group — created explicitly so Terraform controls retention.
# If Lambda creates it implicitly it persists forever after a destroy.
resource "aws_cloudwatch_log_group" "backend" {
  name              = "/aws/lambda/${local.prefix}-backend"
  retention_in_days = 7
}

resource "aws_lambda_function" "backend" {
  function_name = "${local.prefix}-backend"
  role          = aws_iam_role.lambda_exec.arn

  runtime  = "python3.12"
  handler  = "backend.handler.handler" # mangum: backend/handler.py → handler = Mangum(app)
  filename = data.archive_file.lambda_placeholder.output_path

  memory_size = var.lambda_memory_mb
  timeout     = var.lambda_timeout_sec

  environment {
    variables = {
      DATA_BUCKET          = aws_s3_bucket.data.id
      PIPELINE_TABLE       = aws_dynamodb_table.pipeline_runs.name
      KNOWLEDGE_BASE_ID    = aws_bedrockagent_knowledge_base.heatwave.id
      BEDROCK_MODEL_ID     = var.bedrock_model_id
      BEDROCK_MODEL_LITE        = var.bedrock_model_lite
      BEDROCK_GUARDRAIL_ID      = aws_bedrock_guardrail.agent2.guardrail_id
      BEDROCK_GUARDRAIL_VERSION = aws_bedrock_guardrail_version.agent2.version
      AWS_ACCOUNT_ID            = var.account_id
      POWERTOOLS_LOG_LEVEL = "INFO"
    }
  }

  depends_on = [aws_cloudwatch_log_group.backend]

  # CI/CD owns the code — never let terraform plan revert a real deployment
  lifecycle {
    ignore_changes = [filename, source_code_hash]
  }
}
