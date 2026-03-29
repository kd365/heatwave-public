# HEATWAVE — Agent Tool Reference

## Agent 1: Spatial Triage

Ingests raw data, filters noise, geocodes to H3 hex grid. **3 LLM calls total.**

### Tools (invoked by LLM via Bedrock tool_use)
| Tool | Backend | Purpose |
|------|---------|---------|
| `get_911_candidates` | Python data loader | Load pre-filtered 911 records — keyword pre-filter already applied, LLM judges the narratives |
| `get_social_media_posts` | Python data loader | Load social media posts for LLM sarcasm/noise filtering |
| `synthesize_findings` | Python data loader | Load all sub-task results for LLM narrative summary |

### Python Functions (deterministic, no LLM)
| Function | Purpose |
|----------|---------|
| `_process_weather` | Classify 4,608 hourly weather records by temperature thresholds (>=105F CRITICAL, >=100F HIGH, >=95F MEDIUM) |
| `_process_911` | Keyword pre-filter (1,035 records → ~50 candidates) → 1 LLM call to judge MO narratives |
| `_process_311` | Type + daily temperature scoring — no LLM needed (no narrative field in 311 data) |
| `_process_social` | 1 LLM call to filter sarcasm/noise from social media, extract locations |
| `_nearest_station_weather` | Interpolate temperature to every hex from nearest of 8 weather stations + UHI adjustment |

### Design Rationale
- **Weather:** Numeric thresholds — no ambiguity for an LLM to resolve
- **911:** MO narratives have ambiguous language ("hot" = temperature or stolen property?) — LLM judgment essential
- **311:** No text field — only type, date, address. Python can determine `Homeless Encampment + 109F = heat signal` as well as an LLM
- **Social media:** Sarcasm detection, noise filtering, location extraction — core LLM value

---

## Agent 2: Threat Assessment

Reads Agent 1 output, queries RAG knowledge base, scores every hex. **Runs on Haiku 4.5** (orchestration only — scoring is deterministic).

### Tools (invoked by LLM via Bedrock tool_use)
| Tool | Backend | Purpose |
|------|---------|---------|
| `get_hex_events` | S3 data loader | Load Agent 1's hex event output from S3 — no LLM reasoning, just `s3.get_object()` |
| `query_knowledge_base` | Bedrock KB retrieval | Query RAG KB for CDC/NIOSH WBGT thresholds, NWS heat index, Dallas UHI data — **this is where RAG happens** |
| `score_hex_threat` | Deterministic Python | Score a single hex — LLM calls it, Python runs the formula |
| `score_hex_batch` | Deterministic Python | Score 20-30 hexes per call — same formula, batched for efficiency |

### Scoring Formula (deterministic, in Python)
| Component | Weight | Input | Scale |
|-----------|--------|-------|-------|
| Weather | 50% | Apparent temperature | Nonlinear: 85F=0, 105F=0.7, 115F=1.0 |
| 911 Dispatch | 15% | Confirmed heat incidents | 0-3 incidents → 0.0-1.0 |
| 311 Service | 5% | Service request count | 0-8 requests → 0.0-1.0 |
| Social Media | 5% | Social signal count | 0-4 signals → 0.0-1.0 |
| Aggravating Factors | 25% | Auto-derived from hex data | Vulnerable pop (+0.35), no nighttime recovery (+0.30), multi-source (+0.35) |

### Risk Levels
| Level | Threshold | Meaning |
|-------|-----------|---------|
| CRITICAL | >= 0.82 | Extreme heat + confirmed 911 + vulnerable population + multi-source. Deploy immediately. |
| HIGH | >= 0.65 | Extreme heat + vulnerable population or multi-source signals. Pre-position assets. |
| MEDIUM | >= 0.45 | Elevated heat, possibly with isolated signals. Monitor. |
| LOW | < 0.45 | Below intervention threshold. Normal operations. |

### Post-LLM Backfill
Any hexes the LLM missed in batch calls are scored deterministically in Python after the agent completes — ensures all 341 hexes are always scored.

---

## Agent 3: Dispatch Commander

Reads threat map, autonomously selects dispatch strategy, deploys assets. **Runs on Sonnet 4** (strategy reasoning requires strong judgment).

### Tools (invoked by LLM via Bedrock tool_use)
| Tool | Backend | Purpose |
|------|---------|---------|
| `get_threat_map` | S3 data loader | Load Agent 2's scored threat map — `s3.get_object()` |
| `get_available_assets` | JSON data loader | Load 101-asset DFR inventory from local file |
| `query_knowledge_base` | Bedrock KB retrieval | Query RAG KB for FEMA NIMS resource typing, DFR fleet capabilities |
| `run_optimization` | PuLP / Python solver | Execute chosen strategy — **LLM selects which** and sets parameters, Python runs the math |
| `dispatch_orders` | DynamoDB write | Write final dispatch plan to system (autonomous action) |

### Optimization Strategies (in `run_optimization`)
| Strategy | Algorithm | When Selected | Target Hexes |
|----------|-----------|---------------|--------------|
| `optimize_coverage` | Linear Programming (PuLP CBC solver) | Many critical hexes, scarce assets | MEDIUM and above |
| `optimize_response_time` | Greedy nearest assignment | Few critical hexes, plenty of assets | HIGH and above |
| `optimize_staged_reserve` | Two-phase split deployment | Evolving/uncertain situation | CRITICAL (deploy) + HIGH (stage) |

### Autonomous Selection
The LLM analyzes the threat map shape — counts of CRITICAL/HIGH/MEDIUM, asset availability, threat certainty — and selects the strategy. **We never hardcode the selection.** The system prompt provides the decision framework; the LLM reasons through it and justifies its choice.

### LLM-Controlled Parameters (staged reserve only)
| Parameter | Range | Meaning |
|-----------|-------|---------|
| `reserve_ratio` | 0.0–1.0 | Fraction of assets held as reserves (default 0.3 = 30%) |
| `staging_radius` | hex rings | How close to stage reserves to HIGH zones (default 2 rings = ~2.4 km) |

---

## Pipeline Flow

```
Agent 1 (Sonnet 4)          Agent 2 (Haiku 4.5)         Agent 3 (Sonnet 4)
─────────────────           ────────────────────         ─────────────────
3 LLM calls                 ~17 LLM tool calls           ~5 LLM tool calls
+ deterministic Python      + deterministic scoring       + optimization solver

Weather (deterministic)     get_hex_events               get_threat_map
911 (keyword + 1 LLM)      query_knowledge_base (x2-3)  get_available_assets
311 (deterministic)         score_hex_batch (x14)        query_knowledge_base
Social (1 LLM)             → backfill missed hexes       run_optimization
Synthesis (1 LLM)                                        dispatch_orders
       ↓                          ↓                            ↓
   341 HexEvents              341 ThreatScores            DispatchPlan
```
