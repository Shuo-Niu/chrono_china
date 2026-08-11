from __future__ import annotations

import argparse
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from chronochina.io import read_json, write_json


REPO_ROOT = Path(__file__).resolve().parents[3]
FREEZE_PATH = REPO_ROOT / "data/qa/phase1_4_input_freeze.json"

GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("canonical_historical_source", (
        "data/raw/tgaz_index/tgaz_chgis_2016-07-06.csv",
        "data/raw/tgaz_index/manifest.json",
        "data/intermediate/tgaz_points.jsonl",
        "data/processed/explore/tgaz_compact.json",
    )),
    ("historical_semantics_and_mapping", (
        "web/src/display/hierarchy.ts",
        "web/src/display/semanticZoom.ts",
        "data/qa/identity_safety.json",
        "data/qa/geographic_plausibility/*.json",
        "data/qa/marker_alignment/*.json",
    )),
    ("frozen_product_ui", (
        "web/src/App.tsx",
        "web/src/styles.css",
        "web/src/temporal/ContinuousTimeline.tsx",
        "web/src/map/referenceLayers.ts",
        "web/src/map/referenceReadiness.ts",
    )),
    ("five_anchor_fixtures", (
        "data/processed/anchors/**/*.json",
        "data/processed/anchors/**/*.geojson",
    )),
    ("source_limitation_baseline", (
        "data/qa/phase1_3_1f_type_coverage_by_year.json",
        "data/qa/phase1_3_1f_unclassified_audit.json",
        "data/qa/g6_v6_parity.json",
        "docs/phase1_3_1f_report.md",
        "docs/phase1_3_1g_report.md",
    )),
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _files(patterns: tuple[str, ...]) -> list[dict[str, Any]]:
    paths: set[Path] = set()
    for pattern in patterns:
        paths.update(path for path in REPO_ROOT.glob(pattern) if path.is_file())
    if not paths:
        raise FileNotFoundError(f"freeze group matched no files: {patterns}")
    return [
        {
            "path": path.relative_to(REPO_ROOT).as_posix(),
            "size_bytes": path.stat().st_size,
            "sha256": _sha256(path),
        }
        for path in sorted(paths)
    ]


def _current_groups() -> list[dict[str, Any]]:
    return [
        {"name": name, "patterns": list(patterns), "files": _files(patterns)}
        for name, patterns in GROUPS
    ]


def capture() -> dict[str, Any]:
    if FREEZE_PATH.exists():
        raise FileExistsError(f"freeze already exists: {FREEZE_PATH}")
    result = {
        "phase": "1.4",
        "purpose": "freeze canonical history and product UI before source-upgrade research",
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
        before = {item["path"]: item for item in before_group["files"]}
        after = {item["path"]: item for item in current[before_group["name"]]["files"]}
        files = []
        for path in sorted(before.keys() | after.keys()):
            before_item = before.get(path)
            after_item = after.get(path)
            unchanged = before_item == after_item
            changed = changed or not unchanged
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
            "unchanged": all(item["unchanged"] for item in files),
            "files": files,
        })
    result = {
        "phase": "1.4",
        "purpose": baseline["purpose"],
        "captured_at_utc": baseline["captured_at_utc"],
        "verified_at_utc": utc_now(),
        "result": "CHANGED" if changed else "UNCHANGED_IMMUTABLES",
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
