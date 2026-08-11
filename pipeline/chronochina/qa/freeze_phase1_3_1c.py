from __future__ import annotations

import argparse
import hashlib
from typing import Any, Callable

from chronochina.config import PROJECT_ROOT, QA_DIR
from chronochina.io import read_json, utc_now, write_json
from chronochina.qa.freeze import _files_for_patterns, _fingerprint


FREEZE_PATH = QA_DIR / "phase1_3_1c_input_freeze.json"

# Phase 1.3.1g explicitly authorizes adding a user-selectable basemap while
# preserving the historical source. The old R2 file freeze therefore remains
# evidence of change, but no longer represents an immutable factual input.
SUBSEQUENTLY_AUTHORIZED_GROUPS = {"r2_reference_configuration"}

IMMUTABLE_FILE_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "normalized_historical_index",
        (
            "data/raw/tgaz_index/tgaz_chgis_2016-07-06.csv",
            "data/raw/tgaz_index/manifest.json",
            "data/intermediate/tgaz_points.jsonl",
        ),
    ),
    (
        "five_anchor_processed_slices",
        (
            "data/intermediate/anchors.json",
            "data/processed/anchors/**/*",
            "data/processed/phase1_1/**/*",
        ),
    ),
    (
        "strategy_c_artifacts",
        (
            "data/qa/phase1_1_display_strategy_comparison.json",
            "data/qa/phase1_1_display_strategy_comparison.md",
            "data/qa/phase1_2_2_strategy_id_parity.json",
        ),
    ),
    (
        "temporal_context_manifests",
        ("data/processed/temporal_context/*.json",),
    ),
    (
        "marker_alignment_qa",
        (
            "data/qa/marker_alignment/**/*",
            "data/qa/phase1_2_2_strategy_id_parity.json",
            "docs/phase1_2_2_report.md",
        ),
    ),
    (
        "geographic_plausibility_qa",
        (
            "data/qa/geographic_plausibility/**/*",
            "data/qa/phase1_2_1_geography_source_report.md",
            "docs/phase1_2_1_report.md",
        ),
    ),
    (
        "r2_reference_configuration",
        (
            "web/src/map/referenceLayers.ts",
            "web/src/map/referenceReadiness.ts",
            "data/qa/phase1_3_1a_reference_source_report.md",
        ),
    ),
    (
        "prior_user_mode_screenshots",
        (
            "artifacts/phase1_3_1/*.png",
            "artifacts/phase1_3_1a/*-after.png",
            "artifacts/phase1_3_1b/user_mode/*.png",
            "artifacts/phase1_3_1b/zoom_labels/*.png",
        ),
    ),
    (
        "detail_source_content",
        (
            "data/intermediate/tgaz_detail/*.json",
            "data/processed/details/**/*.json",
        ),
    ),
)

AUTHORIZED_DISPLAY_FILE_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "display_family_registry_baseline",
        ("web/src/display/hierarchy.ts",),
    ),
    (
        "temporal_ui_baseline",
        ("web/src/temporal/temporal.ts", "web/src/temporal/TemporalRail.tsx"),
    ),
    (
        "user_mode_legend_and_detail_baseline",
        ("web/src/App.tsx", "web/src/styles.css"),
    ),
)


def _strategy_c_point_ranking() -> str:
    source = (PROJECT_ROOT / "web/src/display/ranking.ts").read_text(encoding="utf-8")
    start = source.index("export function rankNearest")
    end = source.index("\n\nfunction localCoordinates", start)
    return source[start:end]


def _legend_configuration() -> str:
    source = (PROJECT_ROOT / "web/src/App.tsx").read_text(encoding="utf-8")
    start = source.index('<aside className="legend"')
    end = source.index("</aside>", start) + len("</aside>")
    return source[start:end]


def _name_display_policy() -> str:
    source = (PROJECT_ROOT / "web/src/App.tsx").read_text(encoding="utf-8")
    start = source.index("const labelPresentation")
    end = source.index("\n\n  const openDetail", start)
    return source[start:end]


SEGMENT_GROUPS: tuple[tuple[str, str, bool, Callable[[], str]], ...] = (
    (
        "strategy_c_point_ranking_code",
        "web/src/display/ranking.ts#strategy-c-point-ranking",
        True,
        _strategy_c_point_ranking,
    ),
    (
        "legend_configuration_baseline",
        "web/src/App.tsx#legend",
        False,
        _legend_configuration,
    ),
    (
        "name_display_policy_baseline",
        "web/src/App.tsx#name-display-policy",
        False,
        _name_display_policy,
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
    for immutable, specs in (
        (True, IMMUTABLE_FILE_GROUPS),
        (False, AUTHORIZED_DISPLAY_FILE_GROUPS),
    ):
        for name, patterns in specs:
            files = [_fingerprint(path) for path in _files_for_patterns(patterns)]
            if not files:
                raise FileNotFoundError(f"freeze group has no files: {name}")
            groups.append(
                {
                    "name": name,
                    "immutable": immutable,
                    "patterns": list(patterns),
                    "file_count": len(files),
                    "total_size_bytes": sum(item["size_bytes"] for item in files),
                    "files": files,
                }
            )
    for name, path, immutable, producer in SEGMENT_GROUPS:
        item = _segment_fingerprint(path, producer())
        groups.append(
            {
                "name": name,
                "immutable": immutable,
                "file_count": 1,
                "total_size_bytes": item["size_bytes"],
                "files": [item],
            }
        )
    return groups


def capture() -> dict[str, Any]:
    if FREEZE_PATH.exists():
        raise FileExistsError(f"freeze already exists: {FREEZE_PATH}")
    result = {
        "phase": "1.3.1c",
        "purpose": "freeze factual inputs before semantic-zoom and viewport work",
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
        immutable = (
            before_group["immutable"]
            and before_group["name"] not in SUBSEQUENTLY_AUTHORIZED_GROUPS
        )
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
            if immutable and not unchanged:
                immutable_changed = True
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
                "immutable": immutable,
                "subsequently_authorized": before_group["name"] in SUBSEQUENTLY_AUTHORIZED_GROUPS,
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
        "result": "IMMUTABLE_CHANGED" if immutable_changed else "UNCHANGED_IMMUTABLES",
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
