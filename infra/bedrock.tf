# ── Bedrock Knowledge Base ───────────────────────────────────────────────────
# Managed vector store backed by OpenSearch Serverless (VECTORSEARCH collection).
# RAG corpus: 6 reference documents under s3://…/rag/
#   - CDC/NIOSH heat stress (192pg)  — dense doc
#   - OSHA heat hazard assessment    — WBGT equations
#   - NWS heat index safety          — conflict doc
#   - FEMA NIMS doctrine             — resource typing
#   - DFR EMS Annual Report 2023     — real fleet data
#   - Dallas UHI Study 2017          — neighbourhood vulnerability
#
# Dependency order enforced by Terraform references:
#   encryption + network policies → collection → KB service role policy → KB → data source

# ── IAM — Bedrock Knowledge Base Service Role ────────────────────────────────
# Separate from the agent execution role.
# Bedrock assumes this to sync S3 → OpenSearch (ingestion) and to embed queries.

data "aws_iam_policy_document" "bedrock_kb_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["bedrock.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [var.account_id]
    }
  }
}

resource "aws_iam_role" "bedrock_kb" {
  name               = "${local.prefix}-bedrock-kb"
  assume_role_policy = data.aws_iam_policy_document.bedrock_kb_trust.json
}

data "aws_iam_policy_document" "bedrock_kb_permissions" {
  # Read the RAG docs from S3
  statement {
    sid    = "ReadRagDocs"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:ListBucket",
    ]
    resources = [
      aws_s3_bucket.data.arn,
      "${aws_s3_bucket.data.arn}/rag/*",
    ]
  }

  # Embed documents using Titan during ingestion and queries
  statement {
    sid     = "EmbedWithTitan"
    effect  = "Allow"
    actions = ["bedrock:InvokeModel"]
    resources = [
      "arn:aws:bedrock:${var.aws_region}::foundation-model/${var.bedrock_embedding_model_id}",
    ]
  }

  # Access the OpenSearch Serverless collection for indexing and retrieval
  statement {
    sid       = "AccessOpenSearchCollection"
    effect    = "Allow"
    actions   = ["aoss:APIAccessAll"]
    resources = [aws_opensearchserverless_collection.kb.arn]
  }
}

resource "aws_iam_role_policy" "bedrock_kb" {
  name   = "permissions"
  role   = aws_iam_role.bedrock_kb.id
  policy = data.aws_iam_policy_document.bedrock_kb_permissions.json
}

# ── OpenSearch Serverless ─────────────────────────────────────────────────────
# All three policy types (encryption, network, data access) must exist before
# the collection can be created.

resource "aws_opensearchserverless_security_policy" "kb_encryption" {
  name = "${local.prefix}-kb"
  type = "encryption"
  policy = jsonencode({
    Rules = [
      {
        ResourceType = "collection"
        Resource     = ["collection/${local.prefix}-kb"]
      }
    ]
    AWSOwnedKey = true
  })
}

resource "aws_opensearchserverless_security_policy" "kb_network" {
  name = "${local.prefix}-kb"
  type = "network"
  policy = jsonencode([
    {
      Rules = [
        {
          ResourceType = "collection"
          Resource     = ["collection/${local.prefix}-kb"]
        },
        {
          ResourceType = "dashboard"
          Resource     = ["collection/${local.prefix}-kb"]
        }
      ]
      # Public endpoint access — Bedrock service calls out to OpenSearch over the
      # internet endpoint. This is safe because access is controlled via IAM (AOSS
      # data access policy) and no sensitive user data flows through this endpoint.
      AllowFromPublic = true
    }
  ])
}

resource "aws_opensearchserverless_access_policy" "kb" {
  name = "${local.prefix}-kb"
  type = "data"
  policy = jsonencode([
    {
      Rules = [
        {
          ResourceType = "index"
          Resource     = ["index/${local.prefix}-kb/*"]
          Permission = [
            "aoss:CreateIndex",
            "aoss:DeleteIndex",
            "aoss:DescribeIndex",
            "aoss:ReadDocument",
            "aoss:WriteDocument",
            "aoss:UpdateIndex",
          ]
        },
        {
          ResourceType = "collection"
          Resource     = ["collection/${local.prefix}-kb"]
          Permission   = ["aoss:DescribeCollectionItems"]
        }
      ]
      # KB service role needs index write access (ingestion + retrieval).
      # Bedrock agent execution role needs read access (Retrieve API calls).
      # Deploying IAM user needs access to pre-create the vector index manually
      # before running terraform apply for the Knowledge Base.
      Principal = [
        aws_iam_role.bedrock_kb.arn,
        aws_iam_role.bedrock_agent.arn,
        "arn:aws:iam::${var.account_id}:user/kathleen_dev",
      ]
    }
  ])
}

resource "aws_opensearchserverless_collection" "kb" {
  name = "${local.prefix}-kb"
  type = "VECTORSEARCH"

  depends_on = [
    aws_opensearchserverless_security_policy.kb_encryption,
    aws_opensearchserverless_security_policy.kb_network,
  ]
}

# Wait for the AOSS collection to reach ACTIVE status and propagate access policies
# before the KB is created — collection must be ACTIVE.
resource "time_sleep" "aoss_active" {
  create_duration = "3m"

  depends_on = [aws_opensearchserverless_collection.kb]
}

# ── Bedrock Knowledge Base ────────────────────────────────────────────────────
# PREREQUISITE: The vector index must be created manually before this resource.
# Run: AOSS_ENDPOINT=<endpoint> AWS_REGION=us-east-1 \
#        venv/bin/python3 infra/scripts/create_aoss_index.py

resource "aws_bedrockagent_knowledge_base" "heatwave" {
  name     = "${local.prefix}-kb"
  role_arn = aws_iam_role.bedrock_kb.arn

  depends_on = [time_sleep.aoss_active]

  knowledge_base_configuration {
    type = "VECTOR"
    vector_knowledge_base_configuration {
      # Titan Embed Text v2 — 1024-dimensional vectors, supports long medical docs
      embedding_model_arn = "arn:aws:bedrock:${var.aws_region}::foundation-model/${var.bedrock_embedding_model_id}"
    }
  }

  storage_configuration {
    type = "OPENSEARCH_SERVERLESS"
    opensearch_serverless_configuration {
      collection_arn    = aws_opensearchserverless_collection.kb.arn
      vector_index_name = "heatwave-rag-index"
      field_mapping {
        vector_field   = "embedding"
        text_field     = "text"
        metadata_field = "metadata"
      }
    }
  }
}

# ── Bedrock Data Source — RAG docs from S3 ───────────────────────────────────

resource "aws_bedrockagent_data_source" "rag_docs" {
  knowledge_base_id = aws_bedrockagent_knowledge_base.heatwave.id
  name              = "rag-reference-docs"

  data_source_configuration {
    type = "S3"
    s3_configuration {
      bucket_arn         = aws_s3_bucket.data.arn
      inclusion_prefixes = ["rag/"]
    }
  }

  # Fixed-size chunking: 512 tokens with 20% overlap.
  # Balances retrieval precision against context density for medical/regulatory docs.
  # The 192-page CDC NIOSH doc benefits most from the overlap — adjacent chunks
  # share context across WBGT threshold tables that span page boundaries.
  vector_ingestion_configuration {
    chunking_configuration {
      chunking_strategy = "FIXED_SIZE"
      fixed_size_chunking_configuration {
        max_tokens         = 512
        overlap_percentage = 20
      }
    }
  }
}
