#!/bin/bash
# HEATWAVE — Recreate resources destroyed by hibernate.sh
# Takes ~8-10 min (AOSS collection + KB + ingestion)

set -e
cd "$(dirname "$0")/../infra"

echo "=== HEATWAVE Wake Up ==="

# Step 1: First apply — creates AOSS collection (KB will fail, that's OK)
echo "Step 1/6: Creating OpenSearch collection..."
AWS_PROFILE=cyber-risk terraform apply -auto-approve || true

# Step 2: Create vector index
echo "Step 2/6: Creating vector index..."
AWS_PROFILE=cyber-risk python3 ../scripts/create_aoss_index.py

# Step 3: Second apply — KB + Lambda
echo "Step 3/6: Creating Knowledge Base + Lambda..."
AWS_PROFILE=cyber-risk terraform apply -auto-approve

# Step 4: Ingest RAG docs
echo "Step 4/6: Ingesting RAG documents..."
KB_ID=$(terraform output -raw knowledge_base_id)
DS_ID=$(terraform output -raw knowledge_base_data_source_id)
AWS_PROFILE=cyber-risk aws bedrock-agent start-ingestion-job \
  --knowledge-base-id "$KB_ID" \
  --data-source-id "$DS_ID" \
  --region us-east-1

# Step 5: Deploy Lambda code
echo "Step 5/6: Deploying Lambda code..."
if [ -f /tmp/lambda.zip ]; then
  AWS_PROFILE=cyber-risk aws lambda update-function-code \
    --function-name heatwave-dev-backend \
    --zip-file fileb:///tmp/lambda.zip \
    --region us-east-1 > /dev/null
else
  echo "WARNING: /tmp/lambda.zip not found — rebuild with scripts/build-lambda.sh"
fi

# Step 6: Deploy frontend
echo "Step 6/6: Deploying frontend..."
API_URL=$(terraform output -raw api_gateway_url)
FRONTEND_BUCKET=$(terraform output -raw frontend_bucket_name)
CF_DIST=$(terraform output -raw cloudfront_distribution_id)

cd ../frontend
VITE_API_BASE_URL="$API_URL" npm run build
AWS_PROFILE=cyber-risk aws s3 sync dist/ "s3://$FRONTEND_BUCKET/" --delete
AWS_PROFILE=cyber-risk aws cloudfront create-invalidation \
  --distribution-id "$CF_DIST" --paths "/*" > /dev/null

echo ""
echo "=== HEATWAVE is live ==="
echo "Frontend: $(cd ../infra && terraform output -raw frontend_url)"
echo "Note: RAG ingestion takes ~3 min — first run may have limited KB results"
