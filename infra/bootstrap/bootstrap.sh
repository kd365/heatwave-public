#!/usr/bin/env bash
# ============================================================
# HEATWAVE — Terraform Remote State Bootstrap
# Run this ONCE before `terraform init`.
# Creates the S3 bucket and DynamoDB table that Terraform
# will use as its remote backend. These cannot be managed
# by Terraform itself (chicken-and-egg problem).
# ============================================================
set -euo pipefail

AWS_REGION="us-east-1"
ACCOUNT_ID="388691194728"
STATE_BUCKET="heatwave-tf-state-${ACCOUNT_ID}"
LOCK_TABLE="heatwave-tf-locks"

echo "==> Bootstrapping Terraform remote state..."
echo "    Region:       ${AWS_REGION}"
echo "    State bucket: ${STATE_BUCKET}"
echo "    Lock table:   ${LOCK_TABLE}"
echo ""

# --- S3 state bucket ---
if aws s3api head-bucket --bucket "${STATE_BUCKET}" 2>/dev/null; then
  echo "[SKIP] S3 bucket '${STATE_BUCKET}' already exists."
else
  echo "[CREATE] S3 bucket '${STATE_BUCKET}'..."
  aws s3api create-bucket \
    --bucket "${STATE_BUCKET}" \
    --region "${AWS_REGION}"

  # Enable versioning so we can recover from bad state
  aws s3api put-bucket-versioning \
    --bucket "${STATE_BUCKET}" \
    --versioning-configuration Status=Enabled

  # Block all public access
  aws s3api put-public-access-block \
    --bucket "${STATE_BUCKET}" \
    --public-access-block-configuration \
      "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"

  # Enable server-side encryption
  aws s3api put-bucket-encryption \
    --bucket "${STATE_BUCKET}" \
    --server-side-encryption-configuration '{
      "Rules": [{
        "ApplyServerSideEncryptionByDefault": {
          "SSEAlgorithm": "AES256"
        }
      }]
    }'

  echo "[OK] S3 bucket created and secured."
fi

# --- DynamoDB lock table ---
if aws dynamodb describe-table --table-name "${LOCK_TABLE}" --region "${AWS_REGION}" 2>/dev/null | grep -q ACTIVE; then
  echo "[SKIP] DynamoDB table '${LOCK_TABLE}' already exists."
else
  echo "[CREATE] DynamoDB table '${LOCK_TABLE}'..."
  aws dynamodb create-table \
    --table-name "${LOCK_TABLE}" \
    --attribute-definitions AttributeName=LockID,AttributeType=S \
    --key-schema AttributeName=LockID,KeyType=HASH \
    --billing-mode PAY_PER_REQUEST \
    --region "${AWS_REGION}"

  aws dynamodb wait table-exists --table-name "${LOCK_TABLE}" --region "${AWS_REGION}"
  echo "[OK] DynamoDB table created."
fi

echo ""
echo "Bootstrap complete. Now run from the infra/ directory:"
echo "  terraform init"
