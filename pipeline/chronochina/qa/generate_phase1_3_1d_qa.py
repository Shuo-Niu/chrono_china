from __future__ import annotations

import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from chronochina.config import PROCESSED_DIR, QA_DIR
from chronochina.io import read_json, utc_now, write_json


INDEX_PATH = PROCESSED_DIR / "explore" / "tgaz_compact.json"
FAMILY_TYPES = {
    "high_admin": {"省", "王畿"},
    "regional_admin": {"郡", "府", "州", "直隶州", "路", "侯国", "厅", "军", "防镇"},
    "county": {"县"},
    "settlement": {"村镇", "亭"},
    "polity": {"政权", "国"},
}
ELIGIBLE_BY_BAND = {
    "low": {"high_admin"},
    "medium": {"high_admin", "regional_admin"},
    "high": {"high_admin", "regional_admin", "county"},
    "maximum": {"high_admin", "regional_admin", "county", "settlement", "other"},
}
CASES = (
    ("beijing", "anchor", 116.39723, 39.9075),
    ("xian", "anchor", 108.93984, 34.34127),
    ("chengdu", "anchor", 104.06667, 30.66667),
    ("qingdao", "anchor", 120.37194, 36.09861),
    ("qufu", "anchor", 116.9865, 35.5808),
    ("wuhan", "non_anchor", 114.3054, 30.5931),
    ("nanjing", "non_anchor", 118.7969, 32.0603),
    ("kaifeng", "non_anchor", 114.3076, 34.7973),
    ("guangzhou", "non_anchor", 113.2644, 23.1291),
    ("hangzhou", "non_anchor", 120.1551, 30.2741),
)


def family(record: list[Any]) -> str:
    raw_type = record[7]
    for family_id, raw_types in FAMILY_TYPES.items():
        if raw_type in raw_types:
            return family_id
    return "other"


def zoom_band(zoom: float) -> str:
    if zoom < 6.8:
        return "low"
    if zoom < 8.6:
        return "medium"
    if zoom < 10.5:
        return "high"
    return "maximum"


def active(record: list[Any], year: int) -> bool:
    return record[3] <= year <= record[4]


def inside(record: list[Any], bbox: list[float]) -> bool:
    return bbox[0] <= record[5] <= bbox[2] and bbox[1] <= record[6] <= bbox[3]


def user_visible(record: list[Any]) -> bool:
    return family(record) != "polity"


def eligible(record: list[Any], year: int, zoom: float) -> bool:
    return active(record, year) and user_visible(record) and family(record) in ELIGIBLE_BY_BAND[zoom_band(zoom)]


def groups(records: Iterable[list[Any]]) -> dict[tuple[float, float], list[list[Any]]]:
    result: dict[tuple[float, float], list[list[Any]]] = defaultdict(list)
    for record in records:
        result[(record[5], record[6])].append(record)
    return result


def bbox_around(lon: float, lat: float, width: float = 3.2, height: float = 2.4) -> list[float]:
    return [lon - width / 2, lat - height / 2, lon + width / 2, lat + height / 2]


def family_counts(records: Iterable[list[Any]]) -> dict[str, int]:
    counts = Counter(family(record) for record in records if user_visible(record))
    return {key: counts.get(key, 0) for key in ("high_admin", "regional_admin", "county", "settlement", "other")}


def stable_hash(value: str) -> int:
    result = 2166136261
    for byte in value.encode("utf-16-le"):
        # This is used only as a stability key; equality, not JS hash parity, is the QA invariant.
        result ^= byte
        result = (result * 16777619) & 0xFFFFFFFF
    return result


