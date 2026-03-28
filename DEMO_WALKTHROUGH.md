# HEATWAVE — Demo Walkthrough & Talking Points

**Presentation: Saturday March 28, 2026 @ 4pm**
**Time budget: ~15 minutes (5 min pitch + 5 min live demo + 5 min Q&A)**

---

## Pre-Demo Checklist

- [ ] Pre-run Aug 18 (peak) analysis ~30 min before demo so results are cached
- [ ] Pre-run Aug 16 (cool) analysis for contrast comparison
- [ ] Have CloudFront URL open: https://d1fkyokay3hahf.cloudfront.net
- [ ] Have CloudWatch dashboard open in another tab: HEATWAVE-Observability
- [ ] Have GitHub repo open: https://github.com/kd365/heatwave/
- [ ] Backup: screenshots of a completed run in case of live demo failure

---

## Part 1: The Pitch (5 minutes)

### Opening (30 sec)
> "In August 2023, Dallas experienced 24 consecutive days above 100 degrees. At least 34 people died from heat-related causes in Texas that month. Emergency responders were reactive — dispatching ambulances after people collapsed, not before. HEATWAVE closes that gap."

### The Problem (1 min)
- Heat emergencies are **predictable but poorly coordinated**
- Data exists across silos: weather stations, 911 dispatch, 311 service requests, social media
- No system cross-references these signals against medical thresholds in real-time
- Result: ambulances go where people have already collapsed, not where they're about to

### Our Solution (1.5 min)
- **Three AI agents working in sequence:**
  1. **Spatial Triage** — ingests 10,000+ records, filters noise (is "it's hot" sarcasm or a real complaint?), geocodes everything to a hex grid
  2. **Threat Assessment** — queries a medical knowledge base (CDC heat stress criteria, OSHA thresholds) and scores each neighborhood. Surfaces a real conflict: NWS says "Extreme Danger" at 109F, but OSHA uses a different metric (WBGT) with different thresholds
  3. **Dispatch Commander** — looks at the threat map and **autonomously chooses** a deployment strategy. It has three options: maximize coverage, minimize response time, or hedge with staged reserves. The AI picks based on the situation. We never hardcode the choice.
- **Key insight:** Agent 3's strategy selection is the demo moment. Run a hot day vs a cool day and watch it pick different strategies.

### Technical Highlights (1 min)
- **"Pick Five":** CI/CD (GitHub Actions), IaC (Terraform — 47 resources), Observability (CloudWatch dashboard + frontend metrics), RAG (Bedrock KB with 6 medical docs), Security (Bedrock Guardrails + IAM least-privilege)
- **DIL compliance:** 12 datasets, 192-page CDC document, signal buried in noise, conflicting medical standards
- **Real data:** Dallas 911 dispatch, weather stations, 311 requests — not synthetic

### Architecture Slide (1 min)
- Show the pipeline diagram: Agent 1 → Agent 2 → Agent 3
- Point out: "Deterministic where possible, LLM where judgment is needed"
- Mention: runs on Lambda, ~7 min end-to-end, ~$2 per analysis

---

## Part 2: Live Demo (5 minutes)

### Demo Flow: Aug 18 (Peak Day — 109F)

**Step 1: Show the pre-loaded result (30 sec)**
> "This is August 18th, 2023 — the peak of the heat wave at 109 degrees. The hex grid covers all of Dallas at neighborhood resolution."

- Point to the **color gradient**: orange/red hexes in south Dallas, yellow in central, green on edges
- Point to the **legend**: "1 CRITICAL, 44 HIGH, 266 MEDIUM, 30 LOW"
- **Talking point:** "South Dallas consistently scores higher — that's the Urban Heat Island effect. The system knows this from the Dallas UHI Study in our knowledge base."

**Step 2: Hover over a HIGH hex (30 sec)**
- Show the tooltip: temperature, apparent temp, 911 incidents, 311 requests, social signals, population, elderly percentage
- **Talking point:** "This hex has 112F apparent temperature, a confirmed 911 heat incident, and 1,200 elderly residents. The scoring formula weights all of these — temperature is 50%, but vulnerable population and multi-source corroboration push it to HIGH."

**Step 3: Show the Agent Panel (30 sec)**
- Point to A1/A2/A3 all COMPLETE
- Show observability: strategy used, duration, token count, estimated cost
- **Talking point:** "Agent 3 chose 'Coverage Maximization' — with 44 HIGH-risk hexes and limited ambulances, it used a linear programming solver to maximize the total threat coverage."

**Step 4: Show Dispatch Orders (30 sec)**
- Scroll the dispatch table: asset IDs, roles (Deploy/Stage), target hexes, distances
- Point to ambulance markers on the map clustered around HIGH/CRITICAL hexes
- Point to cooling center markers (snowflake icons) activated in south Dallas
- **Talking point:** "20 cooling centers activated, 43 mobile assets deployed. The LP solver placed ambulances where they cover the most high-risk population."

