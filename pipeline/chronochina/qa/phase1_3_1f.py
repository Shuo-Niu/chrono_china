from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping


BASELINE_FAMILIES: dict[str, set[str]] = {
    "high_admin": {"省", "王畿"},
    "regional_admin": {"郡", "府", "州", "直隶州", "路", "侯国", "厅", "军", "防镇"},
    "county": {"县"},
    "settlement": {"村镇", "亭"},
    "polity": {"政权", "国"},
}

# These decisions use the source TYPE_SIM taxonomy. Names are never inspected.
# The deliberately small set is limited to exact administrative-type synonyms
# whose level is unambiguous against an existing display family.
SAFE_RECLASSIFICATIONS: dict[str, str] = {
    "行省": "high_admin",
    "省级": "high_admin",
    "侨郡": "regional_admin",
    "军镇": "regional_admin",
    "道": "regional_admin",
    "监": "regional_admin",
    "侨县": "county",
}


def display_family(raw_type: str, *, revised: bool = True) -> str:
    for family, raw_types in BASELINE_FAMILIES.items():
        if raw_type in raw_types:
            return family
    if revised and raw_type in SAFE_RECLASSIFICATIONS:
        return SAFE_RECLASSIFICATIONS[raw_type]
    return "other"


def build_type_coverage_by_year(records: Iterable[Mapping[str, object]]) -> list[dict[str, object]]:
    rows = list(records)
    min_year = min(int(row["valid_from"]) for row in rows)
    max_year = max(int(row["valid_to"]) for row in rows)
    types = sorted({str(row["feature_type"]) for row in rows})
    keys = ["active", "settlement", "county", "regional_admin", "high_admin", "other"]
    diffs = {key: [0] * (max_year - min_year + 2) for key in keys}
    raw_diffs = {raw_type: [0] * (max_year - min_year + 2) for raw_type in types}

    for row in rows:
        begin = int(row["valid_from"])
        end = int(row["valid_to"])
        raw_type = str(row["feature_type"])
        family = display_family(raw_type)
        category = {
            "settlement": "settlement",
            "county": "county",
            "regional_admin": "regional_admin",
            "high_admin": "high_admin",
        }.get(family, "other")
        left = begin - min_year
        right = end - min_year + 1
        for key in ("active", category):
            diffs[key][left] += 1
            diffs[key][right] -= 1
        raw_diffs[raw_type][left] += 1
        raw_diffs[raw_type][right] -= 1

    running = {key: 0 for key in keys}
    raw_running = {raw_type: 0 for raw_type in types}
    result: list[dict[str, object]] = []
    for offset, year in enumerate(range(min_year, max_year + 1)):
        for key in keys:
            running[key] += diffs[key][offset]
        for raw_type in types:
            raw_running[raw_type] += raw_diffs[raw_type][offset]
        if year == 0:
            continue
        result.append({
            "year": year,
            "active_record_count": running["active"],
            "settlement_count": running["settlement"],
            "county_count": running["county"],
            "regional_admin_count": running["regional_admin"],
            "high_admin_count": running["high_admin"],
            "other_unclassified_count": running["other"],
            "by_raw_type": {
                raw_type: raw_running[raw_type]
                for raw_type in types
                if raw_running[raw_type]
            },
        })
    return result


def build_unclassified_audit(records: Iterable[Mapping[str, object]]) -> dict[str, object]:
    audited: list[dict[str, object]] = []
    reclassified = Counter()
    remaining = Counter()
    for row in records:
        raw_type = str(row["feature_type"])
        if display_family(raw_type, revised=False) != "other":
            continue
        revised = display_family(raw_type, revised=True)
        safe = revised != "other"
        if safe:
            reclassified[raw_type] += 1
        else:
            remaining[raw_type] += 1
        audited.append({
            "tgaz_id": row["tgaz_id"],
            "name": row["name_zh_hans"],
            "raw_type": raw_type,
            "source_type": raw_type,
            "parent": None if row.get("parent_name") in (None, "\\N") else row.get("parent_name"),
            "valid_period": [row["valid_from"], row["valid_to"]],
            "source_note": None,
            "current_reason": "raw TYPE_SIM was not listed in the Phase 1.3.1e display-family registry",
            "safe_mapping": revised if safe else None,
            "decision_basis": (
                "exact source TYPE_SIM taxonomy; no name-token inference"
                if safe
                else "retained as other: source taxonomy alone does not establish an existing display-family level"
            ),
        })
    return {
        "baseline_other_record_count": len(audited),
        "baseline_other_raw_type_count": len(reclassified) + len(remaining),
        "safely_reclassified_record_count": sum(reclassified.values()),
        "safely_reclassified_by_raw_type": dict(sorted(reclassified.items())),
        "remaining_unclassified_record_count": sum(remaining.values()),
        "remaining_unclassified_by_raw_type": dict(sorted(remaining.items())),
        "records": audited,
    }


def _load_points(path: Path) -> list[dict[str, object]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle]