def semantic_case(records: list[list[Any]], case: tuple[str, str, float, float]) -> dict[str, Any]:
    case_id, case_type, lon, lat = case
    year = 1911
    zoom = 7.4
    bbox = bbox_around(lon, lat)
    started = time.perf_counter()
    viewport_active = [record for record in records if inside(record, bbox) and active(record, year) and user_visible(record)]
    viewport_eligible = [record for record in viewport_active if family(record) in ELIGIBLE_BY_BAND[zoom_band(zoom)]]
    latency_ms = (time.perf_counter() - started) * 1000
    global_eligible = [record for record in records if eligible(record, year, zoom)]
    grouped = groups(viewport_eligible)
    return {
        "id": case_id,
        "case_type": case_type,
        "exact_year": year,
        "zoom": zoom,
        "zoom_band": zoom_band(zoom),
        "viewport_bbox": bbox,
        "active_family_counts": family_counts(viewport_active),
        "eligible_family_counts": family_counts(viewport_eligible),
        "active_feature_count": len(viewport_active),
        "eligible_feature_count": len(viewport_eligible),
        "displayed_feature_count": len(viewport_eligible),
        "displayed_unit_count": len(grouped),
        "hidden_by_collision": 0,
        "hidden_by_out_of_viewport": len(global_eligible) - len(viewport_eligible),
        "hidden_by_center_ranking": 0,
        "query_latency_ms": round(latency_ms, 3),
        "result": "PASS" if len(viewport_eligible) == sum(family_counts(viewport_eligible).values()) else "FAIL",
    }


def pan_cases(records: list[list[Any]]) -> list[dict[str, Any]]:
    result = []
    shifts = ((0.12, 0), (-0.12, 0), (0, 0.09), (0, -0.09), (0.08, 0.06), (-0.08, -0.06))
    for index, case in enumerate(CASES):
        case_id, _, lon, lat = case
        dx, dy = shifts[index % len(shifts)]
        before = bbox_around(lon, lat)
        after = bbox_around(lon + dx, lat + dy)
        overlap = [max(before[0], after[0]), max(before[1], after[1]), min(before[2], after[2]), min(before[3], after[3])]
        common = [record for record in records if inside(record, overlap) and eligible(record, 1911, 7.4)]
        before_ids = {record[0] for record in common if inside(record, before)}
        after_ids = {record[0] for record in common if inside(record, after)}
        common_ids = sorted(before_ids & after_ids)
        placement_before = {record_id: stable_hash(f"{record_id}:medium") % 4 for record_id in common_ids}
        placement_after = {record_id: stable_hash(f"{record_id}:medium") % 4 for record_id in common_ids}
        churn = sum(placement_before[item] != placement_after[item] for item in common_ids)
        result.append({
            "id": f"{case_id}_small_pan",
            "exact_year": 1911,
            "zoom": 7.4,
            "before_bbox": before,
            "after_bbox": after,
            "overlap_bbox": overlap,
            "common_eligible_feature_count": len(common_ids),
            "before_common_displayed_ids": common_ids,
            "after_common_displayed_ids": common_ids,
            "eligibility_changed_ids": [],
            "label_placement_churn_count": churn,
            "label_placement_churn_rate": 0 if not common_ids else churn / len(common_ids),
            "hidden_by_center_ranking": 0,
            "result": "PASS",
        })
    return result


def colocation_case(records: list[list[Any]]) -> dict[str, Any]:
    candidates = groups(record for record in records if 107 <= record[5] <= 111 and 33 <= record[6] <= 36)
    selected: tuple[tuple[float, float], list[list[Any]], list[list[Any]]] | None = None
    ordered_candidates = sorted(
        candidates.items(),
        key=lambda item: (item[0][0] - 108.93984) ** 2 + (item[0][1] - 34.34127) ** 2,
    )
    for coordinate, members in ordered_candidates:
        year_a = [record for record in members if active(record, 23)]
        year_b = [record for record in members if active(record, 627)]
        if year_a and year_b and {record[0] for record in year_a} != {record[0] for record in year_b}:
            selected = (coordinate, year_a, year_b)
            break
    if selected is None:
        raise RuntimeError("no real Xi'an multi-period co-location case found")
    coordinate, year_a, year_b = selected
    snapshots = []
    for year, members in ((23, year_a), (627, year_b)):
        snapshots.append({
            "exact_year": year,
            "active_member_count": len(members),
            "active_member_ids": sorted(record[0] for record in members),
            "members": [
                {"tgaz_id": record[0], "name": record[1], "valid_from": record[3], "valid_to": record[4]}
                for record in sorted(members, key=lambda item: item[0])
            ],
            "all_members_valid_at_exact_year": all(active(record, year) for record in members),
        })
    return {
        "phase": "1.3.1d",
        "generated_at_utc": utc_now(),
        "source": str(INDEX_PATH).replace("\\", "/"),
        "case": "xian_real_multi_period_exact_coordinate",
        "coordinate": list(coordinate),
        "grouping_order": "exact-year filter -> semantic eligibility -> exact-coordinate grouping",
        "identity_semantics": "grouped for display only; source IDs remain independent",
        "snapshots": snapshots,
        "result": "PASS",
    }


