# HEATWAVE

**Autonomous Spatial-Intelligence Platform for Preemptive Emergency Logistics**

> "Closing the action gap in urban heat crises through preemptive, AI-driven resource deployment."

Track 1: The "Chaos" Sector (Public Safety & Crisis)

---

## What It Does

HEATWAVE is a 3-agent AI pipeline that ingests chaotic, multi-source data during a heat wave and produces an optimized emergency dispatch plan — in under 8 minutes, with no human in the loop.

**Scenario:** Dallas, TX — August 2023 heat wave (24 consecutive days above 100F, peak 109.3F on Aug 18)

**Input:** 911 dispatch records, 311 service requests, weather station data, social media posts, census demographics, medical reference documents

**Output:** Interactive threat map with risk-scored hex grid, optimized resource deployment orders, cooling center activations

---

## Architecture

```
                                    Bedrock Knowledge Base
                                    (CDC/NIOSH, OSHA, NWS,
                                     FEMA, UHI Study)
                                           |
                                           | RAG queries
                                           v
 Raw Data ──> Agent 1 ──> Agent 2 ──> Agent 3 ──> Dispatch Plan
              Spatial      Threat      Dispatch
              Triage     Assessment   Commander
```

![Heatwave Architecture](docs/Heatwave%20Architecture.png)

### Agent 1: Spatial Triage
- Ingests 10,000+ records across 4 data sources
- Hybrid approach: deterministic Python for numeric thresholds, LLM for text judgment (911 narratives, social media sarcasm)
- Geocodes all signals to H3 hexagonal grid (resolution 7, ~1.2km neighborhoods)
- Output: 341 hex events with temperature, incident counts, demographic data

### Agent 2: Threat Assessment
- Queries RAG knowledge base for medical heat thresholds (WBGT, heat index)
- Surfaces conflict between NWS and OSHA/NIOSH standards
- Deterministic scoring formula with auto-derived aggravating factors
- Output: Threat map with CRITICAL / HIGH / MEDIUM / LOW per hex

### Agent 3: Dispatch Commander (Autonomous Strategy Selection)
- Reads threat map + 101-asset inventory (real DFR fleet data)
- **Autonomously selects** one of three dispatch strategies:
  1. `optimize_coverage` (PuLP LP) — maximize weighted threat coverage
  2. `optimize_response_time` (greedy nearest) — minimize response time
  3. `optimize_staged_reserve` (split deploy) — deploy + pre-position reserves
- The LLM reasons about the situation and picks the strategy. Never hardcoded.
- Output: Dispatch orders + strategy justification + cooling center activations

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React (Vite + TypeScript), Leaflet, h3-js, TanStack Query |
| Backend | Python, FastAPI, Mangum (Lambda ASGI) |
| AI/ML | AWS Bedrock (Claude Sonnet 4 + Haiku 4.5), Bedrock Knowledge Base |
| Infrastructure | Terraform, Lambda, API Gateway (HTTP), DynamoDB, S3, CloudFront |
| CI/CD | GitHub Actions (lint, test, deploy backend + frontend) |
| Optimization | PuLP (LP solver), greedy nearest, centroid staging |
| Spatial | H3 hexagonal grid (Python h3 + h3-js) |
| Observability | CloudWatch (EMF metrics, dashboard, structured logging) |
| Security | Bedrock Guardrails (content filter, grounding check), IAM least-privilege |

---

## "Pick Five" Compliance

| Requirement | Implementation |
|---|---|
| **Automated CI/CD** | GitHub Actions: CI gate (ruff + pytest + ESLint + vite build), Lambda deploy, S3/CloudFront frontend deploy |
| **Infrastructure as Code** | 13 Terraform files, 47 resources: Lambda, API Gateway, DynamoDB, S3, Bedrock KB, OpenSearch Serverless, CloudFront, IAM, Guardrails |
| **Observability** | CloudWatch EMF metrics (agent duration, tokens, errors), HEATWAVE-Observability dashboard, structured JSON logging, frontend metrics panel |
| **Vector Integration / RAG** | Bedrock Knowledge Base with OpenSearch Serverless, 6 reference docs (CDC/NIOSH, OSHA, NWS, FEMA, DFR, UHI Study), Titan Embed v2 |
| **Security & Governance** | Bedrock Guardrail (topic denial, grounding check at 0.75 threshold), IAM least-privilege (3 roles, zero wildcard actions), S3 encryption + versioning |

---

## DIL Data Standards

