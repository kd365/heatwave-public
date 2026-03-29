# HEATWAVE — Issues Encountered & Resolved

## Infrastructure & Deployment

### 1. Lambda deploy package too large (PR #51, #52)
**Problem:** Adding the `data/` directory to the Lambda zip included 50MB of PDFs (CDC, UHI Study, DFR Report), pushing the package over Lambda's 70MB limit.
**Root cause:** `cp -r data package/` copied everything — PDFs are for the Bedrock Knowledge Base (S3), not Lambda.
**Fix:** Copy only `.json` files from `data/raw`, `data/synthetic`, `data/reference`. PDFs stay in S3 for the KB to index; Lambda never reads them directly.

### 2. Lambda missing data files entirely (PR #51, #53)
**Problem:** Agent 1 returned only 90 hex events instead of 341. The hex grid, census, and weather files weren't on Lambda.
**Root cause:** The deploy workflow (`deploy-backend.yml`) only copied `backend/` — the `data/` directory was never included.
**Fix:** Added `data/**` JSON copy to deploy workflow. Also added `data/**` and `.github/workflows/deploy-backend.yml` to the workflow trigger paths so data changes trigger deploys.

### 3. Deploy workflow didn't trigger on its own changes (PR #53)
**Problem:** PR #52 fixed the deploy script but the deploy never ran after merge.
**Root cause:** Workflow trigger paths only included `backend/**` and `requirements.txt`. Changing the workflow file itself didn't match.
**Fix:** Added `.github/workflows/deploy-backend.yml` to the trigger paths.

### 4. h3 Linux wheel incompatibility on Mac (Day 1)
**Problem:** `pip install --target` for Lambda packaging installed Mac-native h3 binaries. Lambda runs Linux.
**Root cause:** h3 has Cython extensions that are platform-specific. `--only-binary=:all:` skips h3 entirely; downloading the Linux wheel and `pip install`-ing it refuses on Mac.
**Fix:** Download Linux wheel separately, unzip directly into package directory: `pip download h3 --platform manylinux2014_x86_64 --only-binary=:all: -d /tmp && unzip -o /tmp/h3-*.whl -d dist/package`. CI/CD now handles this with `--platform manylinux2014_x86_64` flag.

### 5. API Gateway missing cancel route (PR #55)
**Problem:** Cancel button returned 404. Backend code was deployed but API Gateway didn't have the route.
**Root cause:** API Gateway uses explicit routes (not a catch-all proxy). The `POST /api/v1/runs/{run_id}/cancel` route wasn't defined in Terraform or API Gateway.
**Fix:** Added route via AWS CLI for immediate effect, plus Terraform config for permanence.

### 6. IAM permissions missing for Bedrock Guardrail (Day 3)
**Problem:** Pipeline failed with `AccessDeniedException` on `bedrock:ApplyGuardrail`.
**Root cause:** Partner added guardrail to Agent 2 but the Lambda execution role didn't have the `bedrock:ApplyGuardrail` permission.
**Fix:** Manually added IAM policy. Flagged for Terraform-ification.

---

## Agent 1: Spatial Triage

### 7. Monolithic LLM call exceeded context window (Phase 4 design)
**Problem:** First attempt sent all 10,500+ records (weather + 911 + 311 + social) in a single LLM call.
**Root cause:** 4,608 weather + 4,482 311 + 1,035 911 + 300 social = too much for any context window.
**Fix:** Analyzed each data source's actual need for LLM judgment. Result: only 911 narratives and social media need LLM. Weather and 311 are deterministic. Reduced from 10,500 records to ~350 records sent to LLM across 3 calls.

### 8. Batch processing exceeded Lambda timeout (Phase 4 design)
**Problem:** Second attempt batched records (500/batch) — 9 LLM calls × 90 seconds = exceeded Lambda's 15-minute timeout.
**Fix:** Eliminated LLM calls for weather and 311 entirely. Final design: 3 LLM calls total, ~2-3 minutes.

### 9. Weather data missing on cool days (PR #61)
**Problem:** Aug 16 (peak 94.2F) showed `temp: 0` for every hex. No weather data on the map at all.
**Root cause:** `_process_weather` only returned events above the 95F threshold. On a day that peaked at 94.2F, zero events passed, so the station lookup was empty and every hex got zeros.
**Fix:** Added `station_observations` — returns ALL daily station data regardless of threshold. The synthesizer uses these for hex interpolation so every hex gets real temperature data even on cool days.

### 10. 96% of hexes had zero temperature (Day 2)
**Problem:** Only 7 hexes (with direct weather stations) had temperature data. The other 334 showed `max_temp_f: 0`.
**Root cause:** No interpolation — hexes without a weather station got nothing.
**Fix:** Nearest-station weather interpolation. Each hex gets the temperature from its closest weather station (by H3 grid distance) + UHI adjustment based on the Dallas Urban Heat Island Study. Documented as an approximation with `weather_source: "interpolated_nearest_station_uhi_adjusted"`.

---

## Agent 2: Threat Assessment

### 11. No CRITICAL or HIGH hexes on 109F peak day (PR #54)
**Problem:** On the hottest day of the year, every hex scored MEDIUM or LOW. Max score was 0.555.
**Root cause:** Weather was weighted at 40% with a linear 85-115F ramp. Even at 112F apparent, weather contributed only 0.36 to the total. Reaching HIGH (0.65) required perfect scores across all components.
**Fix:** Reweighted: weather 50% with nonlinear ramp (steep above 105F), aggravating factors 25%. Adjusted thresholds: CRITICAL >= 0.82, HIGH >= 0.65, MEDIUM >= 0.45.

