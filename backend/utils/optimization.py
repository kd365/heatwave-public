"""Dispatch optimization strategies for HEATWAVE Agent 3.

Asset-agnostic solver. The LLM selects which strategy to call and provides
the asset inventory (with constraints like coverage_radius, capacity) based
on FEMA NIMS resource typing guidance from the RAG knowledge base.

Three strategies:
1. optimize_coverage     — LP (PuLP): maximize threat-weighted hex coverage
2. optimize_response_time — greedy nearest: minimize distance to critical hexes
3. optimize_staged_reserve — split deploy: CRITICAL gets assets, reserves stage near HIGH
"""

import logging
from dataclasses import dataclass, field
from enum import Enum

import h3
import pulp


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

class RiskLevel(Enum):
    CRITICAL = 4
    HIGH = 3
    MEDIUM = 2
    LOW = 1


@dataclass
class ThreatHex:
    """A hex cell with a risk assessment from Agent 2."""
    hex_id: str
    risk_level: RiskLevel
    risk_score: float  # 0.0–1.0 continuous score for LP weighting


@dataclass
class Asset:
    """A deployable resource. Schema populated by Agent 3 via RAG."""
    id: str
    asset_type: str          # e.g. "ambulance_als", "cooling_bus"
    hex_id: str              # current/home location
    status: str = "available"
    coverage_radius: int = 1  # hex rings this asset can serve
    capacity: int = 1         # simultaneous incidents/areas it can handle


@dataclass
class DispatchOrder:
    """A single asset assignment."""
    asset_id: str
    from_hex: str            # asset's current location
    to_hex: str              # assigned destination
    distance: int            # hex-ring distance
    role: str = "deploy"     # "deploy" or "stage"


@dataclass
class DispatchPlan:
    """Output of a strategy — the full dispatch plan."""
    strategy_used: str
    orders: list[DispatchOrder] = field(default_factory=list)
    unassigned_hexes: list[str] = field(default_factory=list)
    summary: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def hex_distance(a: str, b: str) -> int:
    """H3 grid distance (hex rings) between two cells. Returns -1 if not comparable."""
    try:
        return h3.grid_distance(a, b)
    except h3.H3ResMismatchError:
        return -1


def _available_assets(assets: list[Asset]) -> list[Asset]:
    """Filter to only available assets."""
    return [a for a in assets if a.status == "available"]


def _hexes_at_risk(threat_map: list[ThreatHex], min_level: RiskLevel) -> list[ThreatHex]:
    """Filter threat hexes at or above a risk level."""
    return [t for t in threat_map if t.risk_level.value >= min_level.value]


# ---------------------------------------------------------------------------
# Strategy 1: optimize_coverage (LP / PuLP)
# ---------------------------------------------------------------------------

