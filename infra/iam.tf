# ── IAM — Roles & Policies ───────────────────────────────────────────────────
# Three roles, zero trust / least-privilege. No wildcard actions.
#
# 1. bedrock_agent_role  — assumed by Amazon Bedrock to invoke models + KB
# 2. lambda_exec_role    — assumed by Lambda to call Bedrock, S3, DynamoDB, CW
# 3. github_actions_role — assumed by GitHub Actions via OIDC (no static keys)

# ── GitHub Actions OIDC Provider ────────────────────────────────────────────
# These are GitHub's published thumbprints for token.actions.githubusercontent.com.
# AWS validates the OIDC JWT against its own CA trust store at runtime;
# the thumbprint field is still required by the resource.

# Requires iam:CreateOpenIDConnectProvider — set create_github_oidc_provider=true
# when running as an IAM admin (e.g. bootstrap role). Skip-able; OIDC can be
# created manually via the console then imported: terraform import
#   aws_iam_openid_connect_provider.github_actions <arn>
resource "aws_iam_openid_connect_provider" "github_actions" {
  count          = var.create_github_oidc_provider ? 1 : 0
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
  thumbprint_list = [
    "6938fd4d98bab03faadb97b34396831e3780aea1",
    "1c58a3a8518e8759bf075b76b750d4f2df264fcd",
  ]
}

# ── Deploying User — AOSS data plane access ─────────────────────────────────
# AOSS requires both an IAM identity-based permission (aoss:APIAccessAll) AND
# an entry in the collection's data access policy. The data access policy alone
# is not sufficient for the data plane OpenSearch REST API.
# This policy lets the Nick IAM user create the heatwave-rag-index manually
# before running terraform apply for the Knowledge Base.
resource "aws_iam_user_policy" "dev_aoss" {
  name = "aoss-dev-data-access"
  user = "kathleen_dev"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid      = "AOSSDataPlane"
      Effect   = "Allow"
      Action   = ["aoss:APIAccessAll"]
      Resource = [aws_opensearchserverless_collection.kb.arn]
    }]
  })
}

# ── Role 1: Bedrock Agent Execution ─────────────────────────────────────────

data "aws_iam_policy_document" "bedrock_agent_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["bedrock.amazonaws.com"]
    }

    # Prevent confused deputy — only our account can trigger this assumption
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [var.account_id]
    }
  }
}

resource "aws_iam_role" "bedrock_agent" {
  name               = "${local.prefix}-bedrock-agent"
  assume_role_policy = data.aws_iam_policy_document.bedrock_agent_trust.json
}

data "aws_iam_policy_document" "bedrock_agent_permissions" {
  statement {
    sid     = "InvokeModel"
    effect  = "Allow"
    actions = ["bedrock:InvokeModel"]
    resources = [
      "arn:aws:bedrock:${var.aws_region}::foundation-model/${var.bedrock_model_id}",
    ]
  }

  # Knowledge Base ID is unknown until Phase 3 — scoped to this account only
  statement {
    sid     = "RetrieveFromKnowledgeBase"
    effect  = "Allow"
    actions = ["bedrock:Retrieve"]
    resources = [
      "arn:aws:bedrock:${var.aws_region}:${var.account_id}:knowledge-base/*",
    ]
  }

  statement {
    sid     = "ReadRagDocs"
    effect  = "Allow"
    actions = ["s3:GetObject"]
    resources = [
      "${aws_s3_bucket.data.arn}/rag/*",
    ]
  }

  statement {
    sid    = "WriteAgentLogs"
    effect = "Allow"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = [
      "arn:aws:logs:${var.aws_region}:${var.account_id}:log-group:${local.prefix}-agent-*:*",
    ]
  }
}

resource "aws_iam_role_policy" "bedrock_agent" {
  name   = "permissions"
  role   = aws_iam_role.bedrock_agent.id
  policy = data.aws_iam_policy_document.bedrock_agent_permissions.json
}

# ── Role 2: Lambda Execution ─────────────────────────────────────────────────

data "aws_iam_policy_document" "lambda_exec_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda_exec" {
  name               = "${local.prefix}-lambda-exec"
  assume_role_policy = data.aws_iam_policy_document.lambda_exec_trust.json
}

