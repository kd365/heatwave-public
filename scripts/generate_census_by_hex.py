"""Generate dallas_census_by_hex.json with centroid-based tract-to-hex assignment.

Each census tract is assigned to exactly one H3 hex based on its centroid.
No double-counting: each person counted once.

Data sources:
- Census Bureau ACS 5-year (2022): tract-level population + age brackets
- Census Bureau TIGER/Line: tract centroids (internal point lat/lon)

Usage:
    python scripts/generate_census_by_hex.py

Output:
    data/reference/dallas_census_by_hex.json
"""

import json
import os
import requests
import h3
from collections import defaultdict

# Census Bureau API — no key required for small queries
CENSUS_API = "https://api.census.gov/data/2022/acs/acs5"
DALLAS_COUNTY_FIPS = "113"
TEXAS_FIPS = "48"

# ACS variables
VARIABLES = [
    "B01003_001E",  # total pop
    "B01001_020E", "B01001_021E", "B01001_022E", "B01001_023E", "B01001_024E", "B01001_025E",  # male 65+
    "B01001_044E", "B01001_045E", "B01001_046E", "B01001_047E", "B01001_048E", "B01001_049E",  # female 65+
]
ELDERLY_VARS = VARIABLES[1:]

H3_RESOLUTION = 7


def fetch_census_data():
    """Fetch tract-level population + elderly data for Dallas County."""
    params = {
        "get": ",".join(["NAME"] + VARIABLES),
        "for": "tract:*",
        "in": f"state:{TEXAS_FIPS} county:{DALLAS_COUNTY_FIPS}",
    }
    resp = requests.get(CENSUS_API, params=params)
    resp.raise_for_status()
    rows = resp.json()
    header = rows[0]
    data = {}
    for row in rows[1:]:
        rec = dict(zip(header, row))
        total_pop = int(rec.get("B01003_001E") or 0)
        elderly = sum(int(rec.get(v) or 0) for v in ELDERLY_VARS)
        tract_fips = f"{rec['state']}{rec['county']}{rec['tract']}"
        data[tract_fips] = {
            "population": total_pop,
            "elderly_65plus": elderly,
        }
    print(f"Fetched {len(data)} census tracts")
    print(f"Total county population: {sum(d['population'] for d in data.values()):,}")
    return data


def fetch_tract_centroids():
    """Fetch tract internal point (centroid) coordinates from Census TIGER gazetteer."""
    # Census gazetteer files have centroids for all tracts
    url = f"https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2020_Gazetteer/2020_gaz_tracts_{TEXAS_FIPS}.txt"
    print("Downloading tract centroids from Census gazetteer...")
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()

    centroids = {}
    lines = resp.text.strip().split("\n")
    header = [h.strip() for h in lines[0].split("\t")]
    for line in lines[1:]:
        fields = [f.strip() for f in line.split("\t")]
        if len(fields) < len(header):
            continue
        rec = dict(zip(header, fields))
        geoid = rec.get("GEOID", "")
        # Filter to Dallas County
        if not geoid.startswith(f"{TEXAS_FIPS}{DALLAS_COUNTY_FIPS}"):
            continue
        try:
            lat = float(rec.get("INTPTLAT", ""))
            lon = float(rec.get("INTPTLONG", ""))
            centroids[geoid] = (lat, lon)
        except ValueError:
            continue

    print(f"Found {len(centroids)} Dallas County tract centroids")
    return centroids


def get_hex_grid():
    """Load the Dallas H3 hex grid."""
    grid_path = os.path.join(os.path.dirname(__file__), "..", "data", "reference", "dallas_hex_grid.json")
    with open(grid_path) as f:
        return set(json.load(f))


def assign_tracts_to_hexes(census_data, centroids, hex_grid):
    """Assign each tract to exactly one hex based on centroid location."""
    hex_pop = defaultdict(lambda: {"population": 0, "elderly_65plus": 0, "tract_count": 0})

    matched = 0
    outside_grid = 0
    no_centroid = 0

    for tract_id, pop_data in census_data.items():
        if tract_id not in centroids:
            no_centroid += 1
            continue

        lat, lon = centroids[tract_id]
        hex_id = h3.latlng_to_cell(lat, lon, H3_RESOLUTION)

        if hex_id not in hex_grid:
            outside_grid += 1
            continue

        hex_pop[hex_id]["population"] += pop_data["population"]
        hex_pop[hex_id]["elderly_65plus"] += pop_data["elderly_65plus"]
        hex_pop[hex_id]["tract_count"] += 1
        matched += 1

    print(f"Matched {matched} tracts to hex grid")
    print(f"Outside grid: {outside_grid}, No centroid: {no_centroid}")
    return dict(hex_pop)


def main():
    print("=== Generating centroid-based census-by-hex (no double counting) ===\n")

    census_data = fetch_census_data()
    centroids = fetch_tract_centroids()
    hex_grid = get_hex_grid()
    print(f"Hex grid: {len(hex_grid)} hexes\n")

    hex_pop = assign_tracts_to_hexes(census_data, centroids, hex_grid)

    # Build output
    output = []
    for hex_id, data in hex_pop.items():
        pop = data["population"]
        elderly = data["elderly_65plus"]
        if pop == 0:
            continue
        pct = round(elderly / pop * 100, 1) if pop > 0 else 0
        output.append({
            "hex_id": hex_id,
            "population": pop,
            "elderly_65plus": elderly,
            "pct_elderly": pct,
            "tract_count": data["tract_count"],
        })

    output.sort(key=lambda x: x["population"], reverse=True)

    total_pop = sum(d["population"] for d in output)
    total_elderly = sum(d["elderly_65plus"] for d in output)
    print(f"\n=== Results ===")
    print(f"Hexes with population: {len(output)} / {len(hex_grid)}")
    print(f"Total population: {total_pop:,}")
    print(f"Total elderly 65+: {total_elderly:,}")
    print(f"Avg pop/hex: {total_pop / len(output):,.0f}")
    print(f"Dallas County actual: ~2,604,053 (ACS 2022)")
    print(f"Coverage: {total_pop / 2604053 * 100:.1f}% of county within hex grid")

    out_path = os.path.join(os.path.dirname(__file__), "..", "data", "reference", "dallas_census_by_hex.json")
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nWritten to {out_path}")


if __name__ == "__main__":
    main()
