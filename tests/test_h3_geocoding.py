"""Tests for backend.utils.h3_geocoding module."""

import pytest
from backend.utils.h3_geocoding import (
    H3_RESOLUTION,
    latlng_to_hex,
    hex_to_center,
    hex_to_boundary,
    get_hex_neighbors,
    geocode_911_records,
    geocode_weather_records,
    geocode_social_media_posts,
    aggregate_by_hex,
)

# --- Dallas coordinates for test fixtures ---
DALLAS_LAT, DALLAS_LON = 32.7767, -96.7970  # downtown Dallas


# ---- Core H3 wrapper tests ----

class TestCoreH3:
    def test_latlng_to_hex_returns_valid_hex(self):
        hex_id = latlng_to_hex(DALLAS_LAT, DALLAS_LON)
        assert isinstance(hex_id, str)
        assert len(hex_id) > 0

    def test_latlng_to_hex_resolution(self):
        hex_id = latlng_to_hex(DALLAS_LAT, DALLAS_LON)
        # H3 v4: resolution can be read back from the cell
        import h3
        assert h3.get_resolution(hex_id) == H3_RESOLUTION

    def test_hex_to_center_returns_lat_lon(self):
        hex_id = latlng_to_hex(DALLAS_LAT, DALLAS_LON)
        lat, lon = hex_to_center(hex_id)
        # Center should be close to the original point
        assert abs(lat - DALLAS_LAT) < 0.05
        assert abs(lon - DALLAS_LON) < 0.05

    def test_hex_to_boundary_returns_polygon(self):
        hex_id = latlng_to_hex(DALLAS_LAT, DALLAS_LON)
        boundary = hex_to_boundary(hex_id)
        assert len(boundary) == 6  # hexagons have 6 vertices
        for point in boundary:
            assert len(point) == 2  # (lat, lon)

    def test_get_hex_neighbors_returns_six(self):
        hex_id = latlng_to_hex(DALLAS_LAT, DALLAS_LON)
        neighbors = get_hex_neighbors(hex_id)
        assert len(neighbors) == 6
        assert hex_id not in neighbors  # should not include self

    def test_same_location_same_hex(self):
        """Two nearby points in the same hex cell should produce the same ID."""
        hex_a = latlng_to_hex(32.7767, -96.7970)
        hex_b = latlng_to_hex(32.7768, -96.7971)
        assert hex_a == hex_b

    def test_distant_locations_different_hex(self):
        downtown = latlng_to_hex(32.7767, -96.7970)
        north_dallas = latlng_to_hex(33.0078, -96.8207)
        assert downtown != north_dallas


# ---- 911 geocoding tests ----

class TestGeocode911:
    def test_geocoded_column_primary(self):
        """Records with geocoded_column lat/lon get hex_id."""
        records = [{
            "incidentnum": "TEST-001",
            "geocoded_column": {"latitude": "32.7216", "longitude": "-96.6761"},
            "zip_code": "75217",
        }]
        enriched, skipped = geocode_911_records(records)
        assert len(enriched) == 1
        assert "hex_id" in enriched[0]
        assert skipped == 0

    def test_zip_fallback(self):
        """Records missing geocoded_column fall back to zip_code lookup."""
        records = [{
            "incidentnum": "TEST-002",
            "zip_code": "75217",
        }]
        enriched, skipped = geocode_911_records(records)
        assert len(enriched) == 1
        assert "hex_id" in enriched[0]
        assert skipped == 0

    def test_skip_no_coords_no_zip(self):
        """Records with neither coords nor zip are skipped and counted."""
        records = [{"incidentnum": "TEST-003"}]
        enriched, skipped = geocode_911_records(records)
        assert len(enriched) == 0
        assert skipped == 1

    def test_skip_unknown_zip(self):
        """Records with an unrecognized zip (not in lookup) are skipped."""
        records = [{"incidentnum": "TEST-004", "zip_code": "99999"}]
        enriched, skipped = geocode_911_records(records)
        assert len(enriched) == 0
        assert skipped == 1

    def test_bad_geocoded_column_falls_back(self):
        """If geocoded_column has bad data, fall back to zip."""
        records = [{
            "incidentnum": "TEST-005",
            "geocoded_column": {"latitude": "not_a_number", "longitude": "bad"},
            "zip_code": "75217",
        }]
        enriched, skipped = geocode_911_records(records)
        assert len(enriched) == 1
        assert skipped == 0

    def test_preserves_original_fields(self):
        """Enriched records keep all original fields."""
        records = [{
            "incidentnum": "TEST-006",
            "signal": "HEAT",
            "geocoded_column": {"latitude": "32.7216", "longitude": "-96.6761"},
        }]
        enriched, _ = geocode_911_records(records)
        assert enriched[0]["incidentnum"] == "TEST-006"
        assert enriched[0]["signal"] == "HEAT"


# ---- Weather geocoding tests ----

class TestGeocodeWeather:
    def test_enriches_with_hex(self):
        records = [{
            "station_id": "WX-DAL-SOUTHEAST",
            "lat": 32.7216,
            "lon": -96.6761,
            "temp_f": 105.0,
        }]
        enriched = geocode_weather_records(records)
        assert len(enriched) == 1
        assert "hex_id" in enriched[0]
        assert enriched[0]["temp_f"] == 105.0

    def test_skips_missing_coords(self):
        records = [{"station_id": "WX-BROKEN"}]
        enriched = geocode_weather_records(records)
        assert len(enriched) == 0


# ---- Social media geocoding tests ----

class TestGeocodeSocialMedia:
    def test_post_with_zip_gets_hex(self):
        posts = [{"id": "tw-001", "text": "its hot", "zip": "75217"}]
        enriched = geocode_social_media_posts(posts)
        assert len(enriched) == 1
        assert "hex_id" in enriched[0]

    def test_post_without_zip_kept_no_hex(self):
        """Posts without zip stay in output for Agent 1 text analysis."""
        posts = [{"id": "tw-002", "text": "power out in SE Dallas"}]
        enriched = geocode_social_media_posts(posts)
        assert len(enriched) == 1
        assert "hex_id" not in enriched[0]
        assert enriched[0]["text"] == "power out in SE Dallas"

    def test_mixed_posts(self):
        """Mix of located and unlocated posts."""
        posts = [
            {"id": "tw-001", "text": "hot", "zip": "75217"},
            {"id": "tw-002", "text": "power out in SE Dallas"},
            {"id": "tw-003", "text": "tacos", "zip": "99999"},  # unknown zip
        ]
        enriched = geocode_social_media_posts(posts)
        assert len(enriched) == 3  # all kept
        located = [p for p in enriched if "hex_id" in p]
        assert len(located) == 1  # only the known zip


# ---- Aggregation tests ----

class TestAggregateByHex:
    def test_groups_by_hex(self):
        hex_id = latlng_to_hex(DALLAS_LAT, DALLAS_LON)
        records = [
            {"hex_id": hex_id, "type": "911"},
            {"hex_id": hex_id, "type": "weather"},
        ]
        result = aggregate_by_hex(records)
        assert hex_id in result
        assert result[hex_id]["count"] == 2

    def test_skips_records_without_hex(self):
        records = [
            {"hex_id": "abc123", "type": "a"},
            {"type": "no_hex"},
        ]
        result = aggregate_by_hex(records)
        assert len(result) == 1

    def test_empty_input(self):
        result = aggregate_by_hex([])
        assert result == {}
