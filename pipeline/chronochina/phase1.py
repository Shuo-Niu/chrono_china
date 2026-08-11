from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from .build import build_feature
from .config import PROCESSED_DIR, QA_DIR, TGAZ_DETAIL_DIR, TGAZ_INDEX_MANIFEST_PATH
from .g5 import FINAL_ANCHORS_PATH
from .io import read_json, sha256_file, utc_now, write_json
from .periods import ALGORITHM_VERSION, DEFAULT_PERIOD_COUNT, select_representative_periods
from .probe import spatial_rows
from .temporal import valid_for
from .tgaz_detail import fetch_and_parse_details
from .tgaz_index import NORMALIZED_POINTS_PATH, load_normalized_points


PHASE1_COVERAGE_END_YEAR = 1911
DISPLAY_FEATURE_LIMIT = 12
EXPECTED_ANCHOR_IDS = ("beijing", "xian", "chengdu", "qingdao", "qufu")

PHASE1_REPORT_PATH = QA_DIR / "phase1_data_generation.json"
PHASE1_API_FAILURES_PATH = QA_DIR / "phase1_api_failures.json"
PHASE1_CONFLICTS_PATH = QA_DIR / "phase1_location_assertion_conflicts.json"
V6_PARITY_REPORT_PATH = QA_DIR / "g6_v6_parity.json"
V6_OUTLIERS_PATH = QA_DIR / "v6_parity_outliers.json"
PERIOD_EVIDENCE_DIR = NORMALIZED_POINTS_PATH.parent / "phase1_periods"


def _clean_for_semantic_hash(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _clean_for_semantic_hash(item)
            for key, item in sorted(value.items())
            if key not in {"generated_at", "semantic_sha256"}
        }
    if isinstance(value, list):
        return [_clean_for_semantic_hash(item) for item in value]
    return value


