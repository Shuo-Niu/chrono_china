from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from .config import PROCESSED_DIR, QA_DIR, TGAZ_INDEX_MANIFEST_PATH
from .g5 import FINAL_ANCHORS_PATH
from .io import read_json, sha256_file, utc_now, write_json
from .phase1 import EXPECTED_ANCHOR_IDS, PERIOD_EVIDENCE_DIR, semantic_sha256
from .spatial import haversine
from .tgaz_index import load_normalized_points


STRATEGY_NEAREST = "nearest_n"
STRATEGY_TYPE_DIVERSE = "type_diverse_distance"
STRATEGY_TYPE_SPATIAL = "type_diverse_spatial"
STRATEGIES = (STRATEGY_NEAREST, STRATEGY_TYPE_DIVERSE, STRATEGY_TYPE_SPATIAL)

PHASE1_1_PROCESSED_DIR = PROCESSED_DIR / "phase1_1"
TYPE_DISTRIBUTION_JSON_PATH = QA_DIR / "phase1_1_feature_type_distribution.json"
TYPE_DISTRIBUTION_MD_PATH = QA_DIR / "phase1_1_feature_type_distribution.md"
COMPARISON_JSON_PATH = QA_DIR / "phase1_1_display_strategy_comparison.json"
COMPARISON_MD_PATH = QA_DIR / "phase1_1_display_strategy_comparison.md"
GENERATION_REPORT_PATH = QA_DIR / "phase1_1_generation.json"
V6_OUTLIERS_PATH = QA_DIR / "v6_parity_outliers.json"


@dataclass(frozen=True)
class DisplayConfig:
    nearest_point_limit: int = 12
    diverse_point_limit: int = 30
    label_limit: int = 12
    spatial_grid_size: int = 4
    collision_canvas_width_px: int = 900
    collision_canvas_height_px: int = 600
    collision_label_height_px: int = 24
    collision_character_width_px: int = 14
    collision_label_padding_px: int = 16


DEFAULT_DISPLAY_CONFIG = DisplayConfig()


def display_type_group(row: dict[str, Any]) -> str:
    """Keep the source feature taxonomy intact at the display layer."""
    return (row.get("feature_type") or "未分类").strip() or "未分类"


def _stable_distance_order(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda row: (row["distance_km"], row["tgaz_id"]))


