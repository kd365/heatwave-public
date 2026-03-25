# HEATWAVE — Project Roadmap
**Autonomous Spatial-Intelligence Platform for Preemptive Emergency Logistics**
Track 1: The "Chaos" Sector (Public Safety & Crisis)

> **Presentation:** Saturday March 28, 2026 @ 4pm
> **Scenario:** Dallas, TX heat wave — August 4-27, 2023 (peak: 109.3F on Aug 18)
> **Stack:** React (Vite + TS) · Python · FastAPI · AWS Bedrock (`anthropic.claude-3-5-sonnet-20241022-v2:0`) · Lambda · API Gateway · Terraform · GitHub Actions
> **AWS:** Default profile, default VPC, `us-east-1`
> **Map:** Leaflet + H3-js + OpenStreetMap tiles (free, no API key)
> **Repo:** https://github.com/kd365/heatwave/

---

## Team & Roles

| Member | Responsibility |
|--------|---------------|
| Kathleen (kd365) | Data sourcing, synthetic datasets, optimization solver, agent development |
| Partner (czarnick89) | Infrastructure (Terraform), CI/CD, frontend |
| Shared | Agent wiring (Bedrock), frontend (after backend complete) |

---

## Legend
- [X] Done
- [ ] Not started
- 🔴 Blocking / Critical path
- 🟡 Important but parallelizable
- 🟢 Nice-to-have / polish

---

## Architecture — Three-Agent Pipeline

```
Agent 1 (Spatial Triage) --> Agent 2 (Threat Assessment) --> Agent 3 (Dispatch Commander)
```

- **Agent 1:** Ingests weather, 911, 311, social media. Filters noise/sarcasm, geocodes to H3 hex grid. Outputs HexEvent list.
- **Agent 2:** Reads Agent 1 output + queries RAG (medical/OSHA/UHI docs). Scores each hex CRITICAL/HIGH/MEDIUM/LOW.
- **Agent 3:** Reads threat map + asset inventory. **Autonomously selects** one of three dispatch strategies. Outputs DispatchPlan.

### Agent 3 — Autonomous Tool Selection (key demo feature)
The LLM reasons about the threat map and picks the strategy. We never hardcode the selection.
1. `optimize_coverage` (PuLP LP) — many critical hexes, scarce assets → maximize weighted threat coverage
2. `optimize_response_time` (greedy nearest) — few critical hexes, enough assets → minimize response time
3. `optimize_staged_reserve` (split deploy) — uncertain/evolving situation → deploy to CRITICAL, stage reserves near HIGH clusters

System prompt: *"Analyze the threat map, consider critical zone count, asset availability, and threat certainty, then select and execute the most appropriate strategy. Justify your choice."*

**Demo plan:** Run two different threat scenarios → Agent 3 visibly picks different strategies.

---

## Phase 0 — Project Foundation ✅
*Goal: Everyone can run the project locally and push to the shared repo.*

### Repo & Scaffolding
- [X] 🔴 Fork repo; add both partners as collaborators
- [X] 🔴 Branch strategy: `main` protected (1 PR approval), feature branches `feat/*`
- [X] 🔴 Monorepo structure: `/frontend`, `/backend`, `/infra`, `/data`, `/agents`, `.github/`
- [X] 🔴 `.gitignore`
- [X] 🔴 `.env.example` with all required environment variable keys
- [ ] 🟡 Root `README.md` with setup instructions and architecture diagram

### Local Dev Environment
- [X] 🔴 Python venv + `requirements.txt` (h3, pulp, pytest, etc.)
- [X] 🔴 Node.js / Vite frontend scaffolding
- [ ] 🟡 `Makefile` with common commands
- [ ] 🟡 Pre-commit hooks (Black, isort, ESLint)

### PRs
- [X] PR #6 — Project initialization
- [X] PR #7 — Phase 0 scaffolding (monorepo, vite frontend, .env.example)
- [X] PR #24 — Bootstrap script for remote state (S3 + DynamoDB lock)
- [X] PR #25 — Phase 2 Terraform setup (providers, variables, outputs, main scaffolding)

---

## Phase 1 — Data Sourcing & Validation Set ✅
*Goal: Meet DIL data standards — 5+ docs, 1 dense doc, signal-to-noise, conflict scenario.*

