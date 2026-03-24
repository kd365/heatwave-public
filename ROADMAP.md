# HEATWAVE — Project Roadmap
**Autonomous Spatial-Intelligence Platform for Preemptive Emergency Logistics**
Track 1: The "Chaos" Sector (Public Safety & Crisis)

> **Presentation:** Saturday @ 4pm
> **Stack:** React (Vite + TS) · Python · FastAPI · AWS Bedrock (Claude Sonnet 3.5) · Lambda · API Gateway · Terraform · GitHub Actions
> **AWS:** Default profile, default VPC, `us-east-1`
> **Map:** Leaflet + H3-js + OpenStreetMap tiles (free, no API key)
> **Social data:** Synthetic (generated)

---

## Legend
- 🔴 Blocking / Critical path
- 🟡 Important but parallelizable
- 🟢 Nice-to-have / polish

---

## Phase 0 — Project Foundation
*Goal: Everyone can run the project locally and push to the shared repo.*

### Repo & Scaffolding
- [X] 🔴 Fork the class repo; add both partners as collaborators
- [X] 🔴 Define branch strategy (e.g., `main` protected, feature branches `feat/*`, `fix/*`)
- [X] 🔴 Create monorepo directory structure:
  ```
  /frontend     (React)
  /backend      (FastAPI)
  /infra        (Terraform)
  /data         (raw source documents & synthetic datasets)
  /agents       (agent prompts & configs)
  .github/      (GitHub Actions workflows)
  ```
- [x] 🔴 Create `.gitignore` (committed)
- [ ] 🟡 Create root `README.md` with project description, setup instructions, and architecture diagram placeholder

### Local Dev Environment
- [X] 🔴 Python virtual environment (`python -m venv .venv`) + `requirements.txt`
- [x] 🔴 Node.js environment for React frontend (`npm init` or `create-react-app` / Vite)
- [ ] 🟡 `Makefile` or `justfile` with common commands (`make dev`, `make test`, `make lint`)
- [ ] 🟡 Pre-commit hooks (Black, isort, ESLint)
- [x] 🔴 `.env.example` with all required environment variable keys (no values)

---

## Phase 1 — Data Sourcing & Validation Set
*Goal: Meet DIL data standards — 5+ docs, 1 dense doc, signal-to-noise, conflict scenario.*

### Technical / Medical Reference Documents (RAG corpus)
- [ ] 🔴 Download **OSHA Heat Illness Prevention** guide (PDF) — dense technical doc (5+ pages)
- [ ] 🔴 Download **CDC Heat Stress** guidelines (PDF or TXT)
- [ ] 🔴 Download or source **heatstroke physiology** clinical reference (e.g., FEMA heat emergency annex, NWS Heat Safety)
- [ ] 🟡 Download a second/conflicting source on heat thresholds (e.g., older OSHA vs. newer NIOSH) — satisfies **conflict scenario** requirement
- [ ] 🟡 Download local municipal emergency operations plan or TDEM heat response protocol

### Operational / Signal Data (synthetic or real)
- [ ] 🔴 Generate or source **synthetic weather JSON dataset** (temp, humidity, heat index, coords, timestamps — 50+ records across a city grid)
- [ ] 🔴 Generate **synthetic 911 call transcripts** (~30–50 entries mixing heat-related, non-heat, and ambiguous calls) — satisfies **signal-to-noise** requirement
- [ ] 🔴 Generate **synthetic social media posts** (~50–100 posts mixing:
  - genuine heat complaints / AC failure reports
  - sarcasm: "oh wow sooo hot today 🙄" (cold day)
  - irrelevant posts
  ) — satisfies **conflict scenario** requirement
- [ ] 🟡 Tag/label a subset of each dataset as ground truth for agent evaluation

### Data Storage
- [ ] 🟡 Store all docs in `/data/` with a `manifest.json` listing source, type, and description
- [ ] 🟡 Upload reference docs to S3 (triggered by Terraform or bootstrap script)

---

## Phase 2 — AWS Infrastructure (Terraform)
*Goal: All cloud resources defined as code; no manual console clicks.*

### Terraform Setup
- [ ] 🔴 Initialize Terraform project in `/infra/` with S3 remote state + DynamoDB lock table
- [ ] 🔴 Define `variables.tf`, `outputs.tf`, `main.tf`, and environment-specific `terraform.tfvars` (do NOT commit real values)
- [ ] 🔴 Configure AWS provider + target region

