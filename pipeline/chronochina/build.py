from __future__ import annotations

from typing import Any

from .assertions import select_preferred_location
from .config import PROCESSED_DIR, QA_DIR
from .geonames import load_anchors
from .identity import feature_identity_violations
from .io import read_json, utc_now, write_json
from .spatial import haversine
from .temporal import parse_year, valid_for
from .tgaz_detail import G2_REPORT_PATH, load_parsed_detail
from .tgaz_index import load_normalized_points


G4_REPORT_PATH = QA_DIR / "g4_first_map_dataset.json"
LOCATION_CONFLICT_REPORT_PATH = QA_DIR / "location_assertion_conflicts.json"


def _parents_valid_for(detail: dict[str, Any], year: int) -> list[dict[str, Any]]:
    parents = []
    for parent in detail["relationships"]["part_of"]:
        begin = parse_year(parent.get("begin year", parent.get("begin_year")))
        end = parse_year(parent.get("end year", parent.get("end_year")))
        if begin is None or end is None or valid_for(begin, end, year):
            parents.append(parent)
    return parents


def build_feature(
    row: dict[str, Any],
    detail: dict[str, Any],
    anchor: dict[str, Any],
    year: int,
    *,
    detail_path: str | None = None,
    canonical_location_source: str = "tgaz_canonical_api",
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    assertions = [
        {
            "source_id": "tgaz_csv_snapshot",
            "source_record_id": row["tgaz_id"],
            "lon": row["lon"],
            "lat": row["lat"],
            "valid_from": row["valid_from"],
            "valid_to": row["valid_to"],
            "canonical_source": True,
            "confidence": None,
            "accuracy_radius_m": None,
            "fallback_rank": 1 if canonical_location_source == "tgaz_csv_snapshot" else 2,
            "source_url": row["source_url"],
        },
        {
            "source_id": "tgaz_canonical_api",
            "source_record_id": detail["tgaz_id"],
            "lon": detail["location"]["lon"],
            "lat": detail["location"]["lat"],
            "valid_from": detail["temporal"]["valid_from"],
            "valid_to": detail["temporal"]["valid_to"],
            "canonical_source": True,
            "confidence": None,
            "accuracy_radius_m": None,
            "fallback_rank": 1 if canonical_location_source == "tgaz_canonical_api" else 2,
            "source_url": detail["canonical_uri"],
        },
    ]
    selection = select_preferred_location(assertions, year)
    selected = selection["selected"]
    distance_km = haversine(
        anchor["modern_location"]["lat"],
        anchor["modern_location"]["lon"],
        selected["lat"],
        selected["lon"],
    )
    name = (
        detail["names"]["simplified_chinese"]
        or detail["names"]["traditional_chinese"]
        or row["name_zh_hans"]
    )
    feature_type = detail["feature_type"]["name"] or row["feature_type"]
    parents = _parents_valid_for(detail, year)
    parent_name = parents[0].get("name") if parents else row["parent_name"]
    location_confidence = (
        "unresolved_conflict"
        if selection["status"] == "unresolved_conflict"
        else "source_point"
    )
    properties = {
        "tgaz_id": row["tgaz_id"],
        "name": name,
        "name_pinyin": detail["names"]["pinyin"] or row["name_pinyin"],
        "feature_type": feature_type,
        "valid_from": detail["temporal"]["valid_from"],
        "valid_to": detail["temporal"]["valid_to"],
        "parent_name": parent_name,
        "distance_to_anchor_km": round(distance_km, 3),
        "relation_to_anchor": "spatial_nearby",
        "lineage_claim": None,
        "location_confidence": location_confidence,
        "location_assertion_status": selection["status"],
        "source_id": "tgaz_chgis",
        "source_record_id": row["tgaz_id"],
        "source_url": detail["canonical_uri"],
        "license": detail["source"]["license"],
        "detail_path": detail_path or f"details/{row['tgaz_id']}.json",
    }
    feature = {
        "type": "Feature",
        "id": row["tgaz_id"],
        "geometry": {"type": "Point", "coordinates": [selected["lon"], selected["lat"]]},
        "properties": properties,
    }
    detail_card = {
        **properties,
        "names": detail["names"],
        "feature_type_detail": detail["feature_type"],
        "parent_units": detail["relationships"]["part_of"],
        "subordinate_units": detail["relationships"]["subordinate_units"],
        "preceded_by_evidence": detail["relationships"]["preceded_by"],
        "source": detail["source"],
        "canonical_uri": detail["canonical_uri"],
        "location_assertion": selection,
        "semantic_notice": "Spatial neighborhood only; no historical-lineage claim is made.",
    }
    conflict = {
        "tgaz_id": row["tgaz_id"],
        "year": year,
        "status": selection["status"],
        "selection_reason": selection["selection_reason"],
        "selected_source_id": selected["source_id"],
        "competing_assertions": selection["competing_assertions"],
        "newest_write_wins_used": False,
    }
    return feature, detail_card, conflict


def run_g4() -> dict[str, Any]:
    g2 = read_json(G2_REPORT_PATH)
    year = g2["selection"]["year"]
    sampled_ids = g2["selection"]["sampled_ids"]
    rows_by_id = {row["tgaz_id"]: row for row in load_normalized_points()}
    anchor = next(anchor for anchor in load_anchors() if anchor["anchor_id"] == "beijing")
    features = []
    details = []
    conflicts = []
    for tgaz_id in sampled_ids:
        row = rows_by_id.get(tgaz_id)
        detail = load_parsed_detail(tgaz_id)
        if row is None or detail is None:
            continue
        feature, detail_card, conflict = build_feature(row, detail, anchor, year)
        features.append(feature)
        details.append(detail_card)
        conflicts.append(conflict)

    slice_path = PROCESSED_DIR / "anchors" / "beijing" / "slices" / f"{year}.geojson"
    manifest_path = PROCESSED_DIR / "anchors" / "beijing" / "manifest.json"
    feature_collection = {
        "type": "FeatureCollection",
        "metadata": {
            "generated_at": utc_now(),
            "anchor_id": "beijing",
            "year": year,
            "radius_km": anchor["default_radius_km"],
            "coverage_status": "available",
            "relation_semantics": "spatial_nearby only",
        },
        "features": features,
    }
    write_json(slice_path, feature_collection)
    for detail in details:
        write_json(PROCESSED_DIR / "details" / f"{detail['tgaz_id']}.json", detail)
    manifest = {
        **anchor,
        "available_periods": [year],
        "coverage": {
            "pre_1912": "available",
            "1912_1949": "not_yet_integrated",
            "post_1949": "not_yet_integrated",
        },
        "slices": {str(year): f"anchors/beijing/slices/{year}.geojson"},
    }
    write_json(manifest_path, manifest)
    write_json(
        LOCATION_CONFLICT_REPORT_PATH,
        {
            "generated_at": utc_now(),
            "selection_order": [
                "valid time",
                "canonical source",
                "confidence",
                "accuracy radius",
                "unresolved_conflict with deterministic display fallback",
            ],
            "newest_write_wins_used": False,
            "records": conflicts,
        },
    )
    identity_violations = [
        {"tgaz_id": feature["id"], "violations": found}
        for feature in features
        if (found := feature_identity_violations(feature["properties"]))
    ]
    report = {
        "gate": "G4",
        "status": "DATA_READY" if features and len(features) == len(details) else "FAIL",
        "verified_at": utc_now(),
        "anchor_id": "beijing",
        "year": year,
        "feature_count": len(features),
        "detail_count": len(details),
        "source_traceable_count": sum(
            bool(feature["properties"]["source_record_id"] and feature["properties"]["source_url"])
            for feature in features
        ),
        "identity_violations": identity_violations,
        "location_status_counts": {
            status: sum(conflict["status"] == status for conflict in conflicts)
            for status in sorted({conflict["status"] for conflict in conflicts})
        },
        "slice_path": str(slice_path),
        "manifest_path": str(manifest_path),
        "remaining_for_pass": "Build and verify the minimal point/label/detail-card map UI.",
    }
    write_json(G4_REPORT_PATH, report)
    if report["status"] == "FAIL" or identity_violations:
        raise RuntimeError("G4 data build failed")
    return report
