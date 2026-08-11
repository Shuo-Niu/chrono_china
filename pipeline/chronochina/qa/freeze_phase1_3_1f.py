from __future__ import annotations

import argparse
from typing import Any

from chronochina.config import QA_DIR
from chronochina.io import read_json, utc_now, write_json
from chronochina.qa.freeze import _files_for_patterns, _fingerprint


FREEZE_PATH = QA_DIR / "phase1_3_1f_input_freeze.json"

GROUPS: tuple[tuple[str, bool, tuple[str, ...]], ...] = (
    ("historical_source", True, (
        "data/raw/tgaz_index/tgaz_chgis_2016-07-06.csv",
        "data/raw/tgaz_index/manifest.json",
        "data/raw/tgaz_index/readme.md",
        "data/intermediate/tgaz_points.jsonl",
        "data/processed/explore/tgaz_compact.json",
    )),
    ("v6_comparison_evidence", True, (
        "data/raw/chgis_v6/**/*",
        "data/intermediate/chgis_v6/**/*",
        "data/qa/g6_v6_parity.json",
    )),
    ("identity_and_geography_qa", True, (
        "data/qa/marker_alignment/**/*",
        "data/qa/geographic_plausibility/**/*",
        "data/qa/phase1_2_2_strategy_id_parity.json",
    )),
    ("five_anchor_fixtures", True, (
        "data/processed/anchors/**/*",
        "data/processed/phase1_1/**/*",
        "data/intermediate/anchors.json",
    )),
    ("display_family_registry", False, ("web/src/display/hierarchy.ts",)),
    ("detail_rendering", False, ("web/src/App.tsx",)),
    ("timeline_query_implementation", False, (
        "web/src/temporal/ContinuousTimeline.tsx",
        "web/src/explore/viewportQuery.ts",
        "web/src/App.tsx",
    )),
    ("reference_layer_configuration", True, (
        "web/src/map/referenceLayers.ts",
        "web/src/map/referenceReadiness.ts",
    )),
    ("phase1_3_1e_evidence", False, (
        "data/qa/phase1_3_1e_download_completeness.json",
        "data/qa/phase1_3_1e_ingestion_reconciliation.json",
        "data/qa/phase1_3_1e_year_density.json",
        "data/qa/phase1_3_1e_overlay_collision.json",
        "artifacts/phase1_3_1e/*.png",
    )),
)


def _current_groups() -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    for name, immutable, patterns in GROUPS:
        files = [_fingerprint(path) for path in _files_for_patterns(patterns)]
        if not files:
            raise FileNotFoundError(f"freeze group has no files: {name}")
        groups.append({
            "name": name,
            "immutable": immutable,
            "patterns": list(patterns),
            "file_count": len(files),
            "total_size_bytes": sum(item["size_bytes"] for item in files),
            "files": files,
        })
    return groups


def capture() -> dict[str, Any]:
    if FREEZE_PATH.exists():
        raise FileExistsError(f"freeze already exists: {FREEZE_PATH}")
    result = {
        "phase": "1.3.1f",
        "purpose": "freeze historical facts before type classification, crash hardening, and timeline reliability work",
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
        "phase": "1.3.1f",
        "purpose": baseline["purpose"],
        "captured_at_utc": baseline["captured_at_utc"],
        "verified_at_utc": utc_now(),
        "result": "IMMUTABLE_CHANGED" if immutable_changed else "UNCHANGED_IMMUTABLES",
        "groups": groups,
    }
    write_json(FREEZE_PATH, result)
    return result


def correct_classification() -> dict[str, Any]:
    """Recover the captured baseline after UI screenshots were misclassified immutable.

    This fails closed unless every changed immutable file belongs only to the
    Phase 1.3.1e UI-evidence group. Historical/source changes can never be
    re-baselined by this correction.
    """
    verified = read_json(FREEZE_PATH)
    changed_immutable_groups = [
        group["name"]
        for group in verified["groups"]
        if group["immutable"] and not group["unchanged"]
    ]
    if changed_immutable_groups != ["phase1_3_1e_evidence"]:
        raise RuntimeError(
            f"refusing classification correction; changed immutable groups: {changed_immutable_groups}"
        )
    current_immutability = {name: immutable for name, immutable, _patterns in GROUPS}
    groups = []
    for group in verified["groups"]:
        groups.append({
            "name": group["name"],
            "immutable": current_immutability[group["name"]],
            "patterns": [],
            "file_count": len(group["files"]),
            "total_size_bytes": sum(item["before_size_bytes"] or 0 for item in group["files"]),
            "files": [
                {
                    "path": item["path"],
                    "size_bytes": item["before_size_bytes"],
                    "sha256": item["before_sha256"],
                }
                for item in group["files"]
            ],
        })
    result = {
        "phase": "1.3.1f",
        "purpose": verified["purpose"],
        "captured_at_utc": verified["captured_at_utc"],
        "classification_corrected_at_utc": utc_now(),
        "classification_correction": (
            "Phase 1.3.1e screenshots are mutable UI evidence, not frozen historical facts"
        ),
        "result": "BASELINE_CAPTURED_CORRECTED_CLASSIFICATION",
        "groups": groups,
    }
    write_json(FREEZE_PATH, result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("capture", "verify", "correct-classification"))
    args = parser.parse_args()
    action = {
        "capture": capture,
        "verify": verify,
        "correct-classification": correct_classification,
    }[args.action]
    print(action()["result"])


if __name__ == "__main__":
    main()