### Core Infrastructure
- [ ] 🔴 **S3 Buckets**: raw data, processed results, Bedrock Knowledge Base source docs
- [ ] 🔴 **IAM Roles & Policies** — least-privilege for:
  - Bedrock agent execution role
  - Lambda execution role (invoke Bedrock, read/write S3 + DynamoDB)
  - GitHub Actions deploy role (OIDC — no long-lived keys in secrets)
- [ ] 🔴 **Bedrock Knowledge Base** — default managed vector store (Bedrock-managed OpenSearch Serverless), pointing to S3 RAG bucket
- [ ] 🔴 **Lambda function** for FastAPI backend (Lambda Web Adapter or Mangum handler)
- [ ] 🔴 **API Gateway** (HTTP API) in front of Lambda
- [ ] 🔴 **DynamoDB table** for pipeline run state (keyed by `run_id`)
- [ ] 🟡 **CloudWatch Log Groups** for each agent and backend Lambda
- [ ] 🟡 **CloudWatch Dashboard** resource (`HEATWAVE-Observability`)
- [ ] 🟡 **S3 bucket + CloudFront** for React frontend static hosting

### Terraform Plan/Apply
- [ ] 🔴 Confirm `terraform plan` runs clean with no errors
- [ ] 🔴 `terraform apply` to provision dev environment
- [ ] 🟡 Tag all resources with `project=heatwave` and `env=dev`

---

## Phase 3 — Vector DB & RAG Pipeline
*Goal: Threat Assessment Agent can retrieve relevant clinical thresholds from docs.*

- [ ] 🔴 Upload medical/OSHA reference documents to S3 RAG bucket
- [ ] 🔴 Configure and sync **Bedrock Knowledge Base** data source
- [ ] 🔴 Run knowledge base ingestion job; confirm chunks are indexed
- [ ] 🔴 Write a test RAG query: "At what wet-bulb temperature does heatstroke risk become critical for outdoor workers?" — verify relevant docs returned
- [ ] 🟡 Tune chunking strategy (chunk size / overlap) for dense medical text
- [ ] 🟡 Confirm conflict scenario: two docs with different heat thresholds both surface in results

---

## Phase 4 — Agent 1: Spatial Triage Agent
*Goal: Ingest raw chaos, filter signal, geocode onto H3 hex grid.*

### System Prompt & Tool Definition
- [ ] 🔴 Write system prompt: role = "You are a Spatial Triage Analyst. Your job is to ingest raw, unstructured data streams and extract only heat-relevant signals. You must ignore irrelevant noise and sarcasm. You output a structured spatial event list geocoded to H3 hexagons."
- [ ] 🔴 Define agent tools / actions:
  - `get_weather_data(region)` — fetch from S3 / mock API
  - `get_911_transcripts(region, time_window)` — fetch from S3
  - `get_social_media_posts(region, time_window)` — fetch from S3
  - `geocode_to_h3(lat, lon, resolution)` — H3 library call via Lambda

### Implementation
- [ ] 🔴 Implement H3 hexagonal grid geocoding utility (`h3` Python library)
- [ ] 🔴 Implement weather data parser (JSON → structured events)
- [ ] 🔴 Implement 911 transcript parser — classify heat-related vs. noise (LLM-assisted classification)
- [ ] 🔴 Implement social media parser — detect sarcasm / conflict, classify sentiment
- [ ] 🔴 Output schema: list of `HexEvent(hex_id, event_type, severity_score, timestamp, source)`
- [ ] 🟡 Unit test: given synthetic dataset, confirm known heat signals surface and sarcasm is discarded

---

## Phase 5 — Agent 2: Threat Assessment Agent
*Goal: Cross-reference spatial grid against clinical medical knowledge to score each hex.*

### System Prompt & Tool Definition
- [ ] 🔴 Write system prompt: role = "You are a Threat Assessment Analyst with expertise in environmental medicine. Given a spatial event grid, you query the medical knowledge base to determine which hexagonal zones have crossed physiological danger thresholds. Output a threat map with risk levels."
- [ ] 🔴 Define agent tools / actions:
  - `query_knowledge_base(query_text)` — RAG retrieval from Bedrock KB
  - `get_hex_grid(run_id)` — fetch Agent 1 output from DynamoDB/S3
  - `score_hex_threat(hex_id, conditions)` — deterministic scoring function