### Reference Documents (RAG corpus) — 6 documents
- [X] 🔴 CDC/NIOSH heat stress criteria (`cdc_niosh_2016-106_heat_stress.pdf`, 192 pages) — **dense doc**
- [X] 🔴 OSHA heat hazard assessment (`osha_otm_section3_chapter4_heat_hazards.md`) — WBGT equations, illness types
- [X] 🔴 NWS heat index safety (`nws_heat_index_safety.md`) — **CONFLICT DOC** (Heat Index vs WBGT thresholds)
- [X] 🔴 FEMA NIMS doctrine (`fema_nims_doctrine_2017.pdf`) — resource typing, ICS structure
- [X] 🔴 DFR EMS Annual Report 2023 (`dfr_ems_annual_report_2023.pdf`, 27 pages) — exact fleet: 47 ambulances, 8 peak-demand rescues, MODSS, RIGHT Care
- [X] 🔴 Dallas Urban Heat Island Study (`dallas_uhi_study_2017.pdf`, 83 pages) — 4,000+ data points on neighborhood heat vulnerability

### Operational Data — 5 datasets (real + synthetic)

**Real data:**
- [X] 🔴 Dallas 911 dispatch (`dallas_911_aug2023.json`, 1,035 records) — real Dallas PD, heat signals buried in noise
- [X] 🔴 Dallas weather (`dallas_weather_aug2023.json`, 4,608 records) — 8 stations, hourly, Open-Meteo Archive API
- [X] 🔴 Dallas fire stations (`dallas_fire_stations.json`, 60 stations) — all DFR stations with lat/lon
- [X] 🔴 Dallas 311 requests (`dallas_311_aug2023.json`, 4,482 records) — homeless encampment, animal, water complaints

**Synthetic data:**
- [X] 🔴 Social media posts (`social_media_posts.json`, 300 posts) — signal/sarcasm/noise mix, deliberate data friction
- [X] 🔴 Asset inventory (`dallas_asset_inventory.json`, 101 assets) — typed per NIMS from real DFR fleet + cooling centers

### Data Storage
- [X] 🔴 All docs in `/data/` with `manifest.json` (12 datasets, DIL compliance mapping)
- [X] 🟡 Upload reference docs to S3 RAG bucket

### PRs
- [X] PR #26 — Data sourcing for Dallas Aug 2023 heat wave
- [X] PR #27 — H3 geocoding utility
- [X] PR #28 — Dispatch optimization and Dallas data

### DIL Compliance — MET

| Requirement | Status | Evidence |
|---|---|---|
| 5+ distinct documents | ✅ | 12 datasets/documents |
| 1 dense doc (5+ pages) | ✅ | CDC NIOSH (192pg), Dallas UHI Study (83pg), DFR Annual Report (27pg) |
| Signal-to-noise | ✅ | 10 heat MO entries in 1,035 911 records; social media noise/sarcasm; 311 mixed relevance |
| Conflict scenario | ✅ | NWS Heat Index vs OSHA/NIOSH WBGT thresholds — different risk assessments for same conditions |

---

## Phase 2 — AWS Infrastructure (Terraform)
*Goal: All cloud resources defined as code; no manual console clicks.*
*Owner: czarnick89 (primary), Kathleen (review)*

### Terraform Setup ✅
- [X] 🔴 S3 remote state + DynamoDB lock table (bootstrapped)
- [X] 🔴 `variables.tf`, `outputs.tf`, `main.tf` scaffolding
- [X] 🔴 AWS provider configured (`us-east-1`, Bedrock model ID set)

### Core Infrastructure — IN PROGRESS
- [X] 🔴 **S3 Bucket** for data + RAG docs + processed results
- [X] 🔴 **IAM Roles & Policies** — zero trust / least-privilege for:
  - Bedrock agent execution role
  - Lambda execution role (invoke Bedrock, read/write S3 + DynamoDB)
  - GitHub Actions deploy role (OIDC — no long-lived keys)
- [X] 🔴 **Bedrock Knowledge Base** — managed OpenSearch Serverless, pointing to S3 RAG bucket
- [X] 🔴 **Lambda function** for FastAPI backend (Mangum handler)
- [X] 🔴 **API Gateway** (HTTP API) in front of Lambda
- [X] 🔴 **DynamoDB table** for pipeline run state (keyed by `run_id`)
- [ ] 🟡 **CloudWatch Log Groups** for agents + backend
- [ ] 🟡 **CloudWatch Dashboard** (`HEATWAVE-Observability`)
- [ ] 🟡 **S3 + CloudFront** for React static hosting

