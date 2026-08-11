from __future__ import annotations

from collections import defaultdict
from typing import Any

from .config import QA_DIR
from .geonames import load_anchors
from .io import utc_now, write_json
from .spatial import query_nearby
from .tgaz_index import load_normalized_points


G3_REPORT_PATH = QA_DIR / "g3_identity_safety.json"
FORBIDDEN_AUTOMATIC_RELATIONS = {
    "predecessor_of",
    "successor_of",
    "renamed_to",
    "seat_moved_to",
}


def source_record_identity(record: dict[str, Any]) -> str:
    """Source-record identity never depends on a name or coordinate."""
    return str(record["tgaz_id"])


def feature_identity_violations(feature: dict[str, Any]) -> list[str]:
    violations = []
    if feature.get("relation_to_anchor") != "spatial_nearby":
        violations.append("relation_to_anchor_is_not_spatial_nearby")
    if feature.get("lineage_claim") is not None:
        violations.append("lineage_claim_generated_without_evidence")
    for relation in FORBIDDEN_AUTOMATIC_RELATIONS:
        if relation in feature:
            violations.append(f"forbidden_relation_key:{relation}")
    return violations


def _collision_samples(
    points: list[dict[str, Any]], key_name: str, key_function: Any
) -> dict[str, Any]:
    groups: dict[Any, set[str]] = defaultdict(set)
    for point in points:
        groups[key_function(point)].add(point["tgaz_id"])
    collisions = [(key, ids) for key, ids in groups.items() if key and len(ids) > 1]
    collisions.sort(key=lambda item: (-len(item[1]), str(item[0])))
    return {
        "grouping_key": key_name,
        "collision_group_count": len(collisions),
        "samples": [
            {"value": key, "distinct_tgaz_ids": sorted(ids)[:20], "id_count": len(ids)}
            for key, ids in collisions[:10]
        ],
        "interpretation": "Collision is QA evidence that this field cannot be an identity key; records remain separate.",
    }


def run_g3() -> dict[str, Any]:
    anchors = load_anchors()
    beijing = next(anchor for anchor in anchors if anchor["anchor_id"] == "beijing")
    points = load_normalized_points()
    audited_features = []
    for year in beijing["available_periods"]:
        audited_features.extend(
            query_nearby(
                points,
                anchor_lat=beijing["modern_location"]["lat"],
                anchor_lon=beijing["modern_location"]["lon"],
                year=year,
                radius_km=beijing["default_radius_km"],
            )
        )
    violations = [
        {"tgaz_id": feature["tgaz_id"], "violations": found}
        for feature in audited_features
        if (found := feature_identity_violations(feature))
    ]
    report = {
        "gate": "G3",
        "status": "PASS" if audited_features and not violations else "FAIL",
        "verified_at": utc_now(),
        "audited_real_feature_count": len(audited_features),
        "violations": violations,
        "model_guarantees": {
            "source_record_identity_key": "tgaz_id",
            "coordinate_is_identity_key": False,
            "name_is_identity_key": False,
            "distance_role": "spatial candidate generation only",
            "automatic_relation": "spatial_nearby",
            "historical_lineage_generation": "disabled; evidence required",
            "entity_resolution_phase0": "not performed",
        },
        "real_collision_evidence": {
            "same_name_different_records": _collision_samples(
                points, "name_zh_hans", lambda point: point["name_zh_hans"]
            ),
            "same_coordinate_different_records": _collision_samples(
                points,
                "[lon,lat]",
                lambda point: f"{point['lon']:.6f},{point['lat']:.6f}",
            ),
        },
        "rule_assessment": {
            "nearby_not_same_entity": "verified by real feature audit",
            "coordinate_change_not_new_entity": "protected by excluding coordinate from identity and not performing entity splitting",
            "same_name_not_same_entity": "verified by retaining distinct TGAZ_ID records in real collision groups",
            "different_name_not_different_entity": "protected by excluding name from identity and not performing entity splitting",
            "neighborhood_lineage_separation": "verified by real feature audit",
        },
    }
    write_json(G3_REPORT_PATH, report)
    if report["status"] != "PASS":
        raise RuntimeError(f"G3 failed with {len(violations)} identity-safety violations")
    return report