def _compact_ids(path: Path) -> set[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {record[0] for record in payload["records"]}


def _raw_point_ids(path: Path) -> set[str]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return {
            row["TGAZ_ID"]
            for row in csv.DictReader(handle)
            if row["OBJ_TYPE"].strip().upper() == "POINT"
            and int(row["BEG"]) <= int(row["END"])
            and -180 <= float(row["X"]) <= 180
            and -90 <= float(row["Y"]) <= 90
        }


def generate(repo_root: Path) -> tuple[Path, Path, Path, Path]:
    points_path = repo_root / "data/intermediate/tgaz_points.jsonl"
    compact_path = repo_root / "data/processed/explore/tgaz_compact.json"
    raw_path = repo_root / "data/raw/tgaz_index/tgaz_chgis_2016-07-06.csv"
    points = _load_points(points_path)
    coverage = build_type_coverage_by_year(points)
    audit = build_unclassified_audit(points)
    normalized_ids = {str(row["tgaz_id"]) for row in points}
    compact_ids = _compact_ids(compact_path)
    raw_ids = _raw_point_ids(raw_path)
    generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    type_payload = {
        "phase": "1.3.1f",
        "generated_at_utc": generated_at,
        "canonical_source": "TGAZ CHGIS CSV snapshot 2016-07-06",
        "record_accounting": {
            "normalized_records": len(points),
            "compact_query_records": len(compact_ids),
            "normalized_missing_from_compact": sorted(normalized_ids - compact_ids),
            "compact_missing_from_normalized": sorted(compact_ids - normalized_ids),
            "raw_valid_point_ids": len(raw_ids),
            "raw_valid_points_missing_from_normalized": sorted(raw_ids - normalized_ids),
        },
        "classification": {
            "baseline_families": {key: sorted(value) for key, value in BASELINE_FAMILIES.items()},
            "safe_reclassifications": SAFE_RECLASSIFICATIONS,
            "method": "TYPE_SIM only; record names are not used",
        },
        "year_range": [coverage[0]["year"], coverage[-1]["year"]],
        "by_year": coverage,
    }
    audit_payload = {
        "phase": "1.3.1f",
        "generated_at_utc": generated_at,
        "canonical_source": "TGAZ CHGIS CSV snapshot 2016-07-06",
        "source_note_availability": (
            "The downloadable CSV has no source-note column; null is reported rather than fabricated. "
            "Canonical API detail remains a spot-check source, not a completeness source."
        ),
        **audit,
    }

    qa = repo_root / "data/qa"
    type_json = qa / "phase1_3_1f_type_coverage_by_year.json"
    type_md = qa / "phase1_3_1f_type_coverage_by_year.md"
    audit_json = qa / "phase1_3_1f_unclassified_audit.json"
    audit_md = qa / "phase1_3_1f_unclassified_audit.md"
    type_json.write_text(json.dumps(type_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    audit_json.write_text(json.dumps(audit_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    settlement = [row for row in points if row["feature_type"] == "村镇"]
    province = [row for row in points if row["feature_type"] == "省"]
    xingsheng = [row for row in points if row["feature_type"] == "行省"]
    type_md.write_text(
        "# Phase 1.3.1f type coverage by year\n\n"
        f"Generated from {len(points):,} canonical normalized records; normalized and compact ID sets "
        f"match: **{normalized_ids == compact_ids}**.\n\n"
        "## Findings\n\n"
        f"- `村镇`: {len(settlement):,} records; source periods are "
        f"{dict(sorted(Counter((r['valid_from'], r['valid_to']) for r in settlement).items()))}. "
        "The absence before 1820 and between the two snapshots is present in the source index, not introduced by normalization, exact-year, viewport, or layer filtering.\n"
        f"- `省`: {len(province):,} records, spanning {min(r['valid_from'] for r in province)}.."
        f"{max(r['valid_to'] for r in province)} and strongly Qing-weighted.\n"
        f"- `行省`: {len(xingsheng):,} source-typed records spanning "
        f"{min(r['valid_from'] for r in xingsheng)}..{max(r['valid_to'] for r in xingsheng)}. "
        "Phase 1.3.1e incorrectly left them in Other; Phase 1.3.1f maps the exact raw type to high_admin.\n"
        "- CHGIS V6 artifact in this repository is explicitly **Time Series County Points** (10,522 points); "
        "it is not a settlement or province layer and cannot establish that those two families are complete.\n\n"
        "## Accounting\n\n"
        f"- Raw valid point IDs: {len(raw_ids):,}\n"
        f"- Normalized IDs: {len(normalized_ids):,}\n"
        f"- Compact query IDs: {len(compact_ids):,}\n"
        f"- Unexplained normalized-to-query loss: {len(normalized_ids - compact_ids):,}\n\n"
        "The JSON companion contains every supported year and non-zero raw-type counts for that year.\n",
        encoding="utf-8",
    )
    focus = {"建陵侨县", "怀朔镇"}
    focus_rows = [row for row in audit["records"] if row["name"] in focus]
    audit_md.write_text(
        "# Phase 1.3.1f unclassified-type audit\n\n"
        f"Baseline Other contained **{audit['baseline_other_record_count']:,} records / "
        f"{audit['baseline_other_raw_type_count']} raw types**. "
        f"**{audit['safely_reclassified_record_count']:,} records** across "
        f"{len(audit['safely_reclassified_by_raw_type'])} exact source types were safely reclassified. "
        f"**{audit['remaining_unclassified_record_count']:,} records** remain conservative Other.\n\n"
        "No record name was parsed for classification, and no raw field was changed. The CSV has no "
        "source-note column, so the record-level JSON reports null instead of inventing provenance.\n\n"
        "## Required samples\n\n"
        + "\n".join(
            f"- `{row['tgaz_id']}` {row['name']}: raw/source type `{row['raw_type']}` → "
            f"`{row['safe_mapping']}`; basis: exact TYPE_SIM."
            for row in focus_rows
        )
        + "\n\n## Safe exact-type decisions\n\n"
        + "\n".join(
            f"- `{raw_type}` → `{family}` ({audit['safely_reclassified_by_raw_type'][raw_type]:,} records)"
            for raw_type, family in SAFE_RECLASSIFICATIONS.items()
        )
        + "\n\nAll remaining records and per-record reasons are in the JSON companion.\n",
        encoding="utf-8",
    )
    return type_json, type_md, audit_json, audit_md


if __name__ == "__main__":
    for generated in generate(Path(__file__).resolve().parents[3]):
        print(generated)
