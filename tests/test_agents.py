"""Tests for agent tool handlers (no Bedrock calls — tests run locally)."""

import json
import pytest

from backend.agents.agent1_triage import handle_tool as agent1_handle
from backend.agents.agent2_threat import handle_tool as agent2_handle, _score_hex_threat
from backend.agents.agent3_dispatch import handle_tool as agent3_handle, _run_optimization
from backend.utils.h3_geocoding import latlng_to_hex


# ---- Agent 1: Tool Handlers ----

class TestAgent1Tools:
    def test_load_weather(self):
        result = json.loads(agent1_handle("get_weather_data", {}))
        assert result["total_records"] > 0
        assert result["events_above_threshold"] > 0
        assert "by_severity" in result
        assert "weather_events" in result

    def test_load_911(self):
        result = json.loads(agent1_handle("get_911_records", {}))
        assert result["total_records"] == 1276
        assert "heat_candidate_records" in result
        assert result["pre_filtered_count"] > 0

    def test_load_311(self):
        result = json.loads(agent1_handle("get_311_records", {}))
        assert result["total_311_records"] > 0

    def test_load_social(self):
        result = json.loads(agent1_handle("get_social_media", {}))
        assert result["total_posts"] > 0
        assert "posts" in result

    def test_unknown_tool(self):
        result = json.loads(agent1_handle("nonexistent_tool", {}))
        assert "error" in result


# ---- Agent 2: Scoring ----

class TestAgent2Scoring:
    def test_critical_score(self):
        """Hot weather + dispatch + vulnerable population = CRITICAL."""
        result = json.loads(_score_hex_threat({
            "hex_id": "test_hex",
            "max_temp_f": 110,
            "dispatch_count": 5,
            "service_count": 10,
            "social_count": 5,
            "has_vulnerable_population": True,
            "nighttime_temp_above_80": True,
            "multi_source_corroboration": True,
        }))
        assert result["risk_level"] == "CRITICAL"
        assert result["risk_score"] >= 0.85

    def test_low_score(self):
        """Mild weather, no incidents = LOW."""
        result = json.loads(_score_hex_threat({
            "hex_id": "test_hex",
            "max_temp_f": 88,
        }))
        assert result["risk_level"] == "LOW"
        assert result["risk_score"] < 0.40

    def test_medium_score(self):
        """Hot weather + some dispatch signals = MEDIUM."""
        result = json.loads(_score_hex_threat({
            "hex_id": "test_hex",
            "max_temp_f": 105,
            "dispatch_count": 2,
            "service_count": 3,
            "social_count": 1,
        }))
        assert result["risk_level"] == "MEDIUM"

    def test_aggravating_factors_tracked(self):
        result = json.loads(_score_hex_threat({
            "hex_id": "test_hex",
            "max_temp_f": 100,
            "has_vulnerable_population": True,
            "nighttime_temp_above_80": True,
        }))
        assert "vulnerable_population" in result["aggravating_factors"]
        assert "no_nighttime_recovery" in result["aggravating_factors"]

    def test_kb_query_without_env(self):
        """KB query without KNOWLEDGE_BASE_ID returns graceful fallback."""
        result = json.loads(agent2_handle("query_knowledge_base", {
            "query": "WBGT threshold for heat stroke",
        }))
        assert "results" in result or "note" in result


# ---- Agent 3: Optimization Execution ----

class TestAgent3Tools:
    def test_load_assets(self):
        result = json.loads(agent3_handle("get_available_assets", {}))
        assert result["total_assets"] == 101
        assert "mobile_assets" in result
        assert "fixed_facilities" in result

    def test_run_coverage_optimization(self):
        hex_downtown = latlng_to_hex(32.7767, -96.7970)
        hex_se = latlng_to_hex(32.7216, -96.6761)
        hex_near = latlng_to_hex(32.7850, -96.7970)

        result = json.loads(_run_optimization({
            "strategy": "optimize_coverage",
            "threat_hexes": [
                {"hex_id": hex_downtown, "risk_level": "CRITICAL", "risk_score": 0.95},
                {"hex_id": hex_se, "risk_level": "HIGH", "risk_score": 0.7},
            ],
            "assets": [
                {"id": "AMB-01", "asset_type": "ambulance", "hex_id": hex_near,
                 "coverage_radius": 3, "capacity": 1},
                {"id": "AMB-02", "asset_type": "ambulance", "hex_id": hex_se,
                 "coverage_radius": 2, "capacity": 1},
            ],
        }))
        assert result["strategy_used"] == "optimize_coverage"
        assert len(result["orders"]) > 0

    def test_run_response_time_optimization(self):
        hex_downtown = latlng_to_hex(32.7767, -96.7970)
        hex_near = latlng_to_hex(32.7850, -96.7970)

        result = json.loads(_run_optimization({
            "strategy": "optimize_response_time",
            "threat_hexes": [
                {"hex_id": hex_downtown, "risk_level": "CRITICAL", "risk_score": 0.95},
            ],
            "assets": [
                {"id": "AMB-01", "asset_type": "ambulance", "hex_id": hex_near,
                 "coverage_radius": 3, "capacity": 1},
            ],
        }))
        assert result["strategy_used"] == "optimize_response_time"

    def test_run_staged_reserve(self):
        hex_downtown = latlng_to_hex(32.7767, -96.7970)
        hex_se = latlng_to_hex(32.7216, -96.6761)
        hex_near = latlng_to_hex(32.7850, -96.7970)
        hex_north = latlng_to_hex(33.0078, -96.8207)

        result = json.loads(_run_optimization({
            "strategy": "optimize_staged_reserve",
            "threat_hexes": [
                {"hex_id": hex_downtown, "risk_level": "CRITICAL", "risk_score": 0.95},
                {"hex_id": hex_se, "risk_level": "HIGH", "risk_score": 0.7},
            ],
            "assets": [
                {"id": "AMB-01", "asset_type": "ambulance", "hex_id": hex_near,
                 "coverage_radius": 3, "capacity": 1},
                {"id": "AMB-02", "asset_type": "ambulance", "hex_id": hex_north,
                 "coverage_radius": 3, "capacity": 1},
                {"id": "AMB-03", "asset_type": "ambulance", "hex_id": hex_se,
                 "coverage_radius": 2, "capacity": 1},
            ],
            "staging_radius": 2,
            "reserve_ratio": 0.3,
        }))
        assert result["strategy_used"] == "optimize_staged_reserve"

    def test_dispatch_orders_local(self):
        """Dispatch orders without DynamoDB logs locally."""
        result = json.loads(agent3_handle("dispatch_orders", {
            "dispatch_plan": {"orders": [], "strategy": "test"},
        }))
        assert result["status"] == "dispatched"
        assert result["persisted_to"] == "local_log"

    def test_unknown_strategy(self):
        result = json.loads(_run_optimization({
            "strategy": "nonexistent",
            "threat_hexes": [],
            "assets": [],
        }))
        assert "error" in result