### Terraform Plan/Apply
- [X] 🔴 `terraform plan` clean
- [X] 🔴 `terraform apply` — provision dev environment
- [ ] 🟡 Tag all resources: `project=heatwave`, `env=dev`

---

## Phase 3 — RAG Pipeline
*Goal: Agent 2 can retrieve relevant clinical thresholds from reference docs.*
*Owner: Kathleen (upload + test), czarnick89 (KB provisioning)*

- [X] 🔴 Upload 6 reference documents to S3 RAG bucket
- [X] 🔴 Configure and sync Bedrock Knowledge Base data source
- [X] 🔴 Run KB ingestion job; confirm chunks indexed (6 docs, 0 failed)
- [X] 🔴 Test RAG query: *"At what wet-bulb temperature does heatstroke risk become critical for outdoor workers?"* — CDC NIOSH: 30°C (86°F) WBT upper limit for moderate work
- [ ] 🟡 Tune chunking strategy for dense medical text (CDC 192pg)
- [X] 🟡 Confirm conflict scenario: NWS and OSHA docs both surface with different thresholds ✅
  - Heat Index query → `nws_heat_index_safety.md` (0.634): Danger at HI 103°F
  - WBGT query → `osha_otm_section3_chapter4_heat_hazards.md` (0.590): moderate work limit 27–28°C WBGT
  - Same Aug 18 conditions (109.3°F Dallas) → NWS = Extreme Danger; OSHA = work should cease at ~28°C WBGT
- [X] 🟡 Test Agent 3 RAG query: *"What is the DFR ambulance fleet size and peak-demand staffing model?"* — dfr_ems_annual_report_2023.pdf retrieved ✅

---

## Phase 4 — Agent 1: Spatial Triage
*Goal: Ingest raw chaos, filter signal, geocode onto H3 hex grid.*
*Owner: Kathleen*

### System Prompt & Tools
- [ ] 🔴 Write system prompt: *"You are a Spatial Triage Analyst. Ingest raw data streams, extract heat-relevant signals, ignore noise and sarcasm, output structured spatial events geocoded to H3 hexagons."*
- [ ] 🔴 Define tools:
  - `get_weather_data(region, time_window)` — reads `dallas_weather_aug2023.json`
  - `get_911_records(region, time_window)` — reads `dallas_911_aug2023.json`
  - `get_311_records(region, time_window)` — reads `dallas_311_aug2023.json`
  - `get_social_media_posts(region, time_window)` — reads `social_media_posts.json`
  - `geocode_to_h3(lat, lon)` — calls `h3_geocoding.latlng_to_hex()`

### Implementation
- [X] 🔴 H3 geocoding utility (`backend/utils/h3_geocoding.py`) — 21 tests passing
  - `latlng_to_hex`, `hex_to_center`, `hex_to_boundary`, `get_hex_neighbors`
  - `geocode_911_records` (with zip fallback), `geocode_weather_records`, `geocode_social_media_posts`
  - `aggregate_by_hex`
- [ ] 🔴 Weather data parser (JSON → HexEvents with temp/humidity conditions)
- [ ] 🔴 911 record classifier — LLM-assisted heat signal detection from MO narratives
- [ ] 🔴 311 record classifier — flag homeless encampment + water complaints as heat signals
- [ ] 🔴 Social media parser — detect sarcasm/noise, classify heat relevance; unlocated posts require text analysis for location clues
- [ ] 🔴 Output schema: `HexEvent(hex_id, event_type, severity_score, timestamp, source)`
- [ ] 🟡 Unit test: synthetic dataset → known heat signals surface, sarcasm discarded

---

## Phase 5 — Agent 2: Threat Assessment
*Goal: Cross-reference spatial grid against clinical knowledge to score each hex.*
*Owner: Kathleen*

### System Prompt & Tools
- [ ] 🔴 Write system prompt: *"You are a Threat Assessment Analyst with expertise in environmental medicine. Query the medical knowledge base to determine which hexagonal zones have crossed physiological danger thresholds. Output a threat map with risk levels."*
- [ ] 🔴 Define tools:
  - `query_knowledge_base(query_text)` — RAG retrieval from Bedrock KB
  - `get_hex_events(run_id)` — fetch Agent 1 output
  - `score_hex_threat(hex_id, conditions)` — deterministic scoring