def optimize_coverage(
    threat_map: list[ThreatHex],
    assets: list[Asset],
) -> DispatchPlan:
    """Maximize threat-weighted hex coverage under asset constraints.

    Best when: many critical hexes, scarce assets.
    Uses linear programming (PuLP) to assign assets to hexes such that
    total covered threat weight is maximized.
    """
    available = _available_assets(assets)
    targets = _hexes_at_risk(threat_map, RiskLevel.MEDIUM)

    if not available or not targets:
        return DispatchPlan(
            strategy_used="optimize_coverage",
            unassigned_hexes=[t.hex_id for t in targets],
            summary={"reason": "no available assets or no targets"},
        )

    # Precompute which (asset, hex) pairs are reachable
    reachable: dict[str, list[tuple[Asset, int]]] = {}
    for t in targets:
        reachable[t.hex_id] = []
        for a in available:
            dist = hex_distance(a.hex_id, t.hex_id)
            if dist >= 0 and dist <= a.coverage_radius:
                reachable[t.hex_id].append((a, dist))

    # LP model
    prob = pulp.LpProblem("dispatch_coverage", pulp.LpMaximize)

    # Decision variables: x[asset_id][hex_id] = 1 if asset assigned to hex
    x = {}
    for a in available:
        x[a.id] = {}
        for t in targets:
            x[a.id][t.hex_id] = pulp.LpVariable(
                f"x_{a.id}_{t.hex_id}", cat="Binary",
            )

    # y[hex_id] = 1 if hex is covered by at least one asset
    y = {}
    for t in targets:
        y[t.hex_id] = pulp.LpVariable(f"y_{t.hex_id}", cat="Binary")

    # Objective: maximize sum of risk_score * y[hex]
    prob += pulp.lpSum(t.risk_score * y[t.hex_id] for t in targets)

    # Constraint: hex can only be covered if a reachable asset is assigned
    for t in targets:
        reachable_assets = [a for a, _ in reachable.get(t.hex_id, [])]
        prob += y[t.hex_id] <= pulp.lpSum(
            x[a.id][t.hex_id] for a in reachable_assets
        )
        # Only allow assignment if reachable
        for a in available:
            if a not in reachable_assets:
                prob += x[a.id][t.hex_id] == 0

    # Constraint: each asset assigned to at most `capacity` hexes
    for a in available:
        prob += pulp.lpSum(x[a.id][t.hex_id] for t in targets) <= a.capacity

    prob.solve(pulp.PULP_CBC_CMD(msg=0))

    # Build dispatch plan from solution
    orders = []
    covered_hexes = set()
    for a in available:
        for t in targets:
            if pulp.value(x[a.id][t.hex_id]) and pulp.value(x[a.id][t.hex_id]) > 0.5:
                dist = hex_distance(a.hex_id, t.hex_id)
                orders.append(DispatchOrder(
                    asset_id=a.id,
                    from_hex=a.hex_id,
                    to_hex=t.hex_id,
                    distance=dist,
                    role="deploy",
                ))
                covered_hexes.add(t.hex_id)

    unassigned = [t.hex_id for t in targets if t.hex_id not in covered_hexes]

    return DispatchPlan(
        strategy_used="optimize_coverage",
        orders=orders,
        unassigned_hexes=unassigned,
        summary={
            "total_targets": len(targets),
            "covered": len(covered_hexes),
            "assets_deployed": len({o.asset_id for o in orders}),
        },
    )


# ---------------------------------------------------------------------------
# Strategy 2: optimize_response_time (greedy nearest)
# ---------------------------------------------------------------------------

def optimize_response_time(
    threat_map: list[ThreatHex],
    assets: list[Asset],
) -> DispatchPlan:
    """Assign nearest available asset to each critical hex.

    Best when: few critical hexes, enough assets.
    Greedy approach — sorts critical hexes by risk score (highest first),
    assigns the closest available asset to each.
    """
    available = _available_assets(assets)
    targets = _hexes_at_risk(threat_map, RiskLevel.HIGH)
    targets.sort(key=lambda t: t.risk_score, reverse=True)

    if not available or not targets:
        return DispatchPlan(
            strategy_used="optimize_response_time",
            unassigned_hexes=[t.hex_id for t in targets],
            summary={"reason": "no available assets or no targets"},
        )

    # Track remaining capacity per asset
    remaining_capacity = {a.id: a.capacity for a in available}
    orders = []
    covered_hexes = set()

    for t in targets:
        # Find closest asset with remaining capacity
        best_asset = None
        best_dist = float("inf")
        for a in available:
            if remaining_capacity[a.id] <= 0:
                continue
            dist = hex_distance(a.hex_id, t.hex_id)
            if dist < 0:
                continue
            if dist < best_dist:
                best_dist = dist
                best_asset = a

        if best_asset:
            orders.append(DispatchOrder(
                asset_id=best_asset.id,
                from_hex=best_asset.hex_id,
                to_hex=t.hex_id,
                distance=best_dist,
                role="deploy",
            ))
            remaining_capacity[best_asset.id] -= 1
            covered_hexes.add(t.hex_id)

    unassigned = [t.hex_id for t in targets if t.hex_id not in covered_hexes]

    return DispatchPlan(
        strategy_used="optimize_response_time",
        orders=orders,
        unassigned_hexes=unassigned,
        summary={
            "total_targets": len(targets),
            "covered": len(covered_hexes),
            "total_distance": sum(o.distance for o in orders),
            "avg_distance": (
                sum(o.distance for o in orders) / len(orders) if orders else 0
            ),
        },
    )


# ---------------------------------------------------------------------------
# Strategy 3: optimize_staged_reserve (split deploy)
# ---------------------------------------------------------------------------

