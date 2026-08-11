from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Iterable

from chronochina.config import PROJECT_ROOT, QA_DIR
from chronochina.io import read_json, sha256_file, utc_now, write_json


FREEZE_PATH = QA_DIR / "phase1_2_1_input_freeze.json"

GROUP_SPECS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "tgaz_raw",
        (
            "data/raw/tgaz_index/tgaz_chgis_2016-07-06.csv",
            "data/raw/tgaz_index/manifest.json",
        ),
    ),
    ("normalized_historical_records", ("data/intermediate/tgaz_points.jsonl",)),
    (
        "tgaz_detail_cache",
        (
            "data/raw/tgaz_detail/**/*",
            "data/intermediate/tgaz_detail/**/*",
        ),
    ),
    ("representative_periods", ("data/intermediate/phase1_periods/*.json",)),
    (
        "five_anchor_definitions",
        (
            "data/intermediate/anchors.json",
            "data/processed/anchors/index.json",
            "data/processed/phase1_1/index.json",
        ),
    ),
    (
        "phase1_1_strategy_qa",
        (
            "data/qa/phase1_1_display_strategy_comparison.json",
            "data/qa/phase1_1_display_strategy_comparison.md",
            "data/qa/phase1_1_feature_type_distribution.json",
            "data/qa/phase1_1_feature_type_distribution.md",
            "data/qa/phase1_1_generation.json",
        ),
    ),
    (
        "v6_parity_original_input",
        (
            "data/raw/chgis_v6/**/*",
            "data/intermediate/chgis_v6/**/*",
            "data/qa/g6_v6_parity.json",
            "data/qa/v6_parity_outliers.json",
        ),
    ),
    (
        "processed_historical_slices",
        (
            "data/processed/anchors/**/*",
            "data/processed/phase1_1/**/*",
        ),
    ),
    (
        "phase1_2_screenshot_inputs",
        (
            "artifacts/phase1_2/*",
            "web/src/App.tsx",
            "web/src/styles.css",
            "web/src/map/referenceLayers.ts",
            "web/src/map/labelPriority.ts",
            "web/tests/e2e/phase1_2.spec.ts",
            "docs/phase1_2_report.md",
            "data/qa/phase1_2_reference_source_report.md",
        ),
    ),
)


def _relative(path: Path) -> str:
    return path.relative_to(PROJECT_ROOT).as_posix()


def _files_for_patterns(patterns: Iterable[str]) -> list[Path]:
    found: dict[str, Path] = {}
    for pattern in patterns:
        if not any(character in pattern for character in "*?["):
            literal = PROJECT_ROOT / pattern
            if not literal.is_file():
                raise FileNotFoundError(f"frozen input does not exist: {pattern}")
        for path in PROJECT_ROOT.glob(pattern):
            if path.is_file():
                found[_relative(path)] = path
    return [found[key] for key in sorted(found)]


def _fingerprint(path: Path) -> dict[str, Any]:
    return {
        "path": _relative(path),
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


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
        "phase": "1.2.1",
        "purpose": "immutable input baseline for Geographic Plausibility QA",
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
        current_paths = _files_for_patterns(group["patterns"])
        after = {_relative(path): _fingerprint(path) for path in current_paths}
        all_paths = sorted(before.keys() | after.keys())
        files: list[dict[str, Any]] = []
        for path in all_paths:
            before_item = before.get(path)
            after_item = after.get(path)
            unchanged = before_item == after_item
            changed = changed or not unchanged
            files.append(
                {
                    "path": path,
                    "before_size_bytes": (
                        before_item["size_bytes"] if before_item else None
                    ),
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