data "aws_iam_policy_document" "lambda_exec_permissions" {
  # Invoke deployed Bedrock agents (agent IDs assigned at KB creation time)
  statement {
    sid     = "InvokeBedrockAgents"
    effect  = "Allow"
    actions = ["bedrock:InvokeAgent"]
    resources = [
      "arn:aws:bedrock:${var.aws_region}:${var.account_id}:agent-alias/*",
    ]
  }

  # Retrieve from Knowledge Base (Agent 2 RAG queries)
  statement {
    sid     = "RetrieveFromKnowledgeBase"
    effect  = "Allow"
    actions = ["bedrock:Retrieve"]
    resources = [
      "arn:aws:bedrock:${var.aws_region}:${var.account_id}:knowledge-base/*",
    ]
  }

  # Direct model invocation (orchestration layer calls Claude directly)
  # Covers both foundation models and cross-region inference profiles
  statement {
    sid     = "InvokeBedrockModel"
    effect  = "Allow"
    actions = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream", "bedrock:Converse", "bedrock:ApplyGuardrail"]
    resources = [
      "arn:aws:bedrock:*::foundation-model/*",
      "arn:aws:bedrock:*:${var.account_id}:inference-profile/*",
      "arn:aws:bedrock:us:${var.account_id}:inference-profile/*",
      "arn:aws:bedrock:${var.aws_region}:${var.account_id}:guardrail/*",
    ]
  }

  # Read raw data, synthetic data, and RAG docs; results prefix excluded from reads
  statement {
    sid     = "ReadS3Data"
    effect  = "Allow"
    actions = ["s3:GetObject"]
    resources = [
      "${aws_s3_bucket.data.arn}/raw/*",
      "${aws_s3_bucket.data.arn}/rag/*",
      "${aws_s3_bucket.data.arn}/synthetic/*",
      "${aws_s3_bucket.data.arn}/results/*",
    ]
  }

  # Pipeline outputs (HexEvents, ThreatMaps, DispatchPlans) per run_id
  statement {
    sid     = "WriteS3Results"
    effect  = "Allow"
    actions = ["s3:PutObject"]
    resources = [
      "${aws_s3_bucket.data.arn}/results/*",
    ]
  }

  # Pipeline run state — keyed by run_id (table created in dynamodb.tf)
  statement {
    sid    = "PipelineStateTable"
    effect = "Allow"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:Query",
      "dynamodb:Scan",
    ]
    resources = [
      "arn:aws:dynamodb:${var.aws_region}:${var.account_id}:table/${local.prefix}-pipeline-runs",
    ]
  }

  # Lambda self-invoke (async pipeline — handler invokes itself with InvocationType=Event)
  statement {
    sid     = "SelfInvokeLambda"
    effect  = "Allow"
    actions = ["lambda:InvokeFunction"]
    resources = [
      "arn:aws:lambda:${var.aws_region}:${var.account_id}:function:${local.prefix}-backend",
    ]
  }

  # Lambda execution logs (both /aws/lambda/ default group and named group)
  statement {
    sid    = "WriteLambdaLogs"
    effect = "Allow"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = [
      "arn:aws:logs:${var.aws_region}:${var.account_id}:log-group:/aws/lambda/${local.prefix}-backend:*",
      "arn:aws:logs:${var.aws_region}:${var.account_id}:log-group:${local.prefix}-backend:*",
    ]
  }
}

resource "aws_iam_role_policy" "lambda_exec" {
  name   = "permissions"
  role   = aws_iam_role.lambda_exec.id
  policy = data.aws_iam_policy_document.lambda_exec_permissions.json
}

# ── Role 3: GitHub Actions OIDC ─────────────────────────────────────────────

data "aws_iam_policy_document" "github_actions_trust" {
  count = var.create_github_oidc_provider ? 1 : 0

  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github_actions[0].arn]
    }

    # Scope to this exact repo — wildcard allows any branch/tag/PR
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_org}/${var.github_repo}:*"]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "github_actions" {
  count              = var.create_github_oidc_provider ? 1 : 0
  name               = "${local.prefix}-github-actions"
  assume_role_policy = data.aws_iam_policy_document.github_actions_trust[0].json
}

data "aws_iam_policy_document" "github_actions_permissions" {
  count = var.create_github_oidc_provider ? 1 : 0

  # Backend Lambda deploy — scoped to the single function by name
  statement {
    sid    = "DeployBackendLambda"
    effect = "Allow"
    actions = [
      "lambda:UpdateFunctionCode",
      "lambda:UpdateFunctionConfiguration",
      "lambda:GetFunction",
      "lambda:PublishVersion",
    ]
    resources = [
      "arn:aws:lambda:${var.aws_region}:${var.account_id}:function:${local.prefix}-backend",
    ]
  }

  # PassRole is required so Lambda can still assume its exec role after redeployment
  statement {
    sid     = "PassLambdaExecRole"
    effect  = "Allow"
    actions = ["iam:PassRole"]
    resources = [
      aws_iam_role.lambda_exec.arn, # lambda_exec has count=0 guard removed — always created
    ]
  }

  # Frontend static assets — bucket created in cloudfront.tf (Phase 2 optional)
  statement {
    sid    = "DeployFrontendFiles"
    effect = "Allow"
    actions = [
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:GetObject",
    ]
    resources = [
      "arn:aws:s3:::${local.prefix}-frontend-${var.account_id}/*",
    ]
  }

  statement {
    sid       = "ListFrontendBucket"
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = ["arn:aws:s3:::${local.prefix}-frontend-${var.account_id}"]
  }

  # CloudFront cache invalidation after frontend sync
  statement {
    sid     = "InvalidateCloudFront"
    effect  = "Allow"
    actions = ["cloudfront:CreateInvalidation"]
    resources = [
      "arn:aws:cloudfront::${var.account_id}:distribution/*",
    ]
  }
}

resource "aws_iam_role_policy" "github_actions" {
  count  = var.create_github_oidc_provider ? 1 : 0
  name   = "deploy-permissions"
  role   = aws_iam_role.github_actions[0].id
  policy = data.aws_iam_policy_document.github_actions_permissions[0].json
}