def optimize_staged_reserve(
    threat_map: list[ThreatHex],
    assets: list[Asset],
    staging_radius: int = 2,
    reserve_ratio: float = 0.3,
) -> DispatchPlan:
    """Deploy to CRITICAL hexes, stage reserves near HIGH clusters.

    Best when: uncertain/evolving situation.
    Splits available assets: (1-reserve_ratio) deploy to CRITICAL,
    remainder staged within staging_radius of HIGH cluster centroids.

    Args:
        staging_radius: hex rings from HIGH cluster centroid to stage at.
            Set by the LLM based on situation assessment.
        reserve_ratio: fraction of assets held as reserves (0.0–1.0).
    """
    available = _available_assets(assets)
    critical = _hexes_at_risk(threat_map, RiskLevel.CRITICAL)
    high = [t for t in threat_map if t.risk_level == RiskLevel.HIGH]

    if not available:
        all_targets = critical + high
        return DispatchPlan(
            strategy_used="optimize_staged_reserve",
            unassigned_hexes=[t.hex_id for t in all_targets],
            summary={"reason": "no available assets"},
        )

    # Split assets into deploy pool and reserve pool
    n_reserve = max(1, int(len(available) * reserve_ratio))
    n_deploy = len(available) - n_reserve

    # Sort by distance to nearest critical hex (closest first for deploy)
    def min_dist_to_critical(asset: Asset) -> float:
        if not critical:
            return float("inf")
        dists = [hex_distance(asset.hex_id, t.hex_id) for t in critical]
        valid = [d for d in dists if d >= 0]
        return min(valid) if valid else float("inf")

    available.sort(key=min_dist_to_critical)
    deploy_pool = available[:n_deploy]
    reserve_pool = available[n_deploy:]

    orders = []
    covered_hexes = set()

    # Phase 1: Deploy to CRITICAL (greedy nearest)
    critical.sort(key=lambda t: t.risk_score, reverse=True)
    deploy_capacity = {a.id: a.capacity for a in deploy_pool}

    for t in critical:
        best_asset = None
        best_dist = float("inf")
        for a in deploy_pool:
            if deploy_capacity[a.id] <= 0:
                continue
            dist = hex_distance(a.hex_id, t.hex_id)
            if dist < 0:
                continue
            if dist < best_dist:
                best_dist = dist
                best_asset = a

        if best_asset:
            orders.append(DispatchOrder(
                asset_id=best_asset.id,
                from_hex=best_asset.hex_id,
                to_hex=t.hex_id,
                distance=best_dist,
                role="deploy",
            ))
            deploy_capacity[best_asset.id] -= 1
            covered_hexes.add(t.hex_id)

    # Phase 2: Stage reserves near HIGH clusters
    if high and reserve_pool:
        # Find centroid of HIGH cluster (use the highest-scored HIGH hex)
        high.sort(key=lambda t: t.risk_score, reverse=True)
        staging_targets = high[:len(reserve_pool)]

        for reserve_asset, target in zip(reserve_pool, staging_targets):
            # Find a hex within staging_radius of the HIGH hex
            staging_hex = _find_staging_hex(
                target.hex_id, reserve_asset.hex_id, staging_radius,
            )
            dist = hex_distance(reserve_asset.hex_id, staging_hex)
            orders.append(DispatchOrder(
                asset_id=reserve_asset.id,
                from_hex=reserve_asset.hex_id,
                to_hex=staging_hex,
                distance=dist if dist >= 0 else 0,
                role="stage",
            ))

    unassigned_critical = [t.hex_id for t in critical if t.hex_id not in covered_hexes]

    return DispatchPlan(
        strategy_used="optimize_staged_reserve",
        orders=orders,
        unassigned_hexes=unassigned_critical,
        summary={
            "deployed": len([o for o in orders if o.role == "deploy"]),
            "staged": len([o for o in orders if o.role == "stage"]),
            "critical_covered": len(covered_hexes),
            "critical_total": len(critical),
            "staging_radius": staging_radius,
            "reserve_ratio": reserve_ratio,
        },
    )


def _find_staging_hex(target_hex: str, asset_hex: str, radius: int) -> str:
    """Find a hex within `radius` rings of target that is closest to the asset.

    Returns the best staging position — close to the HIGH cluster but
    reachable from the asset's current location.
    """
    candidates = h3.grid_disk(target_hex, radius)
    best_hex = target_hex
    best_dist = float("inf")

    for candidate in candidates:
        dist = hex_distance(asset_hex, candidate)
        if dist < 0:
            continue
        if dist < best_dist:
            best_dist = dist
            best_hex = candidate

    return best_hex