### Implementation
- [ ] 🔴 RAG query tool wired to Bedrock Knowledge Base
- [ ] 🔴 Threat scoring logic (weather conditions + 911/311 density + social signal → risk score 0.0-1.0)
- [ ] 🔴 Output schema: `ThreatMap(run_id, hexes: list[ThreatHex(hex_id, risk_level, risk_score, justification)])`
- [ ] 🟡 Unit test: high heat index + multiple 911 calls → CRITICAL
- [ ] 🟡 Test: sarcastic social posts do not inflate risk score
- [ ] 🟡 Test: Agent 2 cites UHI study to justify South Dallas vulnerability scoring

---

## Phase 6 — Agent 3: Dispatch Commander
*Goal: Translate threat map into optimized resource dispatch orders via autonomous strategy selection.*
*Owner: Kathleen*

### System Prompt & Tools
- [ ] 🔴 Write system prompt: *"You are the Dispatch Commander. Given a threat map and asset inventory, autonomously select and execute the most appropriate dispatch strategy. Justify your choice. Available strategies: optimize_coverage, optimize_response_time, optimize_staged_reserve."*
- [ ] 🔴 Define tools:
  - `get_threat_map(run_id)` — fetch Agent 2 output
  - `get_available_assets()` — fetch from `dallas_asset_inventory.json` (101 assets, 11 types)
  - `optimize_coverage(threat_map, assets)` — PuLP LP solver
  - `optimize_response_time(threat_map, assets)` — greedy nearest assignment
  - `optimize_staged_reserve(threat_map, assets, staging_radius, reserve_ratio)` — split deploy
  - `dispatch_assets(orders)` — write to DynamoDB, trigger notification
  - `query_knowledge_base(query_text)` — RAG for FEMA NIMS resource typing + DFR fleet constraints

### Implementation
- [X] 🔴 Asset inventory: 101 assets across 11 NIMS-typed categories (from real DFR fleet data)
  - 47 front-line ALS ambulances, 8 peak-demand rescues, 8 special event rescues
  - 4 mini-ambulances, 4 mobile medical units, 4 RIGHT Care, 4 DART Cares, 1 Medic 1, 1 MODSS
  - 10 cooling centers (libraries), 10 cooling centers (rec centers)
- [X] 🔴 Three optimization strategies (`backend/utils/optimization.py`) — 21 tests passing
- [ ] 🔴 Wire solver to Bedrock agent as callable tools
- [ ] 🔴 `dispatch_assets` tool — write orders to DynamoDB + log to CloudWatch
- [ ] 🔴 Output schema: `DispatchPlan(strategy_used, orders, unassigned_hexes, summary)`
- [ ] 🟡 Demo scenario 1: many CRITICAL hexes → Agent 3 picks `optimize_coverage`
- [ ] 🟡 Demo scenario 2: few CRITICAL hexes → Agent 3 picks `optimize_response_time`

---

## Phase 7 — Orchestration + Backend API
*Goal: Pipeline runs end-to-end: Agent 1 → Agent 2 → Agent 3, exposed via FastAPI.*
*Owner: czarnick89 (primary), Kathleen (agent integration)*

### Orchestration
- [ ] 🔴 `POST /api/v1/analyze` — triggers full 3-agent pipeline, returns `run_id` (async)
- [ ] 🔴 `GET /api/v1/runs/{run_id}/status` — poll pipeline status
- [ ] 🔴 `GET /api/v1/runs/{run_id}/result` — fetch dispatch plan + threat map
- [ ] 🔴 Agent handoff: Agent 1 → DynamoDB/S3 → Agent 2 → DynamoDB/S3 → Agent 3
- [ ] 🟡 Retry logic for Bedrock API calls (exponential backoff)
- [ ] 🟡 `GET /api/v1/runs` — list recent pipeline runs

### FastAPI Backend
- [ ] 🔴 FastAPI app with CORS for frontend
- [ ] 🔴 `GET /health` health check
- [ ] 🔴 Pydantic models for request/response schemas
- [ ] 🔴 Bedrock client (boto3) with IAM role assumption
- [ ] 🟡 Structured JSON logging → CloudWatch
- [ ] 🟡 Request/response time middleware → CloudWatch metrics
- [ ] 🟡 Token usage capture → DynamoDB for cost dashboard

---

## Phase 8 — Frontend
*Goal: Web GUI showing hex grid, threat map, dispatch orders, and observability.*
*Owner: Shared (after backend complete)*

