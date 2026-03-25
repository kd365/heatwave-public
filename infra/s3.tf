# ── S3 — Operational Data Bucket ────────────────────────────────────────────
# Single bucket; logical prefixes separate concerns:
#   raw/        — incoming data files (911, weather, 311, social media)
#   rag/        — reference documents ingested by Bedrock Knowledge Base
#   results/    — pipeline output (HexEvents, ThreatMaps, DispatchPlans)
#
# Account ID suffix guarantees global uniqueness without random suffixes.

resource "aws_s3_bucket" "data" {
  bucket = "${local.prefix}-data-${var.account_id}"
}

resource "aws_s3_bucket_versioning" "data" {
  bucket = aws_s3_bucket.data.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "data" {
  bucket = aws_s3_bucket.data.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "data" {
  bucket = aws_s3_bucket.data.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "data" {
  bucket = aws_s3_bucket.data.id

  rule {
    id     = "expire-old-results"
    status = "Enabled"

    filter {
      prefix = "results/"
    }

    noncurrent_version_expiration {
      noncurrent_days = 30
    }
  }
}
