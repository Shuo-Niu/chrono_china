from __future__ import annotations

from copy import deepcopy

from shapely.geometry import box

from chronochina.qa.geographic_plausibility import (
    PlausibilityConfig,
    WaterMosaic,
    classify_feature,
    classify_point,
    deduplicate_occurrences,
    safe_v6_crosscheck,
)


CONFIG = PlausibilityConfig(boundary_uncertainty_km=0.2)
MOSAIC = WaterMosaic.from_geometries(
    marine=box(0, 0, 1, 1),
    inland_by_class={"lake": box(2, 0, 3, 1)},
    origin_lon=0,
    origin_lat=0,
)


def feature(tgaz_id: str = "hvd_1") -> dict:
    return {
        "id": tgaz_id,
        "geometry": {"type": "Point", "coordinates": [4.0, 4.0]},
        "properties": {
            "tgaz_id": tgaz_id,
            "name": "测试县",
            "feature_type": "县",
            "valid_from": 1,
            "valid_to": 10,
        },
    }


def test_point_on_land() -> None:
    result = classify_point(4, 4, MOSAIC, config=CONFIG)
    assert result["classification"] == "modern_land"
    assert result["distance_to_modern_land_km"] == 0


def test_point_in_marine_water_and_distance_to_land() -> None:
    result = classify_point(0.5, 0.5, MOSAIC, config=CONFIG)
    assert result["classification"] == "modern_water"
    assert result["water_membership"] == "marine"
    assert result["distance_to_modern_land_km"] > 50


def test_point_in_inland_water_preserves_unknown_origin() -> None:
    result = classify_point(2.5, 0.5, MOSAIC, config=CONFIG)
    assert result["classification"] == "modern_water"
    assert result["water_type"] == "modern_inland_water_unknown_origin"
    assert result["water_classes"] == ["lake"]


def test_point_near_coastline_is_boundary_uncertain() -> None:
    result = classify_point(1.001, 0.5, MOSAIC, config=CONFIG)
    assert result["classification"] == "boundary_uncertain"
    assert result["triage"] == "boundary_review"


def test_missing_geometry_is_unknown() -> None:
    result = classify_point(1, 1, None)
    assert result["classification"] == "unknown"
    assert result["reason"] == "geometry_unavailable"


def test_invalid_coordinate_is_unknown() -> None:
    result = classify_point(999, "bad", MOSAIC)
    assert result["classification"] == "unknown"
    assert result["reason"] == "invalid_coordinate"


def test_classification_is_deterministic_and_does_not_mutate_feature() -> None:
    source = feature()
    source["geometry"]["coordinates"] = [0.5, 0.5]
    before = deepcopy(source)
    first = classify_feature(source, MOSAIC, config=CONFIG)
    second = classify_feature(source, MOSAIC, config=CONFIG)
    assert first == second
    assert source == before


def test_duplicate_feature_across_snapshots_is_one_unique_feature() -> None:
    observation = {"classification": "modern_water"}
    rows = [
        {
            "tgaz_id": "hvd_1",
            "name": "测试县",
            "occurrence_key": "a|1|hvd_1",
            "longitude": 1.0,
            "latitude": 2.0,
            "geometry_observation": observation,
        },
        {
            "tgaz_id": "hvd_1",
            "name": "测试县",
            "occurrence_key": "a|2|hvd_1",
            "longitude": 1.0,
            "latitude": 2.0,
            "geometry_observation": observation,
        },
    ]
    unique = deduplicate_occurrences(rows)
    assert len(unique) == 1
    assert unique[0]["occurrence_count"] == 2
    assert unique[0]["coordinate_consistent_across_occurrences"] is True


def test_v6_crosscheck_requires_exact_instance_metadata() -> None:
    source = feature()
    exact = {
        "tgaz_id": "hvd_1",
        "name_simplified": "测试县",
        "name_traditional": "測試縣",
        "feature_type": "县",
        "valid_from": 1,
        "valid_to": 10,
        "present_location": "测试",
        "longitude": 4.1,
        "latitude": 4.1,
        "source": "V6",
    }
    assert safe_v6_crosscheck(source, exact)["reliable_match"] is True

    mismatch = {**exact, "valid_from": 2}
    result = safe_v6_crosscheck(source, mismatch)
    assert result["reliable_match"] is False
    assert result["match_status"] == "exact_id_metadata_conflict"


def test_v6_crosscheck_never_uses_name_only_fuzzy_match() -> None:
    result = safe_v6_crosscheck(feature("hvd_999"), None)
    assert result["match_status"] == "no_exact_id_match"
    assert result["match_confidence"] == "none"
