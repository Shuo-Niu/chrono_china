from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from chronochina.config import PROJECT_ROOT, QA_DIR
from chronochina.io import read_json, utc_now, write_json
from chronochina.qa.freeze import _files_for_patterns, _fingerprint, _relative


FREEZE_PATH = QA_DIR / "phase1_3_input_freeze.json"

GROUP_SPECS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "representative_periods_and_anchors",
        (
            "data/intermediate/phase1_periods/*.json",
            "data/intermediate/anchors.json",
            "data/processed/anchors/**/*",
        ),
    ),
    (
        "processed_historical_slices",
        (
            "data/processed/phase1_1/**/*",
            "data/processed/details/**/*",
        ),
    ),
    (
        "strategy_c",
        (
            "web/src/display/ranking.ts",
            "data/qa/phase1_1_display_strategy_comparison.json",
            "data/qa/phase1_1_display_strategy_comparison.md",
            "data/qa/phase1_1_feature_type_distribution.json",
            "data/qa/phase1_1_feature_type_distribution.md",
            "data/qa/phase1_1_generation.json",
            "data/qa/phase1_2_2_strategy_id_parity.json",
        ),
    ),
    (
        "r2_reference_configuration",
        (
            "web/src/map/referenceLayers.ts",
            "data/qa/phase1_2_reference_source_report.md",
            "docs/phase1_2_report.md",
        ),
    ),
    (
        "tgaz_cache",
        (
            "data/raw/tgaz_index/**/*",
            "data/intermediate/tgaz_points.jsonl",
            "data/raw/tgaz_detail/**/*",
            "data/intermediate/tgaz_detail/**/*",
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
)


def capture() -> dict[str, Any]:
    if FREEZE_PATH.exists():
        raise FileExistsError(f"freeze already exists: {FREEZE_PATH}")

    groups: list[dict[str, Any]] = []
    for name, patterns in GROUP_SPECS:
        files = _files_for_patterns(patterns)
        if not files:
            raise FileNotFoundError(f"freeze group has no files: {name}")
        fingerprints = [_fingerprint(path) for path in files]
        groups.append(
            {
                "name": name,
                "patterns": list(patterns),
                "file_count": len(fingerprints),
                "total_size_bytes": sum(item["size_bytes"] for item in fingerprints),
                "files": fingerprints,
            }
        )

    result = {
        "phase": "1.3",
        "purpose": "immutable inputs for Temporal Navigation and Historical Context",
        "captured_at_utc": utc_now(),
        "verification": None,
        "result": "BASELINE_CAPTURED",
        "groups": groups,
    }
    write_json(FREEZE_PATH, result)
    return result


def verify() -> dict[str, Any]:
    baseline = read_json(FREEZE_PATH)
    changed = False
    verified_groups: list[dict[str, Any]] = []

    for group in baseline["groups"]:
        before = {
            item["path"]: {
                "path": item["path"],
                "size_bytes": item.get("size_bytes", item.get("before_size_bytes")),
                "sha256": item.get("sha256", item.get("before_sha256")),
            }
            for item in group["files"]
        }
        after = {
            _relative(path): _fingerprint(path)
            for path in _files_for_patterns(group["patterns"])
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
        verified_groups.append(
            {
                "name": group["name"],
                "patterns": group["patterns"],
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
        "groups": verified_groups,
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