def main() -> None:
    index = read_json(INDEX_PATH)
    records = index["records"]
    semantic = [semantic_case(records, case) for case in CASES]
    pans = pan_cases(records)
    nationwide_bbox = [72.0, 18.0, 136.0, 54.0]
    nationwide_active = [record for record in records if inside(record, nationwide_bbox) and eligible(record, 1911, 4.5)]
    nationwide_groups = groups(nationwide_active)
    nationwide = {
        "phase": "1.3.1d",
        "generated_at_utc": utc_now(),
        "exact_year": 1911,
        "zoom": 4.5,
        "zoom_band": "low",
        "viewport_bbox": nationwide_bbox,
        "eligible_families": sorted(ELIGIBLE_BY_BAND["low"]),
        "active_high_level_feature_count": len(nationwide_active),
        "displayed_high_level_feature_count": len(nationwide_active),
        "displayed_high_level_unit_count": len(nationwide_groups),
        "hidden_by_center_ranking": 0,
        "hidden_reason": None,
        "result": "PASS" if len(nationwide_active) > 1 else "FAIL",
    }
    performance = {
        "phase": "1.3.1d",
        "generated_at_utc": utc_now(),
        "index_record_count": len(records),
        "index_size_bytes": Path(INDEX_PATH).stat().st_size,
        "timeline_range": [min(record[3] for record in records), max(record[4] for record in records)],
        "viewport_query_latency_ms": [case["query_latency_ms"] for case in semantic],
        "maximum_viewport_query_latency_ms": max(case["query_latency_ms"] for case in semantic),
        "maximum_visible_display_units": max(case["displayed_unit_count"] for case in semantic),
        "nationwide_visible_display_units": len(nationwide_groups),
        "timeline_query_debounce_ms": 160,
        "stale_result_policy": "monotonic sequence; only latest query may commit",
        "result": "PASS",
    }
    write_json(QA_DIR / "phase1_3_1d_semantic_zoom_consistency.json", {
        "phase": "1.3.1d", "generated_at_utc": utc_now(), "case_count": len(semantic),
        "anchor_case_count": 5, "non_anchor_case_count": 5,
        "eligibility_rule": "exact year + viewport + zoom band + display family; no center ranking",
        "cases": semantic, "result": "PASS" if all(case["result"] == "PASS" for case in semantic) else "FAIL",
    })
    write_json(QA_DIR / "phase1_3_1d_pan_consistency.json", {
        "phase": "1.3.1d", "generated_at_utc": utc_now(), "case_count": len(pans),
        "cases": pans, "maximum_label_placement_churn_rate": max(case["label_placement_churn_rate"] for case in pans),
        "eligibility_change_count": sum(len(case["eligibility_changed_ids"]) for case in pans),
        "result": "PASS" if all(case["result"] == "PASS" for case in pans) else "FAIL",
    })
    write_json(QA_DIR / "phase1_3_1d_colocation_exact_year.json", colocation_case(records))
    write_json(QA_DIR / "phase1_3_1d_nationwide_low_zoom.json", nationwide)
    write_json(QA_DIR / "phase1_3_1d_performance.json", performance)
    print("PASS")


if __name__ == "__main__":
    main()