### Implementation
- [ ] 🔴 Implement RAG query tool wired to Bedrock Knowledge Base
- [ ] 🔴 Implement threat scoring logic (heat index + 911 density + social signal → risk score 0–100)
- [ ] 🔴 Output schema: `ThreatMap(run_id, hexes: list[HexThreat(hex_id, risk_score, risk_level, justification)])`
- [ ] 🟡 Unit test: high heat index + multiple 911 calls → hex scores "CRITICAL"
- [ ] 🟡 Test conflict handling: sarcastic social posts should not inflate risk score

---

## Phase 6 — Agent 3: Dispatch Commander Agent
*Goal: Translate threat map into optimized resource dispatch orders.*

### System Prompt & Tool Definition
- [ ] 🔴 Write system prompt: role = "You are the Dispatch Commander. Given a threat map, you autonomously route available DIL assets—cooling buses and EMS units—to maximize coverage of high-risk zones while minimizing response time. You call the dispatch tool to execute orders."
- [ ] 🔴 Define agent tools / actions:
  - `get_threat_map(run_id)` — fetch Agent 2 output
  - `get_available_assets()` — fetch resource inventory (mock or DB)
  - `run_optimization(threat_map, assets)` — linear optimization solver
  - `dispatch_assets(orders)` — **autonomous tool action** (write to DynamoDB, trigger notification)

### Implementation
- [ ] 🔴 Implement asset inventory (mock: 3 cooling buses, 5 EMS units at defined depot locations)
- [ ] 🔴 Implement linear optimization solver using **SciPy** (`scipy.optimize.linprog`) or **PuLP**:
  - Objective: maximize threat coverage weighted by risk score
  - Constraints: vehicle capacity, travel time, asset availability
- [ ] 🔴 Implement `dispatch_assets` tool — writes dispatch orders to DynamoDB + logs to CloudWatch
- [ ] 🔴 Output schema: `DispatchPlan(run_id, orders: list[Order(asset_id, asset_type, target_hex, eta_minutes)])`
- [ ] 🟡 Unit test: 2 CRITICAL hexes, 1 HIGH hex → optimizer assigns assets to CRITICAL first

---

## Phase 7 — Agent Orchestration Layer
*Goal: Pipeline runs end-to-end: Agent 1 → Agent 2 → Agent 3.*

- [ ] 🔴 Implement orchestrator in FastAPI:
  - `POST /api/v1/analyze` — triggers full 3-agent pipeline for a given region/time window
  - Stores each agent's output in DynamoDB keyed by `run_id`
  - Returns `run_id` immediately (async); pipeline runs as background task
- [ ] 🔴 Implement `GET /api/v1/runs/{run_id}/status` — poll pipeline status
- [ ] 🔴 Implement `GET /api/v1/runs/{run_id}/result` — fetch final dispatch plan + threat map
- [ ] 🔴 Implement agent handoff: Agent 1 output stored → Agent 2 retrieves it → Agent 3 retrieves Agent 2 output
- [ ] 🟡 Add retry logic for Bedrock API calls (exponential backoff)
- [ ] 🟡 Add run history endpoint: `GET /api/v1/runs` — list recent pipeline runs

---

## Phase 8 — FastAPI Backend
*Goal: Clean, documented API that the React frontend calls.*

- [ ] 🔴 FastAPI app setup with CORS configured for frontend origin
- [ ] 🔴 Health check: `GET /health`
- [ ] 🔴 Pydantic models for all request/response schemas
- [ ] 🔴 Bedrock client setup (boto3) with proper IAM role assumption
- [ ] 🟡 API docs auto-generated at `/docs` (FastAPI default — confirm it works)
- [ ] 🟡 Structured logging (JSON format) to stdout → CloudWatch
- [ ] 🟡 Request/response time middleware → emit metrics to CloudWatch
- [ ] 🟡 Token usage capture from Bedrock responses → store in DynamoDB for cost dashboard

---

## Phase 9 — React Frontend
*Goal: Web-based GUI showing the live hex grid, threat map, and dispatch orders.*

### Setup
- [ ] 🔴 Create React app (`npm create vite@latest` with React + TypeScript)
- [ ] 🔴 Install core dependencies:
  - `leaflet` + `react-leaflet` (free map, no API key — uses OpenStreetMap tiles)
  - `h3-js` (H3 hex grid in browser)
  - `@deck.gl/core` + `@deck.gl/layers` (H3HexagonLayer for hex rendering over Leaflet)
  - `recharts` (charts for observability panel)
  - `@tanstack/react-query` (polling + data fetching)

