from __future__ import annotations

import argparse
import hashlib
from typing import Any, Callable

from chronochina.config import PROJECT_ROOT, QA_DIR
from chronochina.io import read_json, utc_now, write_json
from chronochina.qa.freeze import _files_for_patterns, _fingerprint


FREEZE_PATH = QA_DIR / "phase1_3_1b_input_freeze.json"

FILE_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "five_anchor_manifest",
        ("data/intermediate/anchors.json", "data/processed/anchors/index.json"),
    ),
    (
        "representative_periods",
        (
            "data/intermediate/phase1_periods/*.json",
            "data/processed/anchors/*/manifest.json",
        ),
    ),
    (
        "processed_historical_slices",
        (
            "data/processed/anchors/*/slices/*",
            "data/processed/phase1_1/**/*",
            "data/processed/details/**/*",
        ),
    ),
    (
        "historical_source_type_fields",
        (
            "data/raw/tgaz_index/tgaz_chgis_2016-07-06.csv",
            "data/intermediate/tgaz_points.jsonl",
        ),
    ),
    (
        "strategy_c_outputs",
        (
            "data/qa/phase1_1_display_strategy_comparison.json",
            "data/qa/phase1_1_display_strategy_comparison.md",
            "data/qa/phase1_1_feature_type_distribution.json",
            "data/qa/phase1_1_feature_type_distribution.md",
            "data/qa/phase1_1_generation.json",
            "data/qa/phase1_2_2_strategy_id_parity.json",
        ),
    ),
    (
        "temporal_context_manifests",
        (
            "data/processed/temporal_context/*.json",
            "web/src/temporal/temporal.ts",
            "web/src/temporal/TemporalRail.tsx",
        ),
    ),
    (
        "r2_configuration",
        (
            "web/src/map/referenceLayers.ts",
            "web/src/map/referenceReadiness.ts",
            "data/qa/phase1_3_1a_reference_source_report.md",
        ),
    ),
    (
        "marker_alignment_qa",
        (
            "web/src/map/markerAlignment.ts",
            "data/qa/marker_alignment/**/*",
            "data/qa/phase1_2_2_input_freeze.json",
            "data/qa/phase1_2_2_strategy_id_parity.json",
            "docs/phase1_2_2_report.md",
            "artifacts/phase1_2_2/*",
        ),
    ),
    (
        "geographic_plausibility_qa",
        (
            "data/qa/phase1_2_1_input_freeze.json",
            "data/qa/phase1_2_1_geography_source_report.md",
            "data/qa/geographic_plausibility/**/*",
            "data/raw/modern_geography/openfreemap/**/*",
            "data/raw/geographic_plausibility/**/*",
            "docs/phase1_2_1_report.md",
            "artifacts/phase1_2_1/*",
        ),
    ),
    (
        "current_user_mode_screenshots",
        (
            "artifacts/phase1_3_1/*.png",
            "artifacts/phase1_3_1a/*-after.png",
        ),
    ),
)


def _strategy_c_point_ranking() -> str:
    source = (PROJECT_ROOT / "web/src/display/ranking.ts").read_text(encoding="utf-8")
    start = source.index("export function rankNearest")
    end = source.index("\n\nfunction localCoordinates", start)
    return source[start:end]


SEGMENT_GROUPS: tuple[tuple[str, str, Callable[[], str]], ...] = (
    (
        "strategy_c_point_ranking_code",
        "web/src/display/ranking.ts#strategy-c-point-ranking",
        _strategy_c_point_ranking,
    ),
)


def _segment_fingerprint(path: str, content: str) -> dict[str, Any]:
    payload = content.encode("utf-8")
    return {
        "path": path,
        "size_bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def _current_groups() -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    for name, patterns in FILE_GROUPS:
        files = [_fingerprint(path) for path in _files_for_patterns(patterns)]
        if not files:
            raise FileNotFoundError(f"freeze group has no files: {name}")
        groups.append({"name": name, "file_count": len(files), "files": files})
    for name, path, producer in SEGMENT_GROUPS:
        groups.append(
            {
                "name": name,
                "file_count": 1,
                "files": [_segment_fingerprint(path, producer())],
            }
        )
    return groups


def capture() -> dict[str, Any]:
    if FREEZE_PATH.exists():
        raise FileExistsError(f"freeze already exists: {FREEZE_PATH}")
    result = {
        "phase": "1.3.1b",
        "purpose": "immutable historical and non-display inputs for readability fix",
        "captured_at_utc": utc_now(),
        "result": "BASELINE_CAPTURED",
        "groups": _current_groups(),
    }
    write_json(FREEZE_PATH, result)
    return result


def verify() -> dict[str, Any]:
    baseline = read_json(FREEZE_PATH)
    current = {group["name"]: group for group in _current_groups()}
    changed = False
    groups: list[dict[str, Any]] = []
    for before_group in baseline["groups"]:
        after_group = current[before_group["name"]]
        before = {
            item["path"]: {
                "size_bytes": item.get("size_bytes", item.get("before_size_bytes")),
                "sha256": item.get("sha256", item.get("before_sha256")),
            }
            for item in before_group["files"]
        }
        after = {
            item["path"]: {
                "size_bytes": item["size_bytes"],
                "sha256": item["sha256"],
            }
            for item in after_group["files"]
        }
        files: list[dict[str, Any]] = []
        for path in sorted(before.keys() | after.keys()):
            before_item = before.get(path)
            after_item = after.get(path)
            unchanged = before_item == after_item
            changed = changed or not unchanged
            files.append(
                {
                    "path": path,
                    "before_size_bytes": before_item["size_bytes"] if before_item else None,
                    "after_size_bytes": after_item["size_bytes"] if after_item else None,
                    "before_sha256": before_item["sha256"] if before_item else None,
                    "after_sha256": after_item["sha256"] if after_item else None,
                    "unchanged": unchanged,
                }
            )
        groups.append(
            {
                "name": before_group["name"],
                "baseline_file_count": len(before),
                "current_file_count": len(after),
                "unchanged": all(item["unchanged"] for item in files),
                "files": files,
            }
        )
    result = {
        "phase": baseline["phase"],
        "purpose": baseline["purpose"],
        "captured_at_utc": baseline["captured_at_utc"],
        "verified_at_utc": utc_now(),
        "result": "CHANGED" if changed else "UNCHANGED",
        "groups": groups,
    }
    write_json(FREEZE_PATH, result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("capture", "verify"))
    args = parser.parse_args()
    result = capture() if args.action == "capture" else verify()
    print(result["result"])


if __name__ == "__main__":
    main()