def semantic_sha256(value: Any) -> str:
    content = json.dumps(
        _clean_for_semantic_hash(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def select_display_rows(
    active_rows: list[dict[str, Any]], *, limit: int = DISPLAY_FEATURE_LIMIT
) -> list[dict[str, Any]]:
    """Prefer the nearest distinct coordinates, then fill without merging identities."""
    ordered = sorted(active_rows, key=lambda row: (row["distance_km"], row["tgaz_id"]))
    distinct: list[dict[str, Any]] = []
    deferred: list[dict[str, Any]] = []
    seen_coordinates: set[tuple[float, float]] = set()
    for row in ordered:
        coordinate_key = (round(row["lon"], 4), round(row["lat"], 4))
        if coordinate_key in seen_coordinates:
            deferred.append(row)
            continue
        seen_coordinates.add(coordinate_key)
        distinct.append(row)
    selected = (distinct + deferred)[:limit]
    return [{**row, "display_rank": index + 1} for index, row in enumerate(selected)]


def build_phase1_plan(
    rows: list[dict[str, Any]],
    anchors: list[dict[str, Any]],
    *,
    period_count: int = DEFAULT_PERIOD_COUNT,
    display_limit: int = DISPLAY_FEATURE_LIMIT,
    max_year: int = PHASE1_COVERAGE_END_YEAR,
) -> dict[str, Any]:
    by_id = {anchor["anchor_id"]: anchor for anchor in anchors}
    missing = [anchor_id for anchor_id in EXPECTED_ANCHOR_IDS if anchor_id not in by_id]
    if missing:
        raise RuntimeError(f"Phase 1 is missing fixed anchors: {missing}")

    anchor_plans = []
    unique_display_ids: set[str] = set()
    for anchor_id in EXPECTED_ANCHOR_IDS:
        anchor = by_id[anchor_id]
        radius = anchor["default_radius_km"]
        nearby = spatial_rows(rows, anchor, radius)
        periods = select_representative_periods(
            nearby,
            target_count=period_count,
            max_year=max_year,
        )
        slices = []
        for period in periods:
            year = period["year"]
            active = [
                row
                for row in nearby
                if valid_for(row["valid_from"], row["valid_to"], year)
            ]
            display_rows = select_display_rows(active, limit=display_limit)
            unique_display_ids.update(row["tgaz_id"] for row in display_rows)
            slices.append(
                {
                    "year": year,
                    "period": period,
                    "active_rows": active,
                    "display_rows": display_rows,
                }
            )
        anchor_plans.append(
            {
                "anchor": anchor,
                "spatial_candidate_count": len(nearby),
                "periods": periods,
                "slices": slices,
                "status": (
                    "PASS"
                    if len(periods) >= 3
                    and all(slice_["active_rows"] and slice_["display_rows"] for slice_ in slices)
                    else "FAIL"
                ),
            }
        )
    return {
        "algorithm_version": ALGORITHM_VERSION,
        "period_count_target": period_count,
        "display_feature_limit": display_limit,
        "max_supported_year": max_year,
        "anchors": anchor_plans,
        "unique_display_ids": sorted(unique_display_ids),
    }


def _source_index_provenance() -> dict[str, Any]:
    manifest = read_json(TGAZ_INDEX_MANIFEST_PATH)
    artifact = manifest["artifact"]
    return {
        "dataset": manifest["dataset"],
        "snapshot_date": manifest["snapshot_date"],
        "source_url": artifact["source_url"],
        "sha256": artifact["sha256"],
        "retrieved_at": artifact["retrieved_at"],
    }


def _write_period_evidence(
    anchor_plan: dict[str, Any], *, evidence_dir: Path, generated_at: str
) -> Path:
    anchor = anchor_plan["anchor"]
    value = {
        "generated_at": generated_at,
        "anchor_id": anchor["anchor_id"],
        "algorithm_version": ALGORITHM_VERSION,
        "candidate_year_semantics": ["BEG", "END", "END+1 for closed-interval removal"],
        "snapshots": [
            {
                **slice_["period"],
                "active_feature_ids": sorted(
                    row["tgaz_id"] for row in slice_["active_rows"]
                ),
                "display_feature_ids": [
                    row["tgaz_id"] for row in slice_["display_rows"]
                ],
            }
            for slice_ in anchor_plan["slices"]
        ],
    }
    value["semantic_sha256"] = semantic_sha256(value)
    path = evidence_dir / f"{anchor['anchor_id']}.json"
    write_json(path, value)
    return path


def write_phase1_outputs(
    plan: dict[str, Any],
    details_by_id: dict[str, dict[str, Any]],
    *,
    processed_dir: Path = PROCESSED_DIR,
    evidence_dir: Path = PERIOD_EVIDENCE_DIR,
    generated_at: str | None = None,
    input_fingerprint: str = "test-input",
    source_index: dict[str, Any] | None = None,
) -> dict[str, Any]:
    generated_at = generated_at or utc_now()
    source_index = source_index or _source_index_provenance()
    generated_files: list[str] = []
    anchor_summaries = []
    conflicts = []
    index_entries = []

    for anchor_plan in plan["anchors"]:
        anchor = anchor_plan["anchor"]
        anchor_id = anchor["anchor_id"]
        period_entries = []
        slices: dict[str, str] = {}
        unique_active_ids: set[str] = set()
        unique_rendered_ids: set[str] = set()

        for slice_plan in anchor_plan["slices"]:
            year = slice_plan["year"]
            features = []
            for row in slice_plan["display_rows"]:
                tgaz_id = row["tgaz_id"]
                detail = details_by_id.get(tgaz_id)
                if detail is None:
                    raise RuntimeError(f"missing canonical detail for {tgaz_id}")
                detail_path = f"details/{anchor_id}/{year}/{tgaz_id}.json"
                feature, detail_card, conflict = build_feature(
                    row,
                    detail,
                    anchor,
                    year,
                    detail_path=detail_path,
                    canonical_location_source="tgaz_csv_snapshot",
                )
                feature["properties"]["display_rank"] = row["display_rank"]
                detail_card["display_rank"] = row["display_rank"]
                detail_card["snapshot_year"] = year
                details_path = processed_dir / detail_path
                write_json(details_path, detail_card)
                generated_files.append(str(details_path))
                features.append(feature)
                conflicts.append({"anchor_id": anchor_id, **conflict})
                unique_rendered_ids.add(tgaz_id)

            unique_active_ids.update(row["tgaz_id"] for row in slice_plan["active_rows"])
            slice_relative = f"anchors/{anchor_id}/slices/{year}.geojson"
            feature_collection = {
                "type": "FeatureCollection",
                "metadata": {
                    "generated_at": generated_at,
                    "input_fingerprint": input_fingerprint,
                    "anchor_id": anchor_id,
                    "anchor_display_name": anchor["display_name"],
                    "year": year,
                    "radius_km": anchor["default_radius_km"],
                    "coverage_status": "available_through_1911",
                    "underlying_active_record_count": len(slice_plan["active_rows"]),
                    "rendered_feature_count": len(features),
                    "display_filter": {
                        "method": "nearest_distinct_coordinate_then_fill",
                        "limit": plan["display_feature_limit"],
                        "identity_records_merged": False,
                    },
                    "period_selection": slice_plan["period"],
                    "relation_semantics": "spatial_nearby only; no historical lineage",
                    "source_index": source_index,
                },
                "features": features,
            }
            feature_collection["metadata"]["semantic_sha256"] = semantic_sha256(
                feature_collection
            )
            slice_path = processed_dir / slice_relative
            write_json(slice_path, feature_collection)
            generated_files.append(str(slice_path))
            slices[str(year)] = slice_relative
            period_entries.append(
                {
                    **slice_plan["period"],
                    "rendered_feature_count": len(features),
                    "slice_path": slice_relative,
                }
            )

        default_period = max(
            period_entries,
            key=lambda period: (period["active_feature_count"], period["year"]),
        )["year"]
        manifest = {
            **anchor,
            "phase": "Phase 1 Five-Anchor MVP",
            "generated_at": generated_at,
            "input_fingerprint": input_fingerprint,
            "available_periods": [period["year"] for period in period_entries],
            "default_period": default_period,
            "periods": period_entries,
            "period_selection": {
                "algorithm_version": plan["algorithm_version"],
                "target_count": plan["period_count_target"],
                "candidate_years": ["BEG", "END", "END+1 for closed-interval removal"],
                "selection_rule": "largest active-feature-set change in each chronological segment",
                "coverage_end_year": plan["max_supported_year"],
            },
            "display_filter": {
                "method": "nearest_distinct_coordinate_then_fill",
                "feature_limit_per_slice": plan["display_feature_limit"],
                "underlying_counts_preserved_in_slice_metadata": True,
                "identity_records_merged": False,
            },
            "coverage": {
                "through_1911": "available",
                "1912_1949": "not_publicly_accessible_not_integrated",
                "post_1949": "not_yet_integrated",
            },
            "history_source": source_index,
            "slices": slices,
            "semantic_notice": (
                "Nearby historical places are a spatial neighborhood, not predecessors, "
                "former names, or the same entity as the modern anchor."
            ),
        }
        manifest["semantic_sha256"] = semantic_sha256(manifest)
        manifest_path = processed_dir / "anchors" / anchor_id / "manifest.json"
        write_json(manifest_path, manifest)
        generated_files.append(str(manifest_path))

        evidence_path = _write_period_evidence(
            anchor_plan, evidence_dir=evidence_dir, generated_at=generated_at
        )
        generated_files.append(str(evidence_path))
        summary = {
            "anchor_id": anchor_id,
            "display_name": anchor["display_name"],
            "status": anchor_plan["status"],
            "periods": period_entries,
            "spatial_candidate_count": anchor_plan["spatial_candidate_count"],
            "selected_snapshot_active_record_total": sum(
                period["active_feature_count"] for period in period_entries
            ),
            "selected_snapshot_unique_active_record_count": len(unique_active_ids),
            "rendered_feature_total": sum(
                period["rendered_feature_count"] for period in period_entries
            ),
            "unique_rendered_tgaz_id_count": len(unique_rendered_ids),
            "manifest_path": str(manifest_path),
        }
        anchor_summaries.append(summary)
        index_entries.append(
            {
                "anchor_id": anchor_id,
                "display_name": anchor["display_name"],
                "manifest_path": f"anchors/{anchor_id}/manifest.json",
                "default_period": default_period,
            }
        )

    anchor_index = {
        "generated_at": generated_at,
        "input_fingerprint": input_fingerprint,
        "anchors": index_entries,
    }
    anchor_index["semantic_sha256"] = semantic_sha256(anchor_index)
    index_path = processed_dir / "anchors" / "index.json"
    write_json(index_path, anchor_index)
    generated_files.append(str(index_path))

    conflict_report = {
        "generated_at": generated_at,
        "canonical_location_source": "tgaz_csv_snapshot",
        "api_coordinates_retained_as_competing_assertions": True,
        "newest_write_wins_used": False,
        "records": conflicts,
    }
    conflict_report["semantic_sha256"] = semantic_sha256(conflict_report)
    return {
        "generated_at": generated_at,
        "input_fingerprint": input_fingerprint,
        "anchors": anchor_summaries,
        "anchor_index": anchor_index,
        "conflict_report": conflict_report,
        "generated_files": generated_files,
        "semantic_sha256": semantic_sha256(
            {"anchors": anchor_summaries, "anchor_index": anchor_index}
        ),
    }


def write_v6_parity_outliers(
    source_path: Path = V6_PARITY_REPORT_PATH,
    output_path: Path = V6_OUTLIERS_PATH,
) -> dict[str, Any]:
    report = read_json(source_path)
    outliers = []
    for comparison in report["parity"]["comparisons"]:
        matched = comparison["tgaz_record_found"]
        matches = comparison.get("matches", {})
        anomaly_types = []
        if not matched:
            anomaly_types.append("unmatched_v6_id")
        else:
            if not matches.get("coordinate_within_10m", False):
                anomaly_types.append("coordinate_mismatch_gt_10m")
            if not matches.get("valid_from", False) or not matches.get("valid_to", False):
                anomaly_types.append("temporal_mismatch")
            if not matches.get("name", False):
                anomaly_types.append("name_mismatch")
            if not matches.get("feature_type", False):
                anomaly_types.append("feature_type_mismatch")
        if not anomaly_types:
            continue
        tgaz = comparison.get("tgaz") or {}
        v6 = comparison["v6"]
        distance_m = comparison.get("coordinate_distance_m")
        outliers.append(
            {
                "v6_id": comparison["chgis_id"],
                "hypothesized_tgaz_id": comparison["hypothesized_tgaz_id"],
                "name": v6.get("name"),
                "matching_status": "matched" if matched else "unmatched",
                "csv_coordinate": (
                    {"lon": tgaz.get("lon"), "lat": tgaz.get("lat")} if matched else None
                ),
                "v6_coordinate": {"lon": v6.get("lon"), "lat": v6.get("lat")},
                "distance_m": distance_m,
                "distance_km": round(distance_m / 1000, 3) if distance_m is not None else None,
                "anomaly_types": anomaly_types,
            }
        )
    value = {
        "probe_gate": "G6 COMPLETE",
        "capability": "V6 parity = NOT_EQUIVALENT",
        "source_report": str(source_path),
        "sample_size": report["parity"]["sample_size"],
        "outlier_count": len(outliers),
        "outliers": outliers,
    }
    write_json(output_path, value)
    return value


def _input_fingerprint() -> str:
    values = {
        "normalized_points_sha256": sha256_file(NORMALIZED_POINTS_PATH),
        "final_anchors_sha256": sha256_file(FINAL_ANCHORS_PATH),
        "algorithm_version": ALGORITHM_VERSION,
        "period_count": DEFAULT_PERIOD_COUNT,
        "display_limit": DISPLAY_FEATURE_LIMIT,
        "coverage_end_year": PHASE1_COVERAGE_END_YEAR,
    }
    return semantic_sha256(values)


def record_phase1_api_attempt(
    enrichment: dict[str, Any], output_path: Path = PHASE1_API_FAILURES_PATH
) -> dict[str, Any]:
    observed_at = utc_now()
    existing = read_json(output_path) if output_path.exists() else {}
    attempts = list(existing.get("attempts", []))
    if "failures" in existing:
        legacy_failures = existing["failures"]
        attempts.append(
            {
                "observed_at": existing.get("generated_at"),
                "failure_count": len(legacy_failures),
                "failures": legacy_failures,
            }
        )
    attempts.append(
        {
            "observed_at": observed_at,
            "requested_count": len(enrichment["requested_ids"]),
            "success_count": enrichment["success_count"],
            "failure_count": enrichment["failure_count"],
            "failures": enrichment["failures"],
        }
    )
    value = {
        "generated_at": observed_at,
        "latest_failure_count": enrichment["failure_count"],
        "attempts": attempts,
    }
    write_json(output_path, value)
    return value


def run_phase1() -> dict[str, Any]:
    previous_report = read_json(PHASE1_REPORT_PATH) if PHASE1_REPORT_PATH.exists() else None
    points = load_normalized_points()
    anchors = read_json(FINAL_ANCHORS_PATH)
    plan = build_phase1_plan(points, anchors)
    failed_anchors = [
        anchor_plan["anchor"]["anchor_id"]
        for anchor_plan in plan["anchors"]
        if anchor_plan["status"] != "PASS"
    ]
    if failed_anchors:
        raise RuntimeError(f"Phase 1 period generation failed for {failed_anchors}")

    enrichment = fetch_and_parse_details(plan["unique_display_ids"])
    record_phase1_api_attempt(enrichment)
    if enrichment["failure_count"]:
        raise RuntimeError(
            f"Phase 1 canonical enrichment failed for {enrichment['failure_count']} records"
        )
    incomplete = [
        tgaz_id
        for tgaz_id, detail in enrichment["details"].items()
        if not (
            detail["canonical_uri"]
            and detail["source"]["license"]
            and detail["location"]["lat"] is not None
            and detail["location"]["lon"] is not None
            and detail["temporal"]["valid_from"] is not None
            and detail["temporal"]["valid_to"] is not None
        )
    ]
    if incomplete:
        raise RuntimeError(f"Phase 1 canonical details are incomplete: {incomplete}")

    input_fingerprint = _input_fingerprint()
    outputs = write_phase1_outputs(
        plan,
        enrichment["details"],
        input_fingerprint=input_fingerprint,
    )
    write_json(PHASE1_CONFLICTS_PATH, outputs["conflict_report"])
    outliers = write_v6_parity_outliers()

    input_paths = [NORMALIZED_POINTS_PATH, FINAL_ANCHORS_PATH] + [
        TGAZ_DETAIL_DIR / f"{tgaz_id}.json" for tgaz_id in plan["unique_display_ids"]
    ]
    output_paths = [Path(path) for path in outputs["generated_files"]]
    newest_input = max(path.stat().st_mtime_ns for path in input_paths)
    oldest_output = min(path.stat().st_mtime_ns for path in output_paths)
    freshness = oldest_output >= newest_input
    previous_same_input = bool(
        previous_report
        and previous_report.get("input_fingerprint") == input_fingerprint
    )
    deterministic_match = (
        previous_report.get("semantic_sha256") == outputs["semantic_sha256"]
        if previous_same_input
        else None
    )
    anchor_statuses = {
        anchor["anchor_id"]: anchor["status"] for anchor in outputs["anchors"]
    }
    status = (
        "PASS"
        if all(value == "PASS" for value in anchor_statuses.values())
        and freshness
        and deterministic_match is not False
        else "FAIL"
    )
    report = {
        "phase": "Phase 1 Five-Anchor Interactive MVP",
        "status": status,
        "generated_at": outputs["generated_at"],
        "input_fingerprint": input_fingerprint,
        "semantic_sha256": outputs["semantic_sha256"],
        "semantic_matches_previous_same_input": deterministic_match,
        "anchor_statuses": anchor_statuses,
        "anchors": outputs["anchors"],
        "enrichment": {
            "requested_count": len(enrichment["requested_ids"]),
            "success_count": enrichment["success_count"],
            "failure_count": enrichment["failure_count"],
            "cache_status_counts": enrichment["cache_status_counts"],
            "license_values": dict(
                Counter(
                    detail["source"]["license"]
                    for detail in enrichment["details"].values()
                )
            ),
        },
        "freshness": {
            "outputs_newer_than_all_inputs": freshness,
            "newest_input_mtime_ns": newest_input,
            "oldest_output_mtime_ns": oldest_output,
        },
        "v6_probe": {
            "gate": "COMPLETE",
            "capability": "NOT_EQUIVALENT",
            "outlier_count": outliers["outlier_count"],
            "outlier_path": str(V6_OUTLIERS_PATH),
        },
        "republican_era_probe": {
            "gate": "COMPLETE",
            "capability": "NOT_PUBLICLY_ACCESSIBLE",
            "integrated_into_phase1": False,
        },
        "generated_files": outputs["generated_files"],
    }
    write_json(PHASE1_REPORT_PATH, report)
    if status != "PASS":
        raise RuntimeError("Phase 1 data generation did not satisfy freshness/determinism")
    return report
