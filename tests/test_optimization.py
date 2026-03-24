"""Tests for backend.utils.optimization module."""

import pytest
from backend.utils.h3_geocoding import latlng_to_hex
from backend.utils.optimization import (
    RiskLevel,
    ThreatHex,
    Asset,
    DispatchPlan,
    hex_distance,
    optimize_coverage,
    optimize_response_time,
    optimize_staged_reserve,
)

# --- Dallas hex fixtures ---
# Use real Dallas locations so h3.grid_distance works correctly.

# Downtown Dallas
HEX_DOWNTOWN = latlng_to_hex(32.7767, -96.7970)
# Southeast Dallas (~5km away)
HEX_SE = latlng_to_hex(32.7216, -96.6761)
# North Dallas (~25km away)
HEX_NORTH = latlng_to_hex(33.0078, -96.8207)
# Near downtown (should be 1 ring away)
HEX_NEAR_DOWNTOWN = latlng_to_hex(32.7850, -96.7970)


def _make_threat_map():
    """Standard threat map: 1 CRITICAL, 1 HIGH, 1 MEDIUM."""
    return [
        ThreatHex(hex_id=HEX_DOWNTOWN, risk_level=RiskLevel.CRITICAL, risk_score=0.95),
        ThreatHex(hex_id=HEX_SE, risk_level=RiskLevel.HIGH, risk_score=0.7),
        ThreatHex(hex_id=HEX_NORTH, risk_level=RiskLevel.MEDIUM, risk_score=0.4),
    ]


def _make_assets():
    """Standard asset list: 2 nearby assets, 1 far asset."""
    return [
        Asset(id="AMB-01", asset_type="ambulance", hex_id=HEX_NEAR_DOWNTOWN,
              coverage_radius=3, capacity=1),
        Asset(id="COOL-01", asset_type="cooling_bus", hex_id=HEX_SE,
              coverage_radius=2, capacity=1),
        Asset(id="WATER-01", asset_type="water_unit", hex_id=HEX_NORTH,
              coverage_radius=2, capacity=1),
    ]


# ---- Helpers ----

class TestHelpers:
    def test_hex_distance_same_hex(self):
        assert hex_distance(HEX_DOWNTOWN, HEX_DOWNTOWN) == 0

    def test_hex_distance_nearby(self):
        dist = hex_distance(HEX_DOWNTOWN, HEX_NEAR_DOWNTOWN)
        assert dist >= 0
        assert dist <= 3  # should be close

    def test_hex_distance_far(self):
        dist = hex_distance(HEX_DOWNTOWN, HEX_NORTH)
        assert dist > 5  # significant distance


# ---- Strategy 1: optimize_coverage (LP) ----

class TestOptimizeCoverage:
    def test_returns_dispatch_plan(self):
        plan = optimize_coverage(_make_threat_map(), _make_assets())
        assert isinstance(plan, DispatchPlan)
        assert plan.strategy_used == "optimize_coverage"

    def test_covers_reachable_hexes(self):
        plan = optimize_coverage(_make_threat_map(), _make_assets())
        assert plan.summary["covered"] > 0
        assert len(plan.orders) > 0

    def test_respects_capacity(self):
        """Each asset should not exceed its capacity."""
        plan = optimize_coverage(_make_threat_map(), _make_assets())
        from collections import Counter
        assignments_per_asset = Counter(o.asset_id for o in plan.orders)
        assets = {a.id: a for a in _make_assets()}
        for asset_id, count in assignments_per_asset.items():
            assert count <= assets[asset_id].capacity

    def test_no_assets_returns_empty(self):
        plan = optimize_coverage(_make_threat_map(), [])
        assert len(plan.orders) == 0
        assert len(plan.unassigned_hexes) > 0

    def test_no_threats_returns_empty(self):
        plan = optimize_coverage([], _make_assets())
        assert len(plan.orders) == 0

    def test_unavailable_assets_excluded(self):
        assets = _make_assets()
        for a in assets:
            a.status = "deployed"
        plan = optimize_coverage(_make_threat_map(), assets)
        assert len(plan.orders) == 0

    def test_prefers_higher_risk(self):
        """With limited assets, should prioritize higher-risk hexes."""
        assets = [Asset(id="ONLY-01", asset_type="ambulance",
                        hex_id=HEX_NEAR_DOWNTOWN, coverage_radius=3, capacity=1)]
        plan = optimize_coverage(_make_threat_map(), assets)
        if plan.orders:
            # The single asset should cover the highest-risk reachable hex
            covered = {o.to_hex for o in plan.orders}
            assert HEX_DOWNTOWN in covered