| Requirement | Evidence |
|---|---|
| 5+ distinct documents | 12 datasets/documents in `data/manifest.json` |
| 1 dense doc (5+ pages) | CDC NIOSH 2016-106 (192 pages), Dallas UHI Study (83 pages), DFR EMS Report (27 pages) |
| Signal-to-noise | 10 heat MO entries buried in 1,035 911 records; sarcasm/noise in social media; mixed-relevance 311 |
| Conflict scenario | NWS Heat Index vs OSHA/NIOSH WBGT — different risk assessments for identical conditions |

---

## Data Sources

**Real data:**
- Dallas PD 911 dispatch — 1,035 records, Aug 5-27, 2023 (Dallas Open Data)
- Dallas 311 service requests — 4,482 records (homeless encampments, water, animal)
- Hourly weather — 4,608 records from 8 stations across Dallas (Open-Meteo Archive)
- DFR fire stations — 60 stations with coordinates

**Synthetic:**
- Social media posts — 2,400 posts (100/day) with signal, sarcasm, and noise
- Asset inventory — 101 assets typed per NIMS from real DFR fleet data

**Reference (RAG corpus):**
- CDC/NIOSH 2016-106: Heat stress criteria (192 pages)
- OSHA OTM Section 3 Chapter 4: Heat hazard assessment
- NWS Heat Index Safety: Thresholds (conflict document)
- FEMA NIMS Doctrine 2017: Resource typing
- DFR EMS Annual Report 2023: Fleet data
- Dallas Urban Heat Island Study 2017: Neighborhood vulnerability

---

## Project Structure

```
heatwave/
├── .github/workflows/          # CI + deploy pipelines
│   ├── ci.yml                  # PR gate: lint + test
│   ├── deploy-backend.yml      # Lambda package + deploy
│   └── deploy-frontend.yml     # S3 sync + CloudFront invalidation
├── backend/
│   ├── handler.py              # FastAPI + Mangum Lambda entry point
│   ├── agents/
│   │   ├── base.py             # Bedrock client, retry logic, guardrail support
│   │   ├── agent1_triage.py    # Spatial Triage (hybrid deterministic + LLM)
│   │   ├── agent2_threat.py    # Threat Assessment (RAG + deterministic scoring)
│   │   └── agent3_dispatch.py  # Dispatch Commander (autonomous strategy)
│   └── utils/
│       ├── h3_geocoding.py     # H3 hex grid utilities
│       ├── optimization.py     # LP, greedy, staged-reserve solvers
│       ├── metrics.py          # CloudWatch EMF metrics
│       └── logging_config.py   # Structured logging
├── frontend/src/
│   ├── App.tsx                 # Main app, polling, run management
│   ├── api.ts                  # API client (trigger, poll, cancel, fetch)
│   └── components/
│       ├── HexLayer.tsx        # H3 hex grid with threat colors
│       ├── AssetLayer.tsx      # Ambulance/cooling center markers
│       ├── Legend.tsx           # Risk level legend + stats
│       ├── AgentPanel.tsx      # Agent status + observability
│       └── OrdersPanel.tsx     # Dispatch orders table
├── infra/                      # Terraform (13 files, 47 resources)
│   ├── lambda.tf, apigateway.tf, dynamodb.tf, s3.tf
│   ├── bedrock.tf, guardrail.tf, cloudwatch.tf
│   ├── iam.tf, frontend.tf
│   └── main.tf, providers.tf, variables.tf, outputs.tf
├── data/
│   ├── raw/                    # Real Dallas data (911, 311, weather, stations)
│   ├── synthetic/              # Social media, asset inventory
│   ├── reference/              # RAG corpus + census + hex grid
│   └── manifest.json           # DIL compliance index
└── tests/                      # pytest (agents, geocoding, optimization)
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| POST | `/api/v1/analyze?target_date=2023-08-18` | Trigger 3-agent pipeline |
| GET | `/api/v1/runs/{run_id}/status` | Poll agent-level status |
| GET | `/api/v1/runs/{run_id}/result` | Fetch results (hex events, threat map, dispatch plan) |
| GET | `/api/v1/runs` | List recent runs |
| POST | `/api/v1/runs/{run_id}/cancel` | Cancel a running pipeline |

---

## Running Locally

```bash
# Backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
# Set AWS credentials + env vars (see .env.example)
uvicorn backend.handler:app --reload

# Frontend
cd frontend && npm install && npm run dev
```

---

## Team

| Member | Role |
|--------|------|
| Kathleen Hill (kd365) | Data sourcing, synthetic datasets, optimization solver, agent development |
| Nick Czarnick (czarnick89) | Infrastructure (Terraform), CI/CD, frontend, guardrails |
