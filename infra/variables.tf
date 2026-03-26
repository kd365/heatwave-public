variable "aws_region" {
  description = "AWS region for all resources"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Deployment environment"
  type        = string
  default     = "dev"
}

variable "project" {
  description = "Project name prefix for resource naming"
  type        = string
  default     = "heatwave"
}

variable "account_id" {
  description = "AWS account ID"
  type        = string
  default     = "388691194728"
}

variable "github_org" {
  description = "GitHub organization or username (for OIDC trust policy)"
  type        = string
  # Set in terraform.tfvars — do not default here
}

variable "github_repo" {
  description = "GitHub repo name (for OIDC trust policy)"
  type        = string
  # Set in terraform.tfvars — do not default here
}

variable "bedrock_model_id" {
  description = "Bedrock model ID for agents requiring full reasoning (Sonnet)"
  type        = string
  default     = "us.anthropic.claude-sonnet-4-20250514-v1:0"
}

variable "bedrock_model_lite" {
  description = "Bedrock model ID for lightweight orchestration calls (Haiku)"
  type        = string
  default     = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
}

variable "bedrock_embedding_model_id" {
  description = "Bedrock embedding model ID for the Knowledge Base vector store"
  type        = string
  default     = "amazon.titan-embed-text-v2:0"
}

variable "create_github_oidc_provider" {
  description = "Set true to create the GitHub Actions OIDC provider. Requires iam:CreateOpenIDConnectProvider on the deploying principal."
  type        = bool
  default     = false
}

variable "lambda_memory_mb" {
  description = "Lambda function memory in MB"
  type        = number
  default     = 512
}

variable "lambda_timeout_sec" {
  description = "Lambda function timeout in seconds"
  type        = number
  default     = 300
}
