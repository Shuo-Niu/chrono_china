from __future__ import annotations

import argparse
from typing import Any

from chronochina.config import QA_DIR
from chronochina.io import read_json, utc_now, write_json
from chronochina.qa.freeze import _files_for_patterns, _fingerprint


FREEZE_PATH = QA_DIR / "phase1_3_1d_input_freeze.json"

GROUPS: tuple[tuple[str, bool, tuple[str, ...]], ...] = (
    ("normalized_global_historical_index", True, (
        "data/raw/tgaz_index/tgaz_chgis_2016-07-06.csv",
        "data/raw/tgaz_index/manifest.json",
        "data/intermediate/tgaz_points.jsonl",
    )),
    ("current_viewport_query_index", True, (
        "data/processed/explore/tgaz_compact.json",
        "data/qa/phase1_3_1c_explore_generation.json",
        "data/qa/phase1_3_1c_five_anchor_viewport_parity.json",
    )),
    ("temporal_context_data", True, ("data/processed/temporal_context/*.json",)),
    ("five_anchor_regression_fixtures", True, (
        "data/processed/anchors/**/*",
        "data/processed/phase1_1/**/*",
        "data/intermediate/anchors.json",
    )),
    ("marker_alignment_qa", True, (
        "data/qa/marker_alignment/**/*",
        "data/qa/phase1_2_2_strategy_id_parity.json",
    )),
    ("geographic_plausibility_qa", True, ("data/qa/geographic_plausibility/**/*",)),
    ("r2_reference_configuration", True, (
        "web/src/map/referenceLayers.ts",
        "web/src/map/referenceReadiness.ts",
        "data/qa/phase1_3_1a_reference_source_report.md",
    )),
    ("v6_and_republican_access_evidence", True, (
        "data/qa/g6_v6_parity.json",
        "data/qa/republican_era_access_probe.md",
    )),
    ("phase1_3_1c_user_mode_screenshots", True, (
        "artifacts/phase1_3_1c/track_a/*.png",
        "artifacts/phase1_3_1c/track_b/*.png",
    )),
    ("display_family_registry", False, ("web/src/display/hierarchy.ts",)),
    ("semantic_zoom_thresholds", False, ("web/src/display/semanticZoom.ts",)),
    ("co_location_grouping_rules", False, ("web/src/display/semanticZoom.ts",)),
    ("focus_explore_rendering_configuration", False, (
        "web/src/App.tsx",
        "web/src/styles.css",
        "web/src/explore/viewportQuery.ts",
        "web/src/temporal/TemporalRail.tsx",
        "web/src/temporal/temporal.ts",
    )),
)


def _current_groups() -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for name, immutable, patterns in GROUPS:
        files = [_fingerprint(path) for path in _files_for_patterns(patterns)]
        if not files:
            raise FileNotFoundError(f"freeze group has no files: {name}")
        result.append({
            "name": name,
            "immutable": immutable,
            "patterns": list(patterns),
            "file_count": len(files),
            "total_size_bytes": sum(item["size_bytes"] for item in files),
            "files": files,
        })
    return result


def capture() -> dict[str, Any]:
    if FREEZE_PATH.exists():
        raise FileExistsError(f"freeze already exists: {FREEZE_PATH}")
    result = {
        "phase": "1.3.1d",
        "purpose": "freeze historical facts before unified timeline and map interaction work",
        "captured_at_utc": utc_now(),
        "result": "BASELINE_CAPTURED",
        "groups": _current_groups(),
    }
    write_json(FREEZE_PATH, result)
    return result


def verify() -> dict[str, Any]:
    baseline = read_json(FREEZE_PATH)
    current = {group["name"]: group for group in _current_groups()}
    immutable_changed = False
    groups: list[dict[str, Any]] = []
    for before_group in baseline["groups"]:
        after_group = current[before_group["name"]]
        before = {item["path"]: item for item in before_group["files"]}
        after = {item["path"]: item for item in after_group["files"]}
        files = []
        for path in sorted(before.keys() | after.keys()):
            before_item = before.get(path)
            after_item = after.get(path)
            unchanged = before_item == after_item
            if before_group["immutable"] and not unchanged:
                immutable_changed = True
            files.append({
                "path": path,
                "before_size_bytes": before_item["size_bytes"] if before_item else None,
                "after_size_bytes": after_item["size_bytes"] if after_item else None,
                "before_sha256": before_item["sha256"] if before_item else None,
                "after_sha256": after_item["sha256"] if after_item else None,
                "unchanged": unchanged,
            })
        groups.append({
            "name": before_group["name"],
            "immutable": before_group["immutable"],
            "unchanged": all(item["unchanged"] for item in files),
            "files": files,
        })
    result = {
        "phase": "1.3.1d",
        "purpose": baseline["purpose"],
        "captured_at_utc": baseline["captured_at_utc"],
        "verified_at_utc": utc_now(),
        "result": "IMMUTABLE_CHANGED" if immutable_changed else "UNCHANGED_IMMUTABLES",
        "groups": groups,
    }
    write_json(FREEZE_PATH, result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("capture", "verify"))
    args = parser.parse_args()
    print((capture() if args.action == "capture" else verify())["result"])


if __name__ == "__main__":
    main()
