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
  value       = var.create_github_oidc_provider ? aws_iam_role.github_actions[0].arn : "not created — set create_github_oidc_provider=true as IAM admin"
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

# ── Bedrock ───────────────────────────────────────────────────────────────────

output "knowledge_base_id" {
  description = "Bedrock Knowledge Base ID — used by agents for Retrieve calls"
  value       = aws_bedrockagent_knowledge_base.heatwave.id
}

output "knowledge_base_data_source_id" {
  description = "Bedrock KB data source ID — used to trigger ingestion sync"
  value       = aws_bedrockagent_data_source.rag_docs.data_source_id
}

output "opensearch_collection_endpoint" {
  description = "OpenSearch Serverless collection endpoint (for debugging)"
  value       = aws_opensearchserverless_collection.kb.collection_endpoint
}

# ── Lambda + API Gateway ──────────────────────────────────────────────────────

output "api_gateway_url" {
  description = "Base URL for the API — set as VITE_API_BASE_URL in the frontend"
  value       = aws_apigatewayv2_stage.default.invoke_url
}

output "lambda_function_name" {
  description = "Lambda function name — used by deploy-backend.yml for UpdateFunctionCode"
  value       = aws_lambda_function.backend.function_name
}

# ── Frontend (S3 + CloudFront) ────────────────────────────────────────────────

output "frontend_bucket_name" {
  description = "S3 bucket for frontend static assets — used by deploy-frontend.yml"
  value       = aws_s3_bucket.frontend.id
}

output "frontend_url" {
  description = "CloudFront HTTPS URL for the frontend — open this in the browser"
  value       = "https://${aws_cloudfront_distribution.frontend.domain_name}"
}

output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID — used by deploy-frontend.yml for cache invalidation"
  value       = aws_cloudfront_distribution.frontend.id
}

# ── Guardrail ─────────────────────────────────────────────────────────────────

output "guardrail_id" {
  description = "Bedrock Guardrail ID for Agent 2 — set as BEDROCK_GUARDRAIL_ID env var"
  value       = aws_bedrock_guardrail.agent2.guardrail_id
}

output "guardrail_version" {
  description = "Bedrock Guardrail version for Agent 2"
  value       = aws_bedrock_guardrail_version.agent2.version
}
