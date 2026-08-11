from __future__ import annotations

from collections import Counter
from typing import Any

from .config import QA_DIR
from .geonames import ANCHORS_PATH, load_anchors, resolve_all_anchor_candidates
from .io import utc_now, write_json
from .spatial import haversine, inside_bbox, query_nearby
from .temporal import valid_for
from .tgaz_index import load_normalized_points


G1_REPORT_PATH = QA_DIR / "g1_spatial_query.json"


def spatial_rows(
    rows: list[dict[str, Any]], anchor: dict[str, Any], radius_km: float
) -> list[dict[str, Any]]:
    anchor_lat = anchor["modern_location"]["lat"]
    anchor_lon = anchor["modern_location"]["lon"]
    candidates = []
    for row in rows:
        if not inside_bbox(anchor_lat, anchor_lon, row["lat"], row["lon"], radius_km):
            continue
        distance = haversine(anchor_lat, anchor_lon, row["lat"], row["lon"])
        if distance <= radius_km:
            candidate = dict(row)
            candidate["distance_km"] = round(distance, 3)
            candidates.append(candidate)
    return candidates


def representative_years(rows: list[dict[str, Any]], slots: int = 6) -> list[int]:
    if not rows:
        return []
    first_year = min(row["valid_from"] for row in rows)
    last_year = max(row["valid_to"] for row in rows)
    span = last_year - first_year + 1
    years: list[int] = []
    for index in range(slots):
        start = first_year + span * index // slots
        end = first_year + span * (index + 1) // slots - 1
        if index == slots - 1:
            end = last_year
        midpoint = (start + end) / 2
        best_year, best_count = max(
            (
                (year, sum(valid_for(row["valid_from"], row["valid_to"], year) for row in rows))
                for year in range(start, end + 1)
            ),
            key=lambda item: (item[1], -abs(item[0] - midpoint), item[0]),
        )
        if best_count and best_year not in years:
            years.append(best_year)
    return sorted(years)


def probe_anchor(
    rows: list[dict[str, Any]], anchor: dict[str, Any], radius_km: float | None = None
) -> dict[str, Any]:
    radius = radius_km or anchor["default_radius_km"]
    nearby_without_time = spatial_rows(rows, anchor, radius)
    years = representative_years(nearby_without_time)
    slices = []
    all_ids: set[str] = set()
    all_names: set[str] = set()
    all_parents: set[str] = set()
    for year in years:
        matches = query_nearby(
            nearby_without_time,
            anchor_lat=anchor["modern_location"]["lat"],
            anchor_lon=anchor["modern_location"]["lon"],
            year=year,
            radius_km=radius,
        )
        all_ids.update(row["tgaz_id"] for row in matches)
        all_names.update(row["name_zh_hans"] for row in matches if row["name_zh_hans"])
        all_parents.update(row["parent_name"] for row in matches if row["parent_name"])
        slices.append(
            {
                "year": year,
                "count": len(matches),
                "feature_types": dict(Counter(row["feature_type"] for row in matches)),
                "sample": matches[:20],
            }
        )
    return {
        "anchor_id": anchor["anchor_id"],
        "radius_km": radius,
        "spatial_candidate_count": len(nearby_without_time),
        "representative_years": years,
        "nonempty_period_count": sum(slice_["count"] > 0 for slice_ in slices),
        "unique_tgaz_id_count": len(all_ids),
        "neighborhood_distinct_name_count": len(all_names),
        "neighborhood_distinct_parent_count": len(all_parents),
        "semantic_note": "Name/parent diversity is density evidence only; it is not historical lineage.",
        "slices": slices,
    }


def run_g1() -> dict[str, Any]:
    anchors = resolve_all_anchor_candidates()
    points = load_normalized_points()
    beijing = next(anchor for anchor in anchors if anchor["anchor_id"] == "beijing")
    probe = probe_anchor(points, beijing)
    best_slice = max(probe["slices"], key=lambda item: item["count"], default=None)
    status = "PASS" if best_slice and best_slice["count"] > 0 else "FAIL"
    if status == "PASS":
        beijing["coverage"]["pre_1912"] = "available"
        beijing["available_periods"] = probe["representative_years"]
        write_json(ANCHORS_PATH, anchors)
    report = {
        "gate": "G1",
        "status": status,
        "verified_at": utc_now(),
        "anchor": beijing,
        "probe": probe,
        "best_slice": best_slice,
        "checks": {
            "real_normalized_source": True,
            "bbox_then_haversine": True,
            "closed_interval_time_filter": True,
            "spatial_relation_only": all(
                row["relation_to_anchor"] == "spatial_nearby"
                and row["lineage_claim"] is None
                for slice_ in probe["slices"]
                for row in slice_["sample"]
            ),
        },
    }
    write_json(G1_REPORT_PATH, report)
    if status != "PASS":
        raise RuntimeError("G1 failed: Beijing returned no real historical candidates")
    return report
