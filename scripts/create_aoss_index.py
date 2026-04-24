"""Create the OpenSearch Serverless vector index for the Bedrock Knowledge Base.

Must be run AFTER terraform apply creates the AOSS collection,
and BEFORE the Knowledge Base can be provisioned.

Usage:
    AWS_PROFILE=cyber-risk python scripts/create_aoss_index.py
"""

import boto3
import json
from opensearchpy import OpenSearch, RequestsHttpConnection, AWSV4SignerAuth

# Configuration — update these if your setup differs
PROFILE = "cyber-risk"
REGION = "us-east-1"
INDEX_NAME = "heatwave-rag-index"

# Get the collection endpoint from Terraform output
import subprocess
from pathlib import Path

# Works whether run from project root or infra/ directory
script_dir = Path(__file__).resolve().parent
infra_dir = script_dir.parent / "infra"
if not (infra_dir / "terraform.tfstate").exists():
    infra_dir = Path.cwd()  # fallback: assume we're already in infra/

result = subprocess.run(
    ["terraform", "output", "-raw", "opensearch_collection_endpoint"],
    capture_output=True, text=True, cwd=str(infra_dir)
)
endpoint = result.stdout.strip().replace("https://", "")
print(f"Collection endpoint: {endpoint}")

# Authenticate
session = boto3.Session(profile_name=PROFILE)
credentials = session.get_credentials()
auth = AWSV4SignerAuth(credentials, REGION, "aoss")

client = OpenSearch(
    hosts=[{"host": endpoint, "port": 443}],
    http_auth=auth,
    use_ssl=True,
    verify_certs=True,
    connection_class=RequestsHttpConnection,
    timeout=300,
)

# Create the vector index matching Bedrock KB expectations
index_body = {
    "settings": {
        "index": {
            "knn": True,
        }
    },
    "mappings": {
        "properties": {
            "embedding": {
                "type": "knn_vector",
                "dimension": 1024,  # Titan Embed Text v2
                "method": {
                    "engine": "faiss",
                    "name": "hnsw",
                    "parameters": {},
                    "space_type": "l2",
                },
            },
            "metadata": {
                "type": "text",
                "index": False,
            },
            "text": {
                "type": "text",
            },
        }
    },
}

# Delete existing index if it exists
try:
    client.indices.delete(index=INDEX_NAME)
    print(f"Deleted existing index '{INDEX_NAME}'")
except Exception:
    print(f"No existing index to delete")

response = client.indices.create(index=INDEX_NAME, body=index_body)
print(json.dumps(response, indent=2))
print(f"\nIndex '{INDEX_NAME}' created successfully!")
print("You can now run: terraform apply  (to create the Knowledge Base)")