### Setup
- [X] 🔴 Vite + React + TypeScript scaffolding
- [ ] 🔴 Install: `leaflet`, `react-leaflet`, `h3-js`, `recharts`, `@tanstack/react-query`

### Map & Hex Grid
- [ ] 🔴 Base map with OpenStreetMap/CartoDB tiles (no key needed)
- [ ] 🔴 H3 hex overlay color-coded by risk level (green → yellow → orange → red)
- [ ] 🔴 Dispatch asset markers on map (ambulance, cooling center icons)
- [ ] 🟡 Animate hex transitions on new results

### Panels
- [ ] 🔴 Agent status panel: `IDLE | RUNNING | COMPLETE | ERROR` per agent
- [ ] 🔴 Dispatch orders table (asset, type, target hex, distance)
- [ ] 🔴 Observability panel: run count, avg response time, token usage, cost estimate
- [ ] 🟡 Agent reasoning/justification expandable panel
- [ ] 🟡 CloudWatch metrics embedded or fetched via proxy

### Controls
- [ ] 🔴 "Run Analysis" button → `POST /api/v1/analyze`, poll, update map
- [ ] 🟡 Date/time range selector

---

## Phase 9 — Observability + Security + CI/CD
*Goal: Production-grade ops — logging, monitoring, guardrails, automated deploy.*

### Observability
- [ ] 🔴 CloudWatch Log Groups: `heatwave-agent-1`, `-agent-2`, `-agent-3`, `-backend`
- [ ] 🔴 Structured logs: `{agent, run_id, action, duration_ms, tokens_used, model}`
- [ ] 🔴 CloudWatch Metrics: `AgentLatencyMs`, `AgentTokensUsed`, `PipelineRunCount`, `PipelineErrorCount`
- [ ] 🔴 CloudWatch Dashboard: `HEATWAVE-Observability`
- [ ] 🟡 Alarm: pipeline error rate > 10% → SNS
- [ ] 🟡 Token cost tracking (Claude Sonnet 3.5 v2 pricing)

### Security & Governance
- [ ] 🔴 Bedrock Guardrail (Terraform): deny ungrounded medical advice, content filter, grounding enforcement
- [ ] 🔴 Apply guardrail to Agent 2 RAG output path
- [ ] 🔴 IAM audit: no `*` actions, least-privilege per role
- [ ] 🔴 GitHub Actions OIDC federation (no static AWS keys)
- [ ] 🟡 S3 block public access on all buckets
- [ ] 🟡 Secrets Manager for API keys
- [ ] 🟡 CloudTrail audit logging

### CI/CD (GitHub Actions)
- [ ] 🔴 `.github/workflows/ci.yml` — PR: lint (ruff), pytest, ESLint, frontend build
- [ ] 🔴 `.github/workflows/deploy-backend.yml` — push to main: package + deploy Lambda
- [ ] 🟡 `.github/workflows/terraform.yml` — terraform fmt/validate/plan/apply
- [ ] 🟡 `.github/workflows/deploy-frontend.yml` — build + sync to S3 + CloudFront invalidate
- [ ] 🟡 Status badges in README

---

## Phase 10 — Integration Testing & Demo Prep
*Goal: End-to-end tested, demo rehearsed, presentation ready.*

### Integration Testing
- [ ] 🔴 Full pipeline with real Dallas dataset → valid dispatch plan
- [ ] 🔴 **Signal-to-noise test**: irrelevant 911 calls do not appear in Agent 1 output
- [ ] 🔴 **Sarcasm test**: sarcastic social posts discarded, threat score not inflated
- [ ] 🔴 **Conflict doc test**: NWS vs OSHA thresholds — Agent 2 surfaces discrepancy in justification
- [ ] 🔴 **Strategy selection test**: two scenarios → Agent 3 picks different strategies
- [ ] 🟡 Load test: 5 parallel pipeline runs, no DynamoDB race conditions
- [ ] 🟡 Frontend smoke test: click Run Analysis, map updates

