"""H3 hexagonal geocoding utility for HEATWAVE.

Converts lat/lon coordinates from 911 dispatch, weather stations,
and social media posts into H3 hex cell IDs for spatial aggregation.
Shared by all three agents in the pipeline.
"""

import logging
import h3
from collections import defaultdict
from typing import Optional

logger = logging.getLogger(__name__)

H3_RESOLUTION = 7  # ~1.2 km hexagons (neighborhood scale)

# Dallas zip code centroids for geocoding social media posts that only have zip.
# Covers the 8 weather station zips + additional Dallas zips from 911 data.
DALLAS_ZIP_COORDS: dict[str, tuple[float, float]] = {
    "75201": (32.7876, -96.7985),
    "75204": (32.7934, -96.7781),
    "75211": (32.7341, -96.8745),
    "75215": (32.7406, -96.7597),
    "75217": (32.7216, -96.6761),
    "75220": (32.8608, -96.8896),
    "75228": (32.7841, -96.6453),
    "75243": (32.9065, -96.7485),
    "75238": (32.8641, -96.6879),
    "75241": (32.6534, -96.7748),
    "75287": (33.0078, -96.8207),
    "75219": (32.8058, -96.8107),
    "75226": (32.7770, -96.7700),
    "75227": (32.7545, -96.6907),
    "75232": (32.6716, -96.8388),
    "75235": (32.8248, -96.8465),
    "75247": (32.8134, -96.8731),
}


def latlng_to_hex(lat: float, lon: float, resolution: int = H3_RESOLUTION) -> str:
    """Convert a lat/lon pair to an H3 hex cell ID."""
    return h3.latlng_to_cell(lat, lon, resolution)


def hex_to_center(hex_id: str) -> tuple[float, float]:
    """Return the (lat, lon) center of an H3 hex cell."""
    return h3.cell_to_latlng(hex_id)


def hex_to_boundary(hex_id: str) -> list[tuple[float, float]]:
    """Return the boundary polygon vertices as [(lat, lon), ...] for rendering."""
    return list(h3.cell_to_boundary(hex_id))


def get_hex_neighbors(hex_id: str) -> list[str]:
    """Return adjacent hex cell IDs (for cluster detection)."""
    return [h for h in h3.grid_disk(hex_id, 1) if h != hex_id]


def geocode_911_records(
    records: list[dict],
    zip_coords: Optional[dict[str, tuple[float, float]]] = None,
) -> tuple[list[dict], int]:
    """Enrich 911 dispatch records with hex_id.

    Strategy: try geocoded_column lat/lon first, fall back to zip_code lookup.
    Returns: (enriched_records, skip_count)
    """
    lookup = zip_coords or DALLAS_ZIP_COORDS
    enriched = []
    skipped = 0
    for record in records:
        lat, lon = None, None

        # Primary: geocoded_column
        geo = record.get("geocoded_column")
        if geo:
            try:
                lat = float(geo["latitude"])
                lon = float(geo["longitude"])
            except (KeyError, TypeError, ValueError):
                lat, lon = None, None

        # Fallback: zip_code lookup
        if lat is None:
            zip_code = record.get("zip_code")
            if zip_code and str(zip_code) in lookup:
                lat, lon = lookup[str(zip_code)]

        if lat is not None:
            enriched.append({**record, "hex_id": latlng_to_hex(lat, lon)})
        else:
            skipped += 1

    if skipped:
        logger.warning("911 geocoding: %d records skipped (no coords or zip)", skipped)
    return enriched, skipped


def geocode_weather_records(records: list[dict]) -> list[dict]:
    """Enrich weather station records with hex_id from top-level lat/lon."""
    enriched = []
    for record in records:
        try:
            lat = float(record["lat"])
            lon = float(record["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        enriched.append({**record, "hex_id": latlng_to_hex(lat, lon)})
    return enriched


def geocode_social_media_posts(
    posts: list[dict],
    zip_coords: Optional[dict[str, tuple[float, float]]] = None,
) -> list[dict]:
    """Enrich social media posts with hex_id using zip code lookup.

    Posts with a recognized zip get a hex_id. Posts without a zip are
    kept in the output (no hex_id) so Agent 1 can examine the text
    for location clues.
    """
    lookup = zip_coords or DALLAS_ZIP_COORDS
    enriched = []
    located = 0
    for post in posts:
        zip_code = post.get("zip")
        if zip_code and str(zip_code) in lookup:
            lat, lon = lookup[str(zip_code)]
            enriched.append({**post, "hex_id": latlng_to_hex(lat, lon)})
            located += 1
        else:
            enriched.append({**post})  # no hex_id — needs agent reasoning

    unlocated = len(enriched) - located
    if unlocated:
        logger.info(
            "Social media geocoding: %d/%d posts unlocated (no zip) — "
            "left for Agent 1 text analysis",
            unlocated, len(enriched),
        )
    return enriched


def aggregate_by_hex(records: list[dict]) -> dict[str, dict]:
    """Group hex-tagged records by hex_id and return counts + record lists.

    Returns: {hex_id: {"count": int, "records": [...]}}
    """
    groups: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        hex_id = record.get("hex_id")
        if hex_id:
            groups[hex_id].append(record)
    return {
        hex_id: {"count": len(recs), "records": recs}
        for hex_id, recs in groups.items()
    }
