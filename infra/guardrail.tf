# ── Bedrock Guardrail ─────────────────────────────────────────────────────────
# Applied to Agent 2 (Threat Assessment) — the only agent that produces
# clinical/medical recommendations from RAG documents.
#
# Three layers:
# 1. Content filters  — block harmful/violent content generation
# 2. Topic denial     — deny requests for specific medical prescriptions or
#                       clinical treatment decisions (out of scope)
# 3. Grounding check  — reject responses not grounded in retrieved source docs
#                       (hallucination guard on RAG output)

resource "aws_bedrock_guardrail" "agent2" {
  name                      = "${local.prefix}-agent2-guardrail"
  blocked_input_messaging   = "This request cannot be processed."
  blocked_outputs_messaging = "The response was blocked by safety filters."

  # ── Content Filters ────────────────────────────────────────────────────────
  content_policy_config {
    filters_config {
      type            = "HATE"
      input_strength  = "HIGH"
      output_strength = "HIGH"
    }
    filters_config {
      type            = "VIOLENCE"
      input_strength  = "HIGH"
      output_strength = "HIGH"
    }
    filters_config {
      type            = "SEXUAL"
      input_strength  = "HIGH"
      output_strength = "HIGH"
    }
    filters_config {
      type            = "INSULTS"
      input_strength  = "MEDIUM"
      output_strength = "MEDIUM"
    }
  }

  # ── Topic Denial ───────────────────────────────────────────────────────────
  # Prevent the model from acting as a clinical decision-maker or prescribing
  # specific medical treatments — it should only surface risk thresholds from
  # the RAG docs, not tell responders what medications to administer.
  topic_policy_config {
    topics_config {
      name       = "ClinicalTreatmentAdvice"
      type       = "DENY"
      definition = "Requests for specific medical treatment, medication dosages, or clinical interventions for individual patients."
      examples = [
        "What IV fluids should I administer to this patient?",
        "Should I give epinephrine to this heat stroke victim?",
      ]
    }
  }

  # ── Grounding (Hallucination Guard) ──────────────────────────────────────
  # Rejects responses where the model's claims are not supported by the
  # retrieved RAG source text. Threshold 0.75 = moderately strict.
  contextual_grounding_policy_config {
    filters_config {
      type      = "GROUNDING"
      threshold = 0.75
    }
    filters_config {
      type      = "RELEVANCE"
      threshold = 0.75
    }
  }

  tags = {
    Project     = var.project
    Environment = var.environment
  }
}

resource "aws_bedrock_guardrail_version" "agent2" {
  guardrail_arn = aws_bedrock_guardrail.agent2.guardrail_arn
  description   = "Production version for Agent 2 threat assessment"
}
