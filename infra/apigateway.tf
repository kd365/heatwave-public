# ── API Gateway — HTTP API (v2) ───────────────────────────────────────────────
# HTTP API is cheaper and lower-latency than REST API for this use case.
# All routes proxy to the Lambda — FastAPI/Mangum handles internal routing.
#
# CORS: allow-origin is set to * for now. Once CloudFront is provisioned (Phase 2
# optional) this should be tightened to the CloudFront domain.

resource "aws_apigatewayv2_api" "heatwave" {
  name          = "${local.prefix}-api"
  protocol_type = "HTTP"

  cors_configuration {
    allow_origins = ["*"]
    allow_methods = ["GET", "POST", "OPTIONS"]
    allow_headers = ["Content-Type", "Authorization"]
    max_age       = 300
  }
}

# ── Lambda integration ───────────────────────────────────────────────────────

resource "aws_apigatewayv2_integration" "lambda" {
  api_id             = aws_apigatewayv2_api.heatwave.id
  integration_type   = "AWS_PROXY"
  integration_uri    = aws_lambda_function.backend.invoke_arn
  integration_method = "POST"

  payload_format_version = "2.0"
}

# ── Routes ───────────────────────────────────────────────────────────────────

resource "aws_apigatewayv2_route" "health" {
  api_id    = aws_apigatewayv2_api.heatwave.id
  route_key = "GET /health"
  target    = "integrations/${aws_apigatewayv2_integration.lambda.id}"
}

resource "aws_apigatewayv2_route" "analyze" {
  api_id    = aws_apigatewayv2_api.heatwave.id
  route_key = "POST /api/v1/analyze"
  target    = "integrations/${aws_apigatewayv2_integration.lambda.id}"
}

resource "aws_apigatewayv2_route" "run_status" {
  api_id    = aws_apigatewayv2_api.heatwave.id
  route_key = "GET /api/v1/runs/{run_id}/status"
  target    = "integrations/${aws_apigatewayv2_integration.lambda.id}"
}

resource "aws_apigatewayv2_route" "run_result" {
  api_id    = aws_apigatewayv2_api.heatwave.id
  route_key = "GET /api/v1/runs/{run_id}/result"
  target    = "integrations/${aws_apigatewayv2_integration.lambda.id}"
}

resource "aws_apigatewayv2_route" "runs_list" {
  api_id    = aws_apigatewayv2_api.heatwave.id
  route_key = "GET /api/v1/runs"
  target    = "integrations/${aws_apigatewayv2_integration.lambda.id}"
}

# ── Stage ────────────────────────────────────────────────────────────────────

resource "aws_cloudwatch_log_group" "api_gateway" {
  name              = "/aws/apigateway/${local.prefix}"
  retention_in_days = 7
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.heatwave.id
  name        = "$default"
  auto_deploy = true

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api_gateway.arn
    format = jsonencode({
      requestId      = "$context.requestId"
      sourceIp       = "$context.identity.sourceIp"
      routeKey       = "$context.routeKey"
      status         = "$context.status"
      responseLength = "$context.responseLength"
      durationMs     = "$context.responseLatency"
    })
  }
}

# ── Permission — allow API Gateway to invoke Lambda ──────────────────────────

resource "aws_lambda_permission" "api_gateway" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.backend.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.heatwave.execution_arn}/*/*"
}
