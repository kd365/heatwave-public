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

resource "aws_iam_openid_connect_provider" "github_actions" {
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
  thumbprint_list = [
    "6938fd4d98bab03faadb97b34396831e3780aea1",
    "1c58a3a8518e8759bf075b76b750d4f2df264fcd",
  ]
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

  # Direct model invocation (orchestration layer calls Claude directly)
  statement {
    sid     = "InvokeBedrockModel"
    effect  = "Allow"
    actions = ["bedrock:InvokeModel"]
    resources = [
      "arn:aws:bedrock:${var.aws_region}::foundation-model/${var.bedrock_model_id}",
    ]
  }

  # Read raw data and RAG docs; results prefix excluded from reads
  statement {
    sid     = "ReadS3Data"
    effect  = "Allow"
    actions = ["s3:GetObject"]
    resources = [
      "${aws_s3_bucket.data.arn}/raw/*",
      "${aws_s3_bucket.data.arn}/rag/*",
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
    ]
    resources = [
      "arn:aws:dynamodb:${var.aws_region}:${var.account_id}:table/${local.prefix}-pipeline-runs",
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
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github_actions.arn]
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
  name               = "${local.prefix}-github-actions"
  assume_role_policy = data.aws_iam_policy_document.github_actions_trust.json
}

data "aws_iam_policy_document" "github_actions_permissions" {
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
      aws_iam_role.lambda_exec.arn,
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
  name   = "deploy-permissions"
  role   = aws_iam_role.github_actions.id
  policy = data.aws_iam_policy_document.github_actions_permissions.json
}
