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
  description = "Bedrock model ID for the agents"
  type        = string
  default     = "anthropic.claude-3-5-sonnet-20241022-v2:0"
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