### Map & Hex Grid View
- [ ] 🔴 Render base map with `react-leaflet` using free OpenStreetMap/CartoDB tiles (no token required)
- [ ] 🔴 Overlay H3 hexagon polygons using `h3-js` (`h3.cellToBoundary`) rendered as Leaflet `Polygon` layers
- [ ] 🔴 Color-code hexes by risk level (green → yellow → orange → red)
- [ ] 🔴 Show dispatch asset markers (bus icons, EMS icons) on map with routes
- [ ] 🟡 Animate hex color transitions when new run results arrive

### Panel: Agent Status / "Thinking" States
- [ ] 🔴 Display pipeline run status with per-agent state: `IDLE | RUNNING | COMPLETE | ERROR`
- [ ] 🔴 Show last action taken by each agent (e.g., "Agent 1: geocoded 47 events to H3 grid")
- [ ] 🟡 Show agent reasoning/justification text in expandable panel

### Panel: Dispatch Orders
- [ ] 🔴 Table of current dispatch orders (asset, type, target hex, ETA)
- [ ] 🟡 Highlight newly dispatched assets

### Panel: Observability Dashboard
- [ ] 🔴 Pipeline run metrics: total runs, avg response time, last run timestamp
- [ ] 🔴 Token usage per agent (from backend API)
- [ ] 🔴 Estimated cost per run (based on token count × model pricing)
- [ ] 🟡 CloudWatch metrics embedded or fetched via backend proxy (agent latency, error rate)
- [ ] 🟡 Currently deployed infra cost estimate (from AWS Cost Explorer or hardcoded estimate)

### Trigger & Controls
- [ ] 🔴 "Run Analysis" button — calls `POST /api/v1/analyze`, polls for result, updates map
- [ ] 🟡 Region selector or date/time range filter

---

## Phase 10 — Observability
*Goal: Live dashboard for agent performance, cost, and system health.*

- [ ] 🔴 CloudWatch Log Groups created for: `heatwave-agent-1`, `heatwave-agent-2`, `heatwave-agent-3`, `heatwave-backend`
- [ ] 🔴 Emit structured logs from each agent: `{agent, run_id, action, duration_ms, tokens_used, model}`
- [ ] 🔴 CloudWatch Metrics: `AgentLatencyMs`, `AgentTokensUsed`, `PipelineRunCount`, `PipelineErrorCount`
- [ ] 🔴 CloudWatch Dashboard: `HEATWAVE-Observability` with widgets for the above metrics
- [ ] 🟡 CloudWatch Alarm: pipeline error rate > 10% → SNS notification
- [ ] 🟡 Token cost estimation: Claude Sonnet 3.5 pricing (`input × $0.000003` / `output × $0.000015` per token) logged per run

---

## Phase 11 — Security & Governance
*Goal: Bedrock Guardrails active; no over-privileged roles.*

- [ ] 🔴 Create **Bedrock Guardrail** resource (Terraform):
  - Deny topic: prevent LLM from making up medical advice not grounded in KB
  - Content filter: block harmful outputs
  - Grounding: require responses be grounded in retrieved context
- [ ] 🔴 Apply guardrail to Threat Assessment Agent (RAG output path)
- [ ] 🔴 IAM audit: each role has only the permissions it needs (no `*` actions)
- [ ] 🔴 GitHub Actions deploy role — OIDC federation (no static AWS keys in secrets)
- [ ] 🟡 S3 bucket policies — block public access on all buckets
- [ ] 🟡 Secrets Manager for any API keys (not .env files in prod)
- [ ] 🟡 Enable CloudTrail for audit logging

---

## Phase 12 — CI/CD (GitHub Actions)
*Goal: Every push to main triggers lint, test, build, and deploy.*

### Workflows
- [ ] 🔴 `.github/workflows/ci.yml` — on PR:
  - Python lint (flake8 / ruff) + type check (mypy)
  - Python unit tests (`pytest`)
  - Frontend lint (ESLint) + build (`npm run build`)
- [ ] 🔴 `.github/workflows/deploy-backend.yml` — on push to `main`:
  - Package FastAPI as zip (with `pip install -r requirements.txt -t ./package`)
  - Upload zip to S3
  - Update Lambda function code (`aws lambda update-function-code`)
