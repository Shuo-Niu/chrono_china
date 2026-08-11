import pytest

from chronochina.spatial import haversine, inside_bbox, query_nearby


def test_haversine_zero_distance() -> None:
    assert haversine(39.9, 116.4, 39.9, 116.4) == 0


def test_haversine_one_degree_at_equator() -> None:
    assert haversine(0, 0, 0, 1) == pytest.approx(111.195, abs=0.01)


def test_bbox_handles_longitude_wrap() -> None:
    assert inside_bbox(0, 179.9, 0, -179.9, 30)


def test_query_applies_time_radius_and_identity_safety() -> None:
    structural_rows = [
        {"tgaz_id": "inside", "lat": 30.0, "lon": 120.1, "valid_from": -10, "valid_to": 10},
        {"tgaz_id": "outside_radius", "lat": 31.0, "lon": 120.0, "valid_from": -10, "valid_to": 10},
        {"tgaz_id": "outside_time", "lat": 30.0, "lon": 120.0, "valid_from": 11, "valid_to": 20},
    ]
    result = query_nearby(
        structural_rows,
        anchor_lat=30.0,
        anchor_lon=120.0,
        year=0,
        radius_km=20,
    )
    assert [row["tgaz_id"] for row in result] == ["inside"]
    assert result[0]["relation_to_anchor"] == "spatial_nearby"
    assert result[0]["lineage_claim"] is None
    assert "predecessor_of" not in result[0]
    assert "renamed_to" not in result[0]