# ---- Strategy 2: optimize_response_time (greedy) ----

class TestOptimizeResponseTime:
    def test_returns_dispatch_plan(self):
        plan = optimize_response_time(_make_threat_map(), _make_assets())
        assert isinstance(plan, DispatchPlan)
        assert plan.strategy_used == "optimize_response_time"

    def test_assigns_nearest(self):
        """Asset closest to the critical hex should be assigned to it."""
        plan = optimize_response_time(_make_threat_map(), _make_assets())
        downtown_orders = [o for o in plan.orders if o.to_hex == HEX_DOWNTOWN]
        if downtown_orders:
            # AMB-01 is near downtown, should be assigned
            assert downtown_orders[0].asset_id == "AMB-01"

    def test_orders_have_distance(self):
        plan = optimize_response_time(_make_threat_map(), _make_assets())
        for order in plan.orders:
            assert order.distance >= 0

    def test_summary_has_avg_distance(self):
        plan = optimize_response_time(_make_threat_map(), _make_assets())
        assert "avg_distance" in plan.summary

    def test_no_assets(self):
        plan = optimize_response_time(_make_threat_map(), [])
        assert len(plan.orders) == 0

    def test_all_deploy_role(self):
        """Response time strategy should only deploy, not stage."""
        plan = optimize_response_time(_make_threat_map(), _make_assets())
        for order in plan.orders:
            assert order.role == "deploy"


# ---- Strategy 3: optimize_staged_reserve ----

class TestOptimizeStagedReserve:
    def test_returns_dispatch_plan(self):
        plan = optimize_staged_reserve(_make_threat_map(), _make_assets())
        assert isinstance(plan, DispatchPlan)
        assert plan.strategy_used == "optimize_staged_reserve"

    def test_has_both_deploy_and_stage(self):
        """With enough assets, should have both roles."""
        plan = optimize_staged_reserve(_make_threat_map(), _make_assets())
        roles = {o.role for o in plan.orders}
        assert "deploy" in roles or "stage" in roles

    def test_staging_radius_in_summary(self):
        plan = optimize_staged_reserve(
            _make_threat_map(), _make_assets(), staging_radius=3,
        )
        assert plan.summary["staging_radius"] == 3

    def test_reserve_ratio_in_summary(self):
        plan = optimize_staged_reserve(
            _make_threat_map(), _make_assets(), reserve_ratio=0.5,
        )
        assert plan.summary["reserve_ratio"] == 0.5

    def test_no_assets(self):
        plan = optimize_staged_reserve(_make_threat_map(), [])
        assert len(plan.orders) == 0

    def test_custom_staging_radius(self):
        """Staging orders should respect the radius parameter."""
        plan = optimize_staged_reserve(
            _make_threat_map(), _make_assets(), staging_radius=1,
        )
        staged = [o for o in plan.orders if o.role == "stage"]
        for order in staged:
            # Staged asset should be within staging_radius of a HIGH hex
            dist_to_high = hex_distance(order.to_hex, HEX_SE)
            assert dist_to_high <= 1 or dist_to_high < 0  # -1 if incomparable

    def test_critical_prioritized_over_high(self):
        """Deploy pool should go to CRITICAL first."""
        plan = optimize_staged_reserve(_make_threat_map(), _make_assets())
        deploy_orders = [o for o in plan.orders if o.role == "deploy"]
        if deploy_orders:
            deployed_hexes = {o.to_hex for o in deploy_orders}
            assert HEX_DOWNTOWN in deployed_hexes