### Presentation Prep
- [ ] 🔴 Rehearse pitch (2-minute elevator pitch)
- [ ] 🔴 Record backup demo video
- [ ] 🔴 Confirm both team members have commits in repo
- [ ] 🔴 Stress test live demo 1-2 times end-to-end
- [ ] 🟡 Architecture diagram (draw.io / Excalidraw)
- [ ] 🟡 Observability screenshot (CloudWatch dashboard)
- [ ] 🟡 Prepare "Market Volatility" wrench answers:
  - "Add a flood data stream" → new data parser + S3 source for Agent 1
  - "Add real-time data" → swap static JSON for live NWS/OpenWeatherMap API
  - "Reduce cost by 50%" → swap Claude Sonnet for Haiku
  - "Scale to 10 cities" → H3 resolution param + DynamoDB partition key strategy

---

## Daily Sprint (Tue Mar 24 – Sat Mar 28)

| Day | Date | Kathleen | czarnick89 | Milestone |
|-----|------|----------|------------|-----------|
| **1** | Tue 3/24 | ~~Phase 0+1 data~~ ✅, ~~H3 geocoding~~ ✅, ~~Optimization solver~~ ✅ | Terraform provisioning (S3, IAM, Bedrock KB) | Data + solver complete, infra provisioned |
| **2** | Wed 3/25 | RAG upload + test, Agent 1 system prompt + wiring | Lambda + API Gateway + DynamoDB, CI/CD workflow | RAG working, Agent 1 prototype |
| **3** | Thu 3/26 | Agent 2 + Agent 3 Bedrock wiring | Orchestration layer, FastAPI backend | All 3 agents callable, pipeline wired |
| **4** | Fri 3/27 | Frontend (together) — map, hex grid, panels | Frontend (together) — observability, controls | Working GUI with live pipeline |
| **5** | Sat 3/28 AM | Integration testing, demo rehearsal | Security guardrails, final fixes | Demo-ready by noon |
| | Sat 3/28 4pm | 🎤 **PRESENT** | 🎤 **PRESENT** | |

---

## "Pick Five" Compliance Checklist

| Requirement | Status | Where |
|---|---|---|
| Automated CI/CD | [ ] | `.github/workflows/` |
| Infrastructure as Code | [X] partially | `/infra/` (scaffolding done, provisioning in progress) |
| Observability | [ ] | CloudWatch + frontend dashboard |
| Vector Integration (RAG) | [X] | Bedrock Knowledge Base — 6 docs indexed, RAG queries validated |
| Security & Governance | [ ] | Bedrock Guardrails + IAM zero trust |

> All five selected — exceeds the "pick three" minimum.

---

## DIL Data Standards Compliance ✅

| Requirement | Status | Evidence |
|---|---|---|
| 5+ distinct documents | ✅ | 12 datasets/documents in `/data/manifest.json` |
| 1 dense doc (5+ pages) | ✅ | CDC NIOSH (192pg), Dallas UHI Study (83pg), DFR EMS Report (27pg) |
| Signal-to-noise | ✅ | 10 heat MO entries in 1,035 911 records; sarcasm/noise in social media; mixed-relevance 311 |
| Conflict scenario | ✅ | NWS Heat Index thresholds vs OSHA/NIOSH WBGT thresholds |

---

## Appendix: Agent 3 Optimization Strategy Reference

### Strategy 1: `optimize_coverage` (Linear Programming)

**When the LLM picks this:** Many CRITICAL/HIGH hexes, not enough assets to cover them all. Need to be strategic about *which* hexes to cover.

**How it works:** It's a math problem. We have a grid of dangerous hexes, each with a risk score (0.0-1.0). We have assets, each with a coverage radius (how many hex rings it can reach) and a capacity (how many hexes it can serve at once). The LP solver finds the assignment that **maximizes total risk covered**.

Think of it like this: you have 3 ambulances but 10 dangerous neighborhoods. You can't cover them all. The solver says "put ambulance A here - it covers two CRITICAL zones. Put ambulance B there - it covers one CRITICAL and one HIGH." It picks the combination that protects the most people weighted by danger level.

**The math:**
- **Decision:** for each (asset, hex) pair, assign or not (binary 0/1)
- **Objective:** maximize the sum of `risk_score` for all covered hexes
- **Constraints:** each asset can only serve up to `capacity` hexes, and can only reach hexes within its `coverage_radius`

### Strategy 2: `optimize_response_time` (Greedy Nearest)

**When the LLM picks this:** Few critical hexes, plenty of assets. The problem isn't *which* hexes to cover - it's getting there **fast**.

**How it works:** Sort the dangerous hexes by risk score (worst first). For each hex, find the closest available asset and assign it. Simple, fast, no fancy math.

