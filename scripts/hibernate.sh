#!/bin/bash
# HEATWAVE — Destroy expensive resources (OpenSearch ~$350/month)
# Keeps: S3 data, DynamoDB, IAM roles, API Gateway config
# To wake up: ./scripts/wakeup.sh

set -e
cd "$(dirname "$0")/../infra"

echo "=== HEATWAVE Hibernate ==="
echo "Destroying OpenSearch + Knowledge Base + Lambda..."

AWS_PROFILE=cyber-risk terraform destroy \
  -target=aws_bedrockagent_data_source.rag_docs \
  -target=aws_bedrockagent_knowledge_base.heatwave \
  -target=time_sleep.aoss_active \
  -target=aws_opensearchserverless_collection.kb \
  -target=aws_opensearchserverless_access_policy.kb \
  -target=aws_opensearchserverless_security_policy.kb_network \
  -target=aws_opensearchserverless_security_policy.kb_encryption \
  -target=aws_lambda_function.backend \
  -target=aws_bedrock_guardrail_version.agent2 \
  -target=aws_bedrock_guardrail.agent2 \
  -auto-approve

echo ""
echo "=== Hibernated ==="
echo "To wake up: ./scripts/wakeup.sh"