### 12. Aggravating factors always zero (PR #54)
**Problem:** The scoring tool expected boolean flags (`has_vulnerable_population`, `nighttime_temp_above_80`, `multi_source_corroboration`) from the LLM. Haiku never passed them.
**Root cause:** The tool schema listed these as optional booleans. Haiku (orchestrating the batch calls) skipped them, defaulting to `false`.
**Fix:** Auto-derive aggravating factors from hex data in Python: elderly population > 0, pct_elderly >= 10%, apparent temp >= 110F, 2+ incident source types. LLM no longer needs to compute or pass these.

### 13. 32 unscored hexes (PR #54)
**Problem:** Agent 2 scored 309 of 341 hexes. 32 edge hexes were missing from the threat map.
**Root cause:** System prompt said "use 6-9 batches for 170 hexes." With 341 hexes, the LLM stopped after ~9 batches thinking it was done.
**Fix:** Updated prompt to say "keep scoring until every hex is covered." Added post-LLM backfill step that deterministically scores any hexes the LLM missed. Increased `max_turns` from 25 to 35.

### 14. Census population inflated by double-counting (PR #58)
**Problem:** Total population was 1.9M but Dallas County is 2.6M and city proper is 1.3M. Some hexes showed 28K population.
**Root cause:** Census tracts were assigned to every hex they overlapped. A tract spanning 3 hexes had its full population counted 3 times.
**Fix:** Rebuilt census data using centroid-based assignment — each tract centroid maps to exactly one hex. New total: 2.32M (89% of county, zero double-counting). Created reproducible `scripts/generate_census_by_hex.py`.

---

## Agent 3: Dispatch Commander

### 15. Agent 3 deploying 30 assets on all-LOW day (PR #61)
**Problem:** On Aug 16 (cool day, all hexes LOW), Agent 3 still deployed 30 mobile assets.
**Root cause:** System prompt had no guidance for an all-LOW scenario. The LLM tried to be helpful and deployed anyway.
**Fix:** Added "NO DEPLOYMENT" option to system prompt: if all hexes are LOW, recommend standby posture with normal staffing instead of running optimization.

---

## Frontend / UX

### 16. UI showed stale results from previous run (PR #50)
**Problem:** After a run completed, the map didn't update. Still showed old data.
**Root cause:** React Query cache wasn't invalidated when run status transitioned from RUNNING to COMPLETE.
**Fix:** Added `useEffect` that watches `runStatus.status` — when it transitions RUNNING → COMPLETE, invalidates result, runs, and latestRun queries.

### 17. Old run showing on page refresh (PR #50)
**Problem:** Refreshing the page loaded an old completed run instead of the most recent one.
**Root cause:** `fetchLatestRun` used `runs.find(r => r.status === 'COMPLETE')` which returned the first COMPLETE run. The `useEffect` guard (`!activeRunId`) prevented updates.
**Fix:** Query invalidation on run completion. Initial load syncs to latest run's date.

### 18. Date selector stuck on latest run's date (PR #62)
**Problem:** Selecting a different date in the dropdown redirected back to the latest run's date.
**Root cause:** The `useEffect` that synced `targetDate` to the latest run kept re-firing whenever `activeRunId` was set to null (by the date cache miss).
**Fix:** Added `initialLoadDone` ref so the sync only runs once on first page load, never again.

### 19. Map not clearing when switching to uncached date (PR #60)
**Problem:** Switching to a date with no cached run still showed the previous date's hex grid and results.
**Root cause:** The date cache lookup set `activeRunId` when a cached run was found, but did nothing when no cache existed — leaving the old run's data on screen.
**Fix:** Added `else { setActiveRunId(null) }` to clear the active run when no cache match exists.

### 20. Cancel button did nothing (PR #55, API Gateway fix)
**Problem:** Cancel button appeared but clicking it had no visible effect.
**Root cause:** Two issues: (1) API Gateway had no route for the cancel endpoint (returned 404), (2) after cancel, polling stopped so agent status badges froze.
**Fix:** Added API Gateway route via CLI + Terraform. Added cancel notice message and re-enabled Run Analysis button after cancel.

---

## Data

### 21. City pivot from El Paso to Dallas (Day 1)
**Problem:** El Paso didn't have accessible 911 dispatch data with MO narratives.
**Decision:** Pivoted to Dallas — real 911 data available via Dallas Open Data portal, plus a brutal heat wave in August 2023 with 24 consecutive days above 100F.

### 22. Social media data is synthetic (Day 1)
**Problem:** Twitter/X API requires $100/month Basic tier for read access. No budget.
**Decision:** Created synthetic social media posts with deliberate data friction: genuine heat complaints (signal), sarcasm like "Dallas heat got me dying" (noise), and irrelevant posts about tacos and sports (noise). Documented as synthetic in `data/manifest.json`.

### 23. Bedrock rate limiting between agents (Day 3)
**Problem:** Running Agent 2 immediately after Agent 1 caused Bedrock throttling errors.
**Root cause:** Bedrock has per-account rate limits. Three agents making rapid sequential calls exceeded the limit.
**Fix:** Added 60-second cooldowns between agents in the pipeline. This is also where the cancellation check happens — a silver lining from a workaround.