**Example:** There's one heat stroke emergency downtown. You have 5 ambulances around the city. This strategy picks the ambulance that's 1 hex ring away, not the one that's 8 rings away. It doesn't need to optimize tradeoffs because there are enough assets - it just minimizes travel distance.

**The tradeoff:** It's greedy - it assigns the first critical hex the best asset, which might "steal" that asset from a second critical hex that also needed it. That's why this only works well when you have more assets than emergencies.

### Strategy 3: `optimize_staged_reserve` (Split Deploy)

**When the LLM picks this:** The situation is **evolving**. Maybe it's 2pm and temperatures are still climbing. Some hexes are CRITICAL now, but HIGH hexes could escalate by 4pm.

**How it works in two phases:**

**Phase 1 - Deploy:** Take `(1 - reserve_ratio)` of your assets (default 70%) and send them to CRITICAL hexes using greedy nearest (same as strategy 2).

**Phase 2 - Stage:** Take the remaining 30% and position them **near** HIGH-risk clusters, but not *at* them. The `staging_radius` parameter (set by the LLM) controls how close. Staged assets aren't responding to emergencies yet - they're pre-positioned so that when a HIGH hex escalates to CRITICAL, the response time is minutes, not hours.

**Example:** 10 assets total. 7 deploy immediately to the three CRITICAL hexes downtown. 3 stage within 2 hex rings of the HIGH-risk cluster in southeast Dallas. If southeast goes CRITICAL at 4pm, those staged assets are already nearby.

**The two LLM-controlled parameters:**
- `reserve_ratio` (0.0-1.0): how much to hold back. Higher = more cautious.
- `staging_radius` (hex rings): how close to stage. Smaller = closer to danger but more responsive. The LLM decides these based on its read of the situation - time of day, temperature trajectory, forecast confidence.

### Strategy Selection Matrix

| Situation | Strategy picked | Reasoning |
|-----------|----------------|-----------|
| 15 CRITICAL hexes, 6 ambulances | `optimize_coverage` | Can't cover everything, maximize impact |
| 2 CRITICAL hexes, 8 ambulances | `optimize_response_time` | Plenty of assets, get there fast |
| 5 CRITICAL now, 10 HIGH trending up, 3pm and climbing | `optimize_staged_reserve` | Hedge for escalation |

We never hardcode the selection. The system prompt tells Agent 3: *"Analyze the threat map, consider critical zone count, asset availability, and threat certainty, then select and execute the most appropriate strategy. Justify your choice."*

---

## GitHub Issues / PRs Tracker

### PRs (merged)
- [X] PR #6 — Project initialization
- [X] PR #7 — Phase 0 scaffolding
- [X] PR #24 — Bootstrap remote state
- [X] PR #25 — Terraform setup
- [X] PR #26 — Data sourcing
- [X] PR #27 — H3 geocoding utility
- [X] PR #28 — Dispatch optimization + data

### Open Issues
- [ ] #8 — Terraform root module & remote state → ✅ done (PR #24, #25)
- [ ] #9 — Terraform IAM roles & Secrets Manager → czarnick89, Day 1
- [ ] #10 — Terraform Bedrock/OpenSearch & S3 → czarnick89, Day 1
- [ ] #11 — Init repo & CI/CD pipeline → czarnick89, Day 2
- [ ] #12 — Generate mock data firehose → ✅ done (real data, PR #26, #28)
- [ ] #13 — Validate Bedrock & upload RAG docs → Kathleen, Day 2
- [ ] #14 — Build Agent 1 (Spatial Triage) → Kathleen, Day 2
- [ ] #15 — RAG pipeline (Bedrock KB retrieval) → shared, Day 2
- [ ] #16 — Build Agent 2 (Threat Assessment) → Kathleen, Day 3
- [ ] #17 — Build Agent 3 (Dispatch Optimizer) → Kathleen, Day 3 (solver done, wiring needed)
- [ ] #18 — CloudWatch log groups & dashboard → czarnick89, Day 4
- [ ] #19 — Instrument agents with CloudWatch/X-Ray → shared, Day 4
- [ ] #20 — Map interface (GUI) → shared, Day 4
- [ ] #21 — Wire pipeline to GUI & smoke test → shared, Day 4
- [ ] #22 — End-to-end scenario testing → shared, Day 5
- [ ] #23 — DIL pitch & demo rehearsal → shared, Day 5
