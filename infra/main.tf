# ── HEATWAVE — Core Infrastructure ─────────────────────────────────────────
# Resources are added here phase by phase.
# See ROADMAP.md for what gets added in each phase.
#
# Phase 2 (current): locals block only
# Phase 2 (next):    s3.tf, iam.tf, dynamodb.tf, lambda.tf, cloudwatch.tf
# Phase 3:           bedrock.tf (KB + OpenSearch + Guardrail)

locals {
  prefix = "${var.project}-${var.environment}"
}