**Step 5: Contrast with Aug 16 — Cool Day (1 min)**

> "Now watch what happens on August 16th — the coolest day of the period at 94 degrees."

- Switch date selector to Aug 16
- Click Run Analysis (or show pre-loaded result)
- **Expected result:** Mostly green/LOW hexes, few MEDIUM, no HIGH/CRITICAL
- **Talking point:** "Same data sources, same pipeline, completely different threat picture. And watch — Agent 3 picks a *different* strategy this time."
- If Agent 3 picks `optimize_response_time`: "With only a few medium-risk zones, it doesn't need to maximize coverage. It picks the greedy nearest strategy — just get to the few hot spots fast."

**Step 6: Show Infrastructure (1 min)**
- Tab to GitHub: show CI/CD runs (green checks), PR history
- Tab to CloudWatch dashboard: pipeline duration graph, token usage, error rate
- **Talking point:** "Every push to main triggers automated tests, builds, and deploys. The CloudWatch dashboard tracks every run — duration, cost, errors. We've run 20+ successful pipeline executions this week."

**Step 7: Cancel Demo (30 sec)**
- Start a new run, show the cancel button appear
- Click cancel, show the "Cancelling after current agent completes..." message
- **Talking point:** "We added run cancellation — it checks between agent steps so you don't waste compute on a run you don't need."

---

## Part 3: Q&A Prep — "Market Volatility" Wrench Answers

### "Add a new data stream (e.g., flood data)"
> "Agent 1 is designed for this. We'd add a new data loader function, a deterministic filter for flood-specific signals, and map them to the same H3 hex grid. Agent 2 already handles multi-source scoring. The hex grid is the universal connector — any geo-located data source snaps onto it."

### "Make it work for another city"
> "The H3 hex grid is resolution-parameterized — change the center coordinates and bounding box, and it generates a new grid. The RAG knowledge base is city-agnostic (CDC/OSHA thresholds apply everywhere). City-specific data: swap the 911/311 data sources and add local census data. The architecture doesn't change."

### "Reduce cost by 50%"
> "We already split models: Sonnet for judgment calls, Haiku for orchestration. To cut further: Agent 2's scoring is deterministic — the LLM just orchestrates tool calls. We could replace it with a pure Python loop, saving ~40% of tokens. Or increase batch sizes to reduce round-trips."

### "Add real-time data"
> "Swap the static JSON loaders for API calls. Open-Meteo has a free forecast API. NWS has real-time alerts. The pipeline already handles the target_date parameter — change it to 'now' and add a cron trigger."

### "What about false positives in social media?"
> "That's why we built signal-to-noise into the data. Agent 1 uses LLM judgment specifically for sarcasm detection — 'Dallas heat got me dying' is filtered differently from 'my elderly neighbor hasn't answered the door in two days.' Only 100 of 2,400 posts pass the filter."

### "Why H3 hexagons instead of zip codes?"
> "Zip codes are irregular shapes designed for mail delivery, not emergency response. H3 hexagons are uniform — every hex is the same size (~1.2 km), has the same 6 neighbors, and supports ring-based distance calculations. This is critical for the optimization solver: 'within 2 hex rings' is a precise, consistent metric."

### "What's the conflict scenario?"
> "NWS uses Heat Index — at 109F in Dallas, they classify it as 'Extreme Danger.' OSHA uses Wet Bulb Globe Temperature (WBGT), which accounts for humidity, wind, and solar radiation differently. The same conditions can be 'Extreme Danger' by one standard and 'moderate work restriction' by another. Agent 2 surfaces this conflict in its justifications, citing both sources."

---

## Demo Recovery Plans

### If the pipeline takes too long
- Show the pre-loaded result from an earlier run
- "The pipeline takes about 7 minutes end-to-end. Here's a completed run from earlier today."

### If the pipeline errors
- Show the error in the agent panel
- "This is real-world infrastructure — Bedrock rate limits can cause retries. Here's a successful run from our 20+ test executions."
- Show the CloudWatch error metric: "Our observability catches this — you can see the error rate in the dashboard."

### If the frontend doesn't load
- Show screenshots
- Open the API directly: `https://b5wnyxsvm4.execute-api.us-east-1.amazonaws.com/health`

---

## Key Numbers to Know

| Metric | Value |
|--------|-------|
| Pipeline duration | ~7 min average |
| Token usage | ~800K per run |
| Estimated cost | ~$2-4 per analysis |
| Hex grid | 341 hexes (resolution 7, ~1.2 km each) |
| Population covered | 1.69M across 209 census-mapped hexes |
| Data sources | 12 datasets (7 real, 2 synthetic, 3 reference) |
| Terraform resources | 47 |
| Test count | 60+ (pytest + ESLint + tsc) |
| Total PRs merged | 55+ |
| Successful pipeline runs | 20+ |
