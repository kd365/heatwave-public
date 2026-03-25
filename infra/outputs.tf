# Outputs are added here as resources are provisioned in each phase.
# Phase 2 resources will populate: api_gateway_url, s3 bucket names,
# dynamodb_table_name, lambda_function_name, cloudfront_domain, github_actions_role_arn

# ── S3 ───────────────────────────────────────────────────────────────────────

output "data_bucket_name" {
  description = "Name of the operational data S3 bucket"
  value       = aws_s3_bucket.data.id
}

output "data_bucket_arn" {
  description = "ARN of the operational data S3 bucket"
  value       = aws_s3_bucket.data.arn
}

# ── IAM ──────────────────────────────────────────────────────────────────────

output "bedrock_agent_role_arn" {
  description = "ARN of the Bedrock agent execution role"
  value       = aws_iam_role.bedrock_agent.arn
}

output "lambda_exec_role_arn" {
  description = "ARN of the Lambda execution role"
  value       = aws_iam_role.lambda_exec.arn
}

output "github_actions_role_arn" {
  description = "ARN of the GitHub Actions OIDC role — set as GHA secret AWS_ROLE_ARN"
  value       = aws_iam_role.github_actions.arn
}

# ── DynamoDB ─────────────────────────────────────────────────────────────────

output "pipeline_runs_table_name" {
  description = "DynamoDB table name for pipeline run state"
  value       = aws_dynamodb_table.pipeline_runs.name
}

output "pipeline_runs_table_arn" {
  description = "DynamoDB table ARN for pipeline run state"
  value       = aws_dynamodb_table.pipeline_runs.arn
}
