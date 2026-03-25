#!/usr/bin/env python3
"""
Create the knn vector index in the AOSS collection before Bedrock KB provisioning.

Usage:
    AOSS_ENDPOINT=https://<id>.us-east-1.aoss.amazonaws.com \
    AWS_REGION=us-east-1 \
    venv/bin/python3 infra/scripts/create_aoss_index.py

The AOSS_ENDPOINT can be found with:
    AWS_PAGER="" aws opensearchserverless list-collections \
        --query 'collectionSummaries[?name==`heatwave-dev-kb`].collectionEndpoint' \
        --output text

Requirements: opensearch-py must be installed (it is in requirements.txt).
Note: The deploying IAM user must have:
  1. aoss:APIAccessAll in an IAM identity-based policy (resource: collection ARN)
  2. aoss:CreateIndex in the AOSS collection data access policy
"""
import boto3
import os
import sys

from opensearchpy import AWSV4SignerAuth, OpenSearch, RequestsHttpConnection

INDEX_NAME = "heatwave-rag-index"

endpoint = os.environ.get("AOSS_ENDPOINT", "").rstrip("/")
region = os.environ.get("AWS_REGION", "us-east-1")

if not endpoint:
    print("ERROR: AOSS_ENDPOINT env var is required.", file=sys.stderr)
    sys.exit(1)

credentials = boto3.Session().get_credentials()
auth = AWSV4SignerAuth(credentials, region, "aoss")

client = OpenSearch(
    hosts=[endpoint],
    http_auth=auth,
    use_ssl=True,
    verify_certs=True,
    connection_class=RequestsHttpConnection,
)

if client.indices.exists(index=INDEX_NAME):
    print(f"Index '{INDEX_NAME}' already exists — OK.")
    sys.exit(0)

body = {
    "settings": {
        "index": {
            "knn": True,
            "number_of_shards": 1,
            "number_of_replicas": 0,
        }
    },
    "mappings": {
        "properties": {
            "embedding": {
                "type": "knn_vector",
                "dimension": 1024,
                "method": {
                    "engine": "faiss",
                    "name": "hnsw",
                    "space_type": "l2",
                },
            },
            "text": {"type": "text"},
            "metadata": {"type": "text"},
        }
    },
}

resp = client.indices.create(index=INDEX_NAME, body=body)
print(f"Index '{INDEX_NAME}' created:", resp)

"""
Create the knn vector index in the AOSS collection before Bedrock KB provisioning.

Usage:
    AOSS_ENDPOINT=https://<id>.us-east-1.aoss.amazonaws.com \
    AWS_REGION=us-east-1 \
    venv/bin/python3 infra/scripts/create_aoss_index.py

The AOSS_ENDPOINT can be found with:
    AWS_PAGER="" aws opensearchserverless list-collections \
        --query 'collectionSummaries[?name==`heatwave-dev-kb`].collectionEndpoint' \
        --output text
"""
import boto3
import json
import os
import sys
import urllib.error
import urllib.request

from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

INDEX_NAME = "heatwave-rag-index"

endpoint = os.environ.get("AOSS_ENDPOINT", "").rstrip("/")
region = os.environ.get("AWS_REGION", "us-east-1")

if not endpoint:
    print("ERROR: AOSS_ENDPOINT env var is required.", file=sys.stderr)
    sys.exit(1)

url = f"{endpoint}/{INDEX_NAME}"

body = json.dumps({
    "settings": {
        "index": {
            "knn": True,
            "number_of_shards": 1,
            "number_of_replicas": 0,
        }
    },
    "mappings": {
        "properties": {
            "embedding": {
                "type": "knn_vector",
                "dimension": 1024,
                "method": {
                    "engine": "faiss",
                    "name": "hnsw",
                    "space_type": "l2",
                },
            },
            "text": {"type": "text"},
            "metadata": {"type": "text"},
        }
    },
}).encode("utf-8")

session = boto3.session.Session()
creds = session.get_credentials().get_frozen_credentials()
headers = {
    "Content-Type": "application/json",
    "Content-Length": str(len(body)),
}

req_aws = AWSRequest(method="PUT", url=url, data=body, headers=headers)
SigV4Auth(creds, "aoss", region).add_auth(req_aws)

request = urllib.request.Request(
    url, data=body, headers=dict(req_aws.headers), method="PUT"
)

try:
    resp = urllib.request.urlopen(request)
    print(f"Index '{INDEX_NAME}' created:", resp.read().decode())
except urllib.error.HTTPError as e:
    body_str = e.read().decode()
    if "resource_already_exists_exception" in body_str.lower():
        print(f"Index '{INDEX_NAME}' already exists — OK.")
    else:
        print(f"HTTP {e.code}: {body_str}", file=sys.stderr)
        sys.exit(1)