- [ ] 🟡 `.github/workflows/terraform.yml` — on push to `main`:
  - `terraform fmt` check
  - `terraform validate`
  - `terraform plan` (auto) + `terraform apply` (auto on main, or manual approval gate)
- [ ] 🟡 `.github/workflows/deploy-frontend.yml` — on push to `main`:
  - `npm run build`
  - Sync `dist/` to S3 frontend bucket
  - Invalidate CloudFront distribution cache
- [ ] 🟡 Add status badges to README

---

## Phase 13 — Integration Testing & QA
*Goal: End-to-end pipeline tested with the synthetic dataset.*

- [ ] 🔴 Run full pipeline with synthetic dataset — confirm output is a valid dispatch plan
- [ ] 🔴 **Signal-to-noise test**: inject 20 irrelevant 911 calls — confirm they do not appear in Agent 1 output
- [ ] 🔴 **Conflict scenario test**: inject sarcastic social posts — confirm Agent 1 discards them and threat score is not inflated
- [ ] 🔴 **Conflict doc test**: two conflicting heat threshold docs in KB — confirm Agent 2 surfaces the discrepancy in justification text
- [ ] 🟡 Load test: run pipeline 5 times in parallel — confirm no race conditions in DynamoDB
- [ ] 🟡 Frontend smoke test: open app, click "Run Analysis," confirm map updates

---

## Phase 14 — Presentation Prep
*Goal: 2-minute elevator pitch + live demo ready for Saturday 4pm.*

- [ ] 🔴 Rehearse the pitch script (from the classmate's draft — adapt as needed)
- [ ] 🔴 Record a backup demo video in case live demo fails
- [ ] 🔴 Confirm all team members have commits on the shared repo
- [ ] 🔴 Stress test the live demo path 1–2 times end-to-end before Saturday
- [ ] 🟡 Prepare architecture diagram (draw.io or Excalidraw) to show during pitch
- [ ] 🟡 Prepare 1-slide observability screenshot showing CloudWatch dashboard
- [ ] 🟡 Prepare answers for likely "Market Volatility" wrenches:
  - "Add a flood data stream" — how would you extend Agent 1? (new data parser + S3 source)
  - "Add real-time data" — swap synthetic JSONs for live NWS/OpenWeatherMap API call
  - "Reduce cost by 50%" — swap Claude Sonnet for Claude Haiku (`anthropic.claude-haiku-20240307-v1:0`)
  - "Scale to 10 cities" — H3 resolution change + DynamoDB partition key strategy

---

## Daily Sprint Targets (suggested)

| Day | Focus |
|-----|-------|
| **Mon (Day 1)** | Phase 0 + Phase 1 (scaffolding + data sourcing) |
| **Tue (Day 2)** | Phase 2 + Phase 3 (Terraform + RAG pipeline) |
| **Wed (Day 3)** | Phase 4 + Phase 5 (Agent 1 + Agent 2) |
| **Thu (Day 4)** | Phase 6 + Phase 7 + Phase 8 (Agent 3 + orchestration + backend API) |
| **Fri (Day 5)** | Phase 9 + Phase 10 + Phase 11 + Phase 12 (frontend + CI/CD + security) |
| **Sat AM** | Phase 13 + Phase 14 (integration testing + final prep) |
| **Sat 4pm** | 🎤 PRESENT |

---

## "Pick Three" Compliance Checklist

| Requirement | Status | Where |
|---|---|---|
| Automated CI/CD | [ ] | `.github/workflows/` |
| Infrastructure as Code (Terraform) | [ ] | `/infra/` |
| Observability | [ ] | CloudWatch + frontend dashboard |
| Vector Integration (RAG) | [ ] | Bedrock Knowledge Base |
| Security & Governance | [ ] | Bedrock Guardrails + IAM |

> All five selected — exceeds the "pick three" minimum.

---

## DIL Data Standards Compliance

| Requirement | Status | Source |
|---|---|---|
| 5+ distinct documents | [ ] | `/data/` manifest |
| 1 dense doc (5+ pages technical) | [ ] | OSHA Heat Illness Prevention PDF |
| Signal-to-noise (raw, uncleaned data) | [ ] | Synthetic 911 + social media sets |
| Conflict scenario (conflicting docs) | [ ] | OSHA vs. NIOSH threshold docs |