def rank_nearest(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return _stable_distance_order(rows)


def rank_type_diverse(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Round-robin source types; use distance and ID inside every type."""
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[display_type_group(row)].append(row)
    for group_rows in groups.values():
        group_rows.sort(key=lambda row: (row["distance_km"], row["tgaz_id"]))
    group_names = sorted(
        groups,
        key=lambda name: (
            groups[name][0]["distance_km"],
            groups[name][0]["tgaz_id"],
            name,
        ),
    )
    ranked: list[dict[str, Any]] = []
    round_index = 0
    while True:
        added = False
        for name in group_names:
            if round_index < len(groups[name]):
                ranked.append(groups[name][round_index])
                added = True
        if not added:
            return ranked
        round_index += 1


def rank_type_spatial(
    rows: Iterable[dict[str, Any]], *, limit: int | None = None
) -> list[dict[str, Any]]:
    """Seed one nearby record per type, then greedily spread remaining points."""
    base = rank_type_diverse(rows)
    if not base:
        return []
    target_count = min(len(base), limit if limit is not None else len(base))
    base_rank = {row["tgaz_id"]: index for index, row in enumerate(base)}
    selected: list[dict[str, Any]] = []
    selected_ids: set[str] = set()
    selected_types: set[str] = set()

    for row in base:
        group = display_type_group(row)
        if group in selected_types:
            continue
        selected.append(row)
        selected_ids.add(row["tgaz_id"])
        selected_types.add(group)
        if len(selected) >= target_count:
            return selected

    remaining = [row for row in base if row["tgaz_id"] not in selected_ids]
    while remaining and len(selected) < target_count:
        def spatial_key(row: dict[str, Any]) -> tuple[float, int, float, str]:
            minimum_separation = min(
                haversine(row["lat"], row["lon"], chosen["lat"], chosen["lon"])
                for chosen in selected
            )
            return (
                -minimum_separation,
                base_rank[row["tgaz_id"]],
                row["distance_km"],
                row["tgaz_id"],
            )

        chosen = min(remaining, key=spatial_key)
        selected.append(chosen)
        remaining.remove(chosen)
    return selected


def select_display_points(
    active_rows: Iterable[dict[str, Any]],
    strategy: str,
    *,
    config: DisplayConfig = DEFAULT_DISPLAY_CONFIG,
) -> list[dict[str, Any]]:
    rows = list(active_rows)
    if strategy == STRATEGY_NEAREST:
        return rank_nearest(rows)[: config.nearest_point_limit]
    if strategy == STRATEGY_TYPE_DIVERSE:
        return rank_type_diverse(rows)[: config.diverse_point_limit]
    if strategy == STRATEGY_TYPE_SPATIAL:
        return rank_type_spatial(rows, limit=config.diverse_point_limit)
    raise ValueError(f"unknown display strategy: {strategy}")


def _local_xy_km(
    row: dict[str, Any], anchor: dict[str, Any]
) -> tuple[float, float]:
    anchor_lon = anchor["modern_location"]["lon"]
    anchor_lat = anchor["modern_location"]["lat"]
    wrapped_lon_delta = (row["lon"] - anchor_lon + 180.0) % 360.0 - 180.0
    x_km = wrapped_lon_delta * 111.320 * math.cos(math.radians(anchor_lat))
    y_km = (row["lat"] - anchor_lat) * 110.574
    return x_km, y_km


def _label_rectangle(
    row: dict[str, Any],
    anchor: dict[str, Any],
    radius_km: float,
    rank: int,
    config: DisplayConfig,
) -> tuple[float, float, float, float]:
    x_km, y_km = _local_xy_km(row, anchor)
    width = config.collision_canvas_width_px
    height = config.collision_canvas_height_px
    x = width / 2 + (x_km / radius_km) * width * 0.44
    y = height / 2 - (y_km / radius_km) * height * 0.44
    lane_offset = (0, -10, 10)[rank % 3]
    character_count = min(14, len(row.get("name_zh_hans") or row["tgaz_id"]))
    label_width = (
        config.collision_label_padding_px
        + character_count * config.collision_character_width_px
    )
    label_height = config.collision_label_height_px
    return (
        x + 9,
        y - label_height / 2 + lane_offset,
        x + 9 + label_width,
        y + label_height / 2 + lane_offset,
    )


def _rectangles_overlap(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> bool:
    return not (
        first[2] <= second[0]
        or second[2] <= first[0]
        or first[3] <= second[1]
        or second[3] <= first[1]
    )


def select_display_labels(
    displayed_points: Iterable[dict[str, Any]],
    anchor: dict[str, Any],
    radius_km: float,
    *,
    config: DisplayConfig = DEFAULT_DISPLAY_CONFIG,
) -> dict[str, Any]:
    selected: list[dict[str, Any]] = []
    rectangles: list[tuple[float, float, float, float]] = []
    collision_hidden = 0
    for rank, row in enumerate(displayed_points):
        if len(selected) >= config.label_limit:
            break
        rectangle = _label_rectangle(row, anchor, radius_km, rank, config)
        if any(_rectangles_overlap(rectangle, existing) for existing in rectangles):
            collision_hidden += 1
            continue
        selected.append(row)
        rectangles.append(rectangle)
    return {
        "labels": selected,
        "collision_hidden_label_count": collision_hidden,
        "collision_metric_kind": "estimated",
    }


def spatial_coverage_grid_cells(
    rows: Iterable[dict[str, Any]],
    anchor: dict[str, Any],
    radius_km: float,
    *,
    grid_size: int = DEFAULT_DISPLAY_CONFIG.spatial_grid_size,
) -> int:
    occupied: set[tuple[int, int]] = set()
    for row in rows:
        x_km, y_km = _local_xy_km(row, anchor)
        x_index = min(
            grid_size - 1,
            max(0, math.floor(((x_km + radius_km) / (2 * radius_km)) * grid_size)),
        )
        y_index = min(
            grid_size - 1,
            max(0, math.floor(((y_km + radius_km) / (2 * radius_km)) * grid_size)),
        )
        occupied.add((x_index, y_index))
    return len(occupied)


def _type_distribution(rows: Iterable[dict[str, Any]]) -> dict[str, int]:
    counts = Counter(display_type_group(row) for row in rows)
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def build_strategy_case(
    active_rows: list[dict[str, Any]],
    anchor: dict[str, Any],
    year: int,
    strategy: str,
    *,
    config: DisplayConfig = DEFAULT_DISPLAY_CONFIG,
) -> dict[str, Any]:
    points = select_display_points(active_rows, strategy, config=config)
    label_result = select_display_labels(
        points, anchor, anchor["default_radius_km"], config=config
    )
    labels = label_result["labels"]
    point_types = _type_distribution(points)
    label_types = _type_distribution(labels)
    dominant_type = next(iter(label_types), None)
    dominant_count = label_types.get(dominant_type, 0) if dominant_type else 0
    point_dominant_type = next(iter(point_types), None)
    point_dominant_count = (
        point_types.get(point_dominant_type, 0) if point_dominant_type else 0
    )
    distances = [row["distance_km"] for row in points]
    return {
        "anchor": anchor["anchor_id"],
        "anchor_display_name": anchor["display_name"],
        "year": year,
        "strategy": strategy,
        "active_feature_count": len(active_rows),
        "displayed_point_count": len(points),
        "displayed_label_count": len(labels),
        "visible_type_count": len(label_types),
        "dominant_type": dominant_type,
        "dominant_type_share": round(dominant_count / len(labels), 4) if labels else 0.0,
        "point_visible_type_count": len(point_types),
        "point_dominant_type": point_dominant_type,
        "point_dominant_type_share": (
            round(point_dominant_count / len(points), 4) if points else 0.0
        ),
        "nearest_displayed_distance_km": min(distances) if distances else None,
        "farthest_displayed_distance_km": max(distances) if distances else None,
        "spatial_coverage_metric": spatial_coverage_grid_cells(
            points,
            anchor,
            anchor["default_radius_km"],
            grid_size=config.spatial_grid_size,
        ),
        "spatial_coverage_metric_name": (
            f"occupied_anchor_grid_cells_{config.spatial_grid_size}x{config.spatial_grid_size}"
        ),
        "collision_hidden_label_count": label_result[
            "collision_hidden_label_count"
        ],
        "collision_metric_kind": label_result["collision_metric_kind"],
        "point_type_distribution": point_types,
        "label_type_distribution": label_types,
        "displayed_point_ids": [row["tgaz_id"] for row in points],
        "displayed_label_ids": [row["tgaz_id"] for row in labels],
    }


def _existing_detail_properties(
    processed_dir: Path,
) -> dict[tuple[str, int, str], dict[str, Any]]:
    lookup: dict[tuple[str, int, str], dict[str, Any]] = {}
    for anchor_id in EXPECTED_ANCHOR_IDS:
        manifest_path = processed_dir / "anchors" / anchor_id / "manifest.json"
        if not manifest_path.exists():
            continue
        manifest = read_json(manifest_path)
        for year_text, relative_path in manifest.get("slices", {}).items():
            slice_path = processed_dir / relative_path
            if not slice_path.exists():
                continue
            for feature in read_json(slice_path).get("features", []):
                lookup[(anchor_id, int(year_text), feature["id"])] = feature[
                    "properties"
                ]
    return lookup


def _active_feature(
    row: dict[str, Any],
    anchor_id: str,
    year: int,
    existing_details: dict[tuple[str, int, str], dict[str, Any]],
) -> dict[str, Any]:
    existing = existing_details.get((anchor_id, year, row["tgaz_id"]), {})
    return {
        "type": "Feature",
        "id": row["tgaz_id"],
        "geometry": {"type": "Point", "coordinates": [row["lon"], row["lat"]]},
        "properties": {
            "tgaz_id": row["tgaz_id"],
            "name": row["name_zh_hans"],
            "name_pinyin": row["name_pinyin"] or None,
            "feature_type": row["feature_type"] or "未分类",
            "display_type_group": display_type_group(row),
            "valid_from": row["valid_from"],
            "valid_to": row["valid_to"],
            "parent_name": row["parent_name"],
            "distance_to_anchor_km": row["distance_km"],
            "relation_to_anchor": "spatial_nearby",
            "lineage_claim": None,
            "location_confidence": existing.get(
                "location_confidence", row["location_confidence"]
            ),
            "location_assertion_status": existing.get(
                "location_assertion_status", "not_re_enriched"
            ),
            "source_id": "tgaz_chgis",
            "source_record_id": row["tgaz_id"],
            "source_url": row["source_url"],
            "source_data_source": row["data_source"],
            "source_detail_level": (
                "canonical_api_cache" if existing.get("detail_path") else "csv_snapshot"
            ),
            "license": existing.get("license"),
            "detail_path": existing.get("detail_path"),
        },
    }


def _snapshot_inputs(
    points: list[dict[str, Any]], anchors: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    rows_by_id = {row["tgaz_id"]: row for row in points}
    anchors_by_id = {anchor["anchor_id"]: anchor for anchor in anchors}
    snapshots = []
    for anchor_id in EXPECTED_ANCHOR_IDS:
        anchor = anchors_by_id[anchor_id]
        evidence_path = PERIOD_EVIDENCE_DIR / f"{anchor_id}.json"
        evidence = read_json(evidence_path)
        if len(evidence["snapshots"]) != 4:
            raise RuntimeError(f"{anchor_id} does not have the frozen four snapshots")
        for snapshot in evidence["snapshots"]:
            missing = [
                tgaz_id
                for tgaz_id in snapshot["active_feature_ids"]
                if tgaz_id not in rows_by_id
            ]
            if missing:
                raise RuntimeError(
                    f"{anchor_id}/{snapshot['year']} missing normalized rows: {missing[:3]}"
                )
            active_rows = []
            for tgaz_id in snapshot["active_feature_ids"]:
                source = rows_by_id[tgaz_id]
                row = dict(source)
                row["distance_km"] = round(
                    haversine(
                        anchor["modern_location"]["lat"],
                        anchor["modern_location"]["lon"],
                        source["lat"],
                        source["lon"],
                    ),
                    3,
                )
                active_rows.append(row)
            active_rows = _stable_distance_order(active_rows)
            if len(active_rows) != snapshot["active_feature_count"]:
                raise RuntimeError(
                    f"{anchor_id}/{snapshot['year']} active count differs from Phase 1 evidence"
                )
            snapshots.append(
                {
                    "anchor": anchor,
                    "year": snapshot["year"],
                    "period": snapshot,
                    "active_rows": active_rows,
                    "evidence_path": evidence_path,
                    "evidence_semantic_sha256": evidence["semantic_sha256"],
                }
            )
    return snapshots


def _write_active_slices(
    snapshots: list[dict[str, Any]],
    *,
    processed_dir: Path,
    generated_at: str,
) -> dict[str, Any]:
    existing_details = _existing_detail_properties(processed_dir)
    source_manifest = read_json(TGAZ_INDEX_MANIFEST_PATH)
    source_index = {
        "dataset": source_manifest["dataset"],
        "snapshot_date": source_manifest["snapshot_date"],
        "source_url": source_manifest["artifact"]["source_url"],
        "sha256": source_manifest["artifact"]["sha256"],
        "retrieved_at": source_manifest["artifact"]["retrieved_at"],
    }
    entries: dict[str, dict[str, Any]] = {}
    generated_files: list[str] = []
    for snapshot in snapshots:
        anchor = snapshot["anchor"]
        anchor_id = anchor["anchor_id"]
        year = snapshot["year"]
        active_rows = snapshot["active_rows"]
        features = [
            _active_feature(row, anchor_id, year, existing_details)
            for row in active_rows
        ]
        relative_path = f"phase1_1/anchors/{anchor_id}/slices/{year}.geojson"
        value = {
            "type": "FeatureCollection",
            "metadata": {
                "generated_at": generated_at,
                "phase": "Phase 1.1 Display Semantics Experiment",
                "anchor_id": anchor_id,
                "anchor_display_name": anchor["display_name"],
                "year": year,
                "radius_km": anchor["default_radius_km"],
                "active_feature_count": len(features),
                "underlying_active_record_count": len(features),
                "active_feature_ids_sha256": semantic_sha256(
                    sorted(feature["id"] for feature in features)
                ),
                "frozen_period_snapshot_signature_sha256": snapshot["period"][
                    "snapshot_signature_sha256"
                ],
                "phase1_evidence_semantic_sha256": snapshot[
                    "evidence_semantic_sha256"
                ],
                "coverage_status": "available_through_1911",
                "relation_semantics": "spatial_nearby only; no historical lineage",
                "display_semantics": (
                    "This file contains all active_features. The browser derives "
                    "displayed_points and displayed_labels without rewriting these records."
                ),
                "source_index": source_index,
            },
            "features": features,
        }
        value["metadata"]["semantic_sha256"] = semantic_sha256(value)
        output_path = processed_dir / relative_path
        write_json(output_path, value)
        generated_files.append(str(output_path))
        anchor_entry = entries.setdefault(
            anchor_id,
            {
                "anchor_id": anchor_id,
                "display_name": anchor["display_name"],
                "modern_location": anchor["modern_location"],
                "radius_km": anchor["default_radius_km"],
                "slices": {},
            },
        )
        anchor_entry["slices"][str(year)] = relative_path
    index = {
        "generated_at": generated_at,
        "phase": "Phase 1.1 Display Semantics Experiment",
        "active_data_source": "frozen Phase 1 period evidence + TGAZ/CHGIS CSV snapshot",
        "display_config": asdict(DEFAULT_DISPLAY_CONFIG),
        "strategies": list(STRATEGIES),
        "anchors": entries,
    }
    index["semantic_sha256"] = semantic_sha256(index)
    index_path = processed_dir / "phase1_1" / "index.json"
    write_json(index_path, index)
    generated_files.append(str(index_path))
    return {"index": index, "index_path": str(index_path), "generated_files": generated_files}


def build_feature_type_distribution(
    snapshots: list[dict[str, Any]], *, generated_at: str
) -> dict[str, Any]:
    overall = Counter()
    pinyin_by_type: dict[str, set[str]] = defaultdict(set)
    dominant_snapshot_counts = Counter()
    snapshot_results = []
    for snapshot in snapshots:
        counts = Counter(display_type_group(row) for row in snapshot["active_rows"])
        overall.update(counts)
        for row in snapshot["active_rows"]:
            if row.get("feature_type_pinyin"):
                pinyin_by_type[display_type_group(row)].add(row["feature_type_pinyin"])
        dominant_type, dominant_count = min(
            counts.items(), key=lambda item: (-item[1], item[0])
        )
        dominant_snapshot_counts[dominant_type] += 1
        snapshot_results.append(
            {
                "anchor": snapshot["anchor"]["anchor_id"],
                "anchor_display_name": snapshot["anchor"]["display_name"],
                "year": snapshot["year"],
                "active_feature_count": len(snapshot["active_rows"]),
                "distinct_type_count": len(counts),
                "dominant_type": dominant_type,
                "dominant_type_share": round(
                    dominant_count / len(snapshot["active_rows"]), 4
                ),
                "distribution": dict(
                    sorted(counts.items(), key=lambda item: (-item[1], item[0]))
                ),
            }
        )
    mapping = {name: name for name in sorted(overall)}
    return {
        "generated_at": generated_at,
        "analysis_basis": {
            "canonical_field": "feature_type",
            "source_mapping": "TYPE_SIM -> feature_type; TYPE_ENG -> feature_type_pinyin",
            "snapshot_count": len(snapshots),
            "feature_occurrence_count": sum(overall.values()),
        },
        "total_distinct_type_count": len(overall),
        "overall_snapshot_occurrence_distribution": dict(
            sorted(overall.items(), key=lambda item: (-item[1], item[0]))
        ),
        "types": [
            {
                "raw_feature_type": name,
                "feature_type_pinyin_values": sorted(pinyin_by_type[name]),
                "display_type_group": mapping[name],
                "snapshot_occurrence_count": overall[name],
                "dominant_snapshot_count": dominant_snapshot_counts[name],
            }
            for name in sorted(overall)
        ],
        "frequent_dominant_types": dict(
            sorted(
                dominant_snapshot_counts.items(),
                key=lambda item: (-item[1], item[0]),
            )
        ),
        "raw_to_display_type_group": mapping,
        "grouping_assessment": {
            "grouping_applied": False,
            "decision": "identity_mapping_only",
            "reason": (
                "Some administrative types are historically related, but the frozen source "
                "does not provide an authoritative equivalence relation. Merging them for "
                "display would add subjective semantics, so every raw canonical type remains "
                "its own explicit display group."
            ),
        },
        "snapshots": snapshot_results,
    }


def _format_year(year: int) -> str:
    return f"前{abs(year)}" if year < 0 else str(year)


def _write_type_distribution_markdown(value: dict[str, Any], path: Path) -> None:
    lines = [
        "# Phase 1.1 Feature Type Distribution",
        "",
        f"- 冻结 snapshot：{value['analysis_basis']['snapshot_count']}",
        f"- Active feature occurrences：{value['analysis_basis']['feature_occurrence_count']}",
        f"- Canonical feature types：{value['total_distinct_type_count']}",
        "- Grouping：未合并；`raw_feature_type -> display_type_group` 为显式 identity mapping。",
        "",
        "相关行政类型可能在语言上接近，但当前 source 没有提供等价关系。Display 层合并会引入主观语义，故本实验保留每个原始 canonical type。",
        "",
        "## Dominant Type Frequency",
        "",
        "| Type | 成为 dominant 的 snapshot 数 | Active occurrence 数 |",
        "|---|---:|---:|",
    ]
    for feature_type, count in value["frequent_dominant_types"].items():
        total = value["overall_snapshot_occurrence_distribution"][feature_type]
        lines.append(f"| {feature_type} | {count} | {total} |")
    lines.extend(
        [
            "",
            "## Snapshot Distribution",
            "",
            "| Anchor | Year | Active | Types | Dominant | Share | Full distribution |",
            "|---|---:|---:|---:|---|---:|---|",
        ]
    )
    for snapshot in value["snapshots"]:
        distribution = "；".join(
            f"{name} {count}" for name, count in snapshot["distribution"].items()
        )
        lines.append(
            f"| {snapshot['anchor_display_name']} | {_format_year(snapshot['year'])} | "
            f"{snapshot['active_feature_count']} | {snapshot['distinct_type_count']} | "
            f"{snapshot['dominant_type']} | {snapshot['dominant_type_share']:.1%} | "
            f"{distribution} |"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_comparison(
    snapshots: list[dict[str, Any]], *, generated_at: str
) -> dict[str, Any]:
    cases = [
        build_strategy_case(
            snapshot["active_rows"],
            snapshot["anchor"],
            snapshot["year"],
            strategy,
        )
        for snapshot in snapshots
        for strategy in STRATEGIES
    ]
    return {
        "generated_at": generated_at,
        "experiment": "Phase 1.1 Display Ranking & Label Semantics",
        "case_count": len(cases),
        "snapshot_count": len(snapshots),
        "strategy_count": len(STRATEGIES),
        "display_config": asdict(DEFAULT_DISPLAY_CONFIG),
        "set_invariants": [
            "displayed_points is a subset of active_features",
            "displayed_labels is a subset of displayed_points",
            "display selection does not merge identity or create lineage",
        ],
        "metric_definitions": {
            "dominant_type": "Computed over displayed_labels; point equivalents are also retained.",
            "spatial_coverage_metric": (
                "Count of occupied cells in a fixed 4x4 anchor-centered square spanning "
                "the 75 km query radius; a display-only proxy, not a quality score."
            ),
            "collision_hidden_label_count": (
                "Estimated by greedy overlap checks on deterministic label rectangles "
                "projected to a 900x600 analysis canvas. It is not MapLibre measured placement."
            ),
        },
        "winner": None,
        "composite_quality_score_used": False,
        "cases": cases,
    }


def _write_comparison_markdown(value: dict[str, Any], path: Path) -> None:
    lines = [
        "# Phase 1.1 Display Strategy Comparison",
        "",
        f"共 {value['case_count']} 个 case（{value['snapshot_count']} snapshots × {value['strategy_count']} strategies）。",
        "",
        "`dominant_type*` 以 displayed labels 计算；point 指标另存于 JSON。Collision 为固定分析画布上的 `estimated` 值，不是 MapLibre placement 的 measured 值。Spatial coverage 是 4×4 锚点网格占用格数，不是综合质量分。未自动选出 winner。",
        "",
        "| Anchor | Year | Strategy | Active | Points | Labels | Label types | Dominant | Share | Near km | Far km | Grid cells | Collision hidden |",
        "|---|---:|---|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|",
    ]
    for case in value["cases"]:
        near = "—" if case["nearest_displayed_distance_km"] is None else f"{case['nearest_displayed_distance_km']:.3f}"
        far = "—" if case["farthest_displayed_distance_km"] is None else f"{case['farthest_displayed_distance_km']:.3f}"
        lines.append(
            f"| {case['anchor_display_name']} | {_format_year(case['year'])} | "
            f"{case['strategy']} | {case['active_feature_count']} | "
            f"{case['displayed_point_count']} | {case['displayed_label_count']} | "
            f"{case['visible_type_count']} | {case['dominant_type'] or '—'} | "
            f"{case['dominant_type_share']:.1%} | {near} | {far} | "
            f"{case['spatial_coverage_metric']} | {case['collision_hidden_label_count']} |"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_phase1_1(
    *,
    processed_dir: Path = PROCESSED_DIR,
    generated_at: str | None = None,
) -> dict[str, Any]:
    generated_at = generated_at or utc_now()
    preserved_paths = [
        processed_dir / "anchors" / "index.json",
        QA_DIR / "phase1_data_generation.json",
        V6_OUTLIERS_PATH,
    ]
    missing_preserved = [str(path) for path in preserved_paths if not path.exists()]
    if missing_preserved:
        raise RuntimeError(f"required Phase 1 artifacts are missing: {missing_preserved}")
    hashes_before = {str(path): sha256_file(path) for path in preserved_paths}

    snapshots = _snapshot_inputs(load_normalized_points(), read_json(FINAL_ANCHORS_PATH))
    active_output = _write_active_slices(
        snapshots, processed_dir=processed_dir, generated_at=generated_at
    )
    type_distribution = build_feature_type_distribution(
        snapshots, generated_at=generated_at
    )
    write_json(TYPE_DISTRIBUTION_JSON_PATH, type_distribution)
    _write_type_distribution_markdown(type_distribution, TYPE_DISTRIBUTION_MD_PATH)
    comparison = build_comparison(snapshots, generated_at=generated_at)
    write_json(COMPARISON_JSON_PATH, comparison)
    _write_comparison_markdown(comparison, COMPARISON_MD_PATH)

    hashes_after = {str(path): sha256_file(path) for path in preserved_paths}
    preservation = {
        path: {
            "sha256_before": hashes_before[path],
            "sha256_after": hashes_after[path],
            "unchanged": hashes_before[path] == hashes_after[path],
        }
        for path in hashes_before
    }
    report = {
        "phase": "Phase 1.1 Display Ranking & Label Semantics Experiment",
        "status": "PASS"
        if comparison["case_count"] == 60
        and all(item["unchanged"] for item in preservation.values())
        else "FAIL",
        "generated_at": generated_at,
        "snapshot_count": len(snapshots),
        "strategy_case_count": comparison["case_count"],
        "active_feature_occurrence_count": sum(
            len(snapshot["active_rows"]) for snapshot in snapshots
        ),
        "type_count": type_distribution["total_distinct_type_count"],
        "processed_index_path": active_output["index_path"],
        "type_distribution_paths": [
            str(TYPE_DISTRIBUTION_JSON_PATH),
            str(TYPE_DISTRIBUTION_MD_PATH),
        ],
        "comparison_paths": [str(COMPARISON_JSON_PATH), str(COMPARISON_MD_PATH)],
        "phase1_artifact_preservation": preservation,
        "canonical_spatial_source_changed": False,
        "representative_period_algorithm_rerun": False,
        "new_source_accessed": False,
        "winner_selected": False,
    }
    write_json(GENERATION_REPORT_PATH, report)
    if report["status"] != "PASS":
        raise RuntimeError("Phase 1.1 QA generation failed")
    return report
