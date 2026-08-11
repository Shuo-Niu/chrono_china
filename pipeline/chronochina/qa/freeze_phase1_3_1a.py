from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
from typing import Any, Callable

from chronochina.config import PROJECT_ROOT, QA_DIR
from chronochina.io import read_json, utc_now, write_json
from chronochina.qa.freeze import _files_for_patterns, _fingerprint, _relative


FREEZE_PATH = QA_DIR / "phase1_3_1a_input_freeze.json"

FILE_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "representative_snapshots",
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
        "strategy_c_artifacts",
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
        "temporal_context_manifests",
        (
            "data/processed/temporal_context/*.json",
            "web/src/temporal/temporal.ts",
            "web/src/temporal/TemporalRail.tsx",
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
    ("representative_visual_baseline", ("artifacts/phase1_3/*.png",)),
)


def _text(path: str) -> str:
    return (PROJECT_ROOT / path).read_text(encoding="utf-8")


def _between(path: str, start: str, end: str) -> str:
    source = _text(path)
    start_index = source.index(start)
    end_index = source.index(end, start_index)
    return source[start_index:end_index]


def _reference_non_r2() -> str:
    path = "web/src/map/referenceLayers.ts"
    pieces = [
        _between(path, '  {\n    id: "r0_grid",', '  {\n    id: "r1_physical",'),
        _between(path, '  {\n    id: "r1_physical",', '  {\n    id: "r2_minimal_modern",'),
        _between(path, '  {\n    id: "r3_modern_admin",', "];\n\nconst MODERN_REFERENCE_LAYERS"),
        _between(path, "  {\n    id: WATER_LAYER_ID,", "  {\n    id: WATERWAY_LAYER_ID,"),
        _between(path, "  {\n    id: WATERWAY_LAYER_ID,", "  {\n    id: SETTLEMENT_LABEL_LAYER_ID,"),
        _between(path, "  {\n    id: ADMIN_BOUNDARY_LAYER_ID,", "  {\n    id: ADMIN_LABEL_LAYER_ID,"),
        _between(path, "  {\n    id: ADMIN_LABEL_LAYER_ID,", "];\n\nexport function referenceMode"),
    ]
    return "\n--- frozen segment ---\n".join(pieces)


def _user_temporal_ui() -> str:
    return _between(
        "web/src/App.tsx",
        '        <section className="period-control" aria-label="代表时期">',
        '        {referenceModeId !== "r0_grid" && (',
    )


def _historical_marker_rendering() -> str:
    return _between(
        "web/src/App.tsx",
        "  useEffect(() => {\n    if (!mapReady || !map.current) return;\n    anchorMarker.current?.remove();",
        "\n\n  const activePeriod =",
    )


def _historical_marker_css() -> str:
    end = ".detail-card {" if ".detail-card {" in _text("web/src/styles.css") else ".detail-card,"
    return _between("web/src/styles.css", ".anchor-marker {", end)


SEGMENT_GROUPS: tuple[tuple[str, str, Callable[[], str]], ...] = (
    (
        "r0_r1_r3_definitions",
        "web/src/map/referenceLayers.ts#r0-r1-r3-definitions",
        _reference_non_r2,
    ),
    (
        "user_mode_temporal_ui",
        "web/src/App.tsx#user-mode-temporal-ui",
        _user_temporal_ui,
    ),
    (
        "historical_marker_rendering",
        "web/src/App.tsx#historical-marker-rendering",
        _historical_marker_rendering,
    ),
    (
        "historical_marker_css",
        "web/src/styles.css#historical-marker-css",
        _historical_marker_css,
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
        fingerprints = [_fingerprint(path) for path in _files_for_patterns(patterns)]
        if not fingerprints:
            raise FileNotFoundError(f"freeze group has no files: {name}")
        groups.append(
            {
                "name": name,
                "patterns": list(patterns),
                "file_count": len(fingerprints),
                "files": fingerprints,
            }
        )
    for name, path, producer in SEGMENT_GROUPS:
        groups.append(
            {
                "name": name,
                "patterns": [path],
                "file_count": 1,
                "files": [_segment_fingerprint(path, producer())],
            }
        )
    return groups


def capture() -> dict[str, Any]:
    if FREEZE_PATH.exists():
        raise FileExistsError(f"freeze already exists: {FREEZE_PATH}")
    result = {
        "phase": "1.3.1a",
        "purpose": "immutable non-R2 inputs for the R2 reference readiness fix",
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
                "path": item["path"],
                "size_bytes": item.get("size_bytes", item.get("before_size_bytes")),
                "sha256": item.get("sha256", item.get("before_sha256")),
            }
            for item in before_group["files"]
        }
        after = {item["path"]: item for item in after_group["files"]}
        files = []
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
