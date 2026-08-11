from __future__ import annotations

import csv
import json
import math
import os
from collections import Counter
from pathlib import Path
from typing import Any

from .config import (
    INTERMEDIATE_DIR,
    QA_DIR,
    REQUIRED_TGAZ_FIELDS,
    TGAZ_INDEX_MANIFEST_PATH,
    TGAZ_INDEX_PATH,
    TGAZ_INDEX_README_PATH,
    TGAZ_INDEX_README_URL,
    TGAZ_INDEX_URL,
)
from .io import download_file, utc_now, write_json
from .temporal import parse_year


NORMALIZED_POINTS_PATH = INTERMEDIATE_DIR / "tgaz_points.jsonl"
SCHEMA_REPORT_PATH = QA_DIR / "g0_tgaz_schema_report.json"
NORMALIZATION_REPORT_PATH = QA_DIR / "tgaz_normalization_report.json"
QA_ISSUES_PATH = QA_DIR / "tgaz_qa_issues.csv"

FIELD_MAPPING = {
    "TGAZ_ID": "tgaz_id",
    "TGAZ_URI": "source_url",
    "DATA_SRC": "data_source",
    "NAME_SIM": "name_zh_hans",
    "NAME_ENG": "name_pinyin",
    "BEG": "valid_from",
    "END": "valid_to",
    "OBJ_TYPE": "source_object_type",
    "X": "lon",
    "Y": "lat",
    "TYPE_SIM": "feature_type",
    "TYPE_ENG": "feature_type_pinyin",
    "PARTOF_ID": "parent_source_id",
    "PARTOF_SIM": "parent_name",
    "PARTOF_ENG": "parent_name_pinyin",
}

FIELD_VALUE_MAPPING = {
    "OBJ_TYPE": {"POINT": "Point", "POLYGON": "Polygon"},
}


class SchemaError(RuntimeError):
    pass


def fetch_tgaz_index() -> dict[str, Any]:
    try:
        index_artifact = download_file(TGAZ_INDEX_URL, TGAZ_INDEX_PATH)
        readme_artifact = download_file(TGAZ_INDEX_README_URL, TGAZ_INDEX_README_PATH)
    except Exception as error:
        write_json(
            QA_DIR / "g0_fetch_error.json",
            {
                "gate": "G0",
                "status": "FAIL",
                "observed_at": utc_now(),
                "source_url": TGAZ_INDEX_URL,
                "error_type": type(error).__name__,
                "error": str(error),
            },
        )
        raise

    manifest = {
        "dataset": "TGAZ CHGIS CSV snapshot",
        "snapshot_date": "2016-07-06",
        "documented_record_count": 71647,
        "source_repository": "https://github.com/cga-harvard/tgaz",
        "artifact": index_artifact,
        "source_notice": readme_artifact,
        "license_scope_note": (
            "Repository README labels TGaz software GPL-3.0; historical record content "
            "license must be retained separately from canonical API responses."
        ),
        "manifest_generated_at": utc_now(),
    }
    write_json(TGAZ_INDEX_MANIFEST_PATH, manifest)
    return manifest


def _read_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        fieldnames = reader.fieldnames or []
        return fieldnames, list(reader)


def validate_tgaz_index(path: Path = TGAZ_INDEX_PATH) -> dict[str, Any]:
    fieldnames, rows = _read_rows(path)
    missing_fields = sorted(set(REQUIRED_TGAZ_FIELDS) - set(fieldnames))
    null_counts = {
        field: sum(not (row.get(field) or "").strip() for row in rows)
        for field in REQUIRED_TGAZ_FIELDS
        if field in fieldnames
    }
    ids = [(row.get("TGAZ_ID") or "").strip() for row in rows]
    duplicate_ids = sorted(key for key, count in Counter(ids).items() if key and count > 1)
    report = {
        "gate": "G0",
        "source_path": str(path),
        "validated_at": utc_now(),
        "encoding": "utf-8-sig",
        "record_count": len(rows),
        "documented_record_count": 71647,
        "record_count_matches_document": len(rows) == 71647,
        "schema": fieldnames,
        "required_fields": list(REQUIRED_TGAZ_FIELDS),
        "missing_required_fields": missing_fields,
        "null_counts": null_counts,
        "null_rates": {
            field: round(count / len(rows), 8) if rows else None
            for field, count in null_counts.items()
        },
        "duplicate_tgaz_id_count": len(duplicate_ids),
        "duplicate_tgaz_ids_sample": duplicate_ids[:20],
        "field_mapping": FIELD_MAPPING,
        "field_value_mapping": FIELD_VALUE_MAPPING,
        "status": "PASS" if rows and not missing_fields else "FAIL",
    }
    write_json(SCHEMA_REPORT_PATH, report)
    if not rows:
        raise SchemaError("TGAZ index contains no records")
    if missing_fields:
        raise SchemaError(f"TGAZ index is missing required fields: {missing_fields}")
    return report


def _parse_coordinate(raw: str, lower: float, upper: float) -> float | None:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) and lower <= value <= upper else None


def normalize_tgaz_points(path: Path = TGAZ_INDEX_PATH) -> dict[str, Any]:
    _, rows = _read_rows(path)
    id_counts = Counter((row.get("TGAZ_ID") or "").strip() for row in rows)
    output_rows: list[dict[str, Any]] = []
    issues: list[dict[str, str]] = []
    skipped_sources: Counter[str] = Counter()
    skipped_object_types: Counter[str] = Counter()

    for row_number, row in enumerate(rows, start=2):
        tgaz_id = (row.get("TGAZ_ID") or "").strip()
        if not tgaz_id:
            issues.append(
                {"row": str(row_number), "tgaz_id": "", "issue": "missing_tgaz_id", "raw_beg": row.get("BEG", ""), "raw_end": row.get("END", ""), "raw_x": row.get("X", ""), "raw_y": row.get("Y", "")}
            )
            continue
        if id_counts[tgaz_id] > 1:
            issues.append(
                {"row": str(row_number), "tgaz_id": tgaz_id, "issue": "duplicate_tgaz_id_quarantined", "raw_beg": row.get("BEG", ""), "raw_end": row.get("END", ""), "raw_x": row.get("X", ""), "raw_y": row.get("Y", "")}
            )
            continue

        data_source = (row.get("DATA_SRC") or "").strip()
        raw_object_type = (row.get("OBJ_TYPE") or "").strip()
        normalized_object_type = FIELD_VALUE_MAPPING["OBJ_TYPE"].get(
            raw_object_type.upper(), raw_object_type
        )
        if data_source != "CHGIS":
            skipped_sources[data_source or "<missing>"] += 1
            continue
        if normalized_object_type != "Point":
            skipped_object_types[raw_object_type or "<missing>"] += 1
            continue

        valid_from = parse_year(row.get("BEG"))
        valid_to = parse_year(row.get("END"))
        if valid_from is None or valid_to is None or valid_from > valid_to:
            issues.append(
                {"row": str(row_number), "tgaz_id": tgaz_id, "issue": "invalid_time_bounds", "raw_beg": row.get("BEG", ""), "raw_end": row.get("END", ""), "raw_x": row.get("X", ""), "raw_y": row.get("Y", "")}
            )
            continue
        lon = _parse_coordinate(row.get("X") or "", -180, 180)
        lat = _parse_coordinate(row.get("Y") or "", -90, 90)
        if lon is None or lat is None:
            issues.append(
                {"row": str(row_number), "tgaz_id": tgaz_id, "issue": "invalid_coordinate", "raw_beg": row.get("BEG", ""), "raw_end": row.get("END", ""), "raw_x": row.get("X", ""), "raw_y": row.get("Y", "")}
            )
            continue

        output_rows.append(
            {
                "tgaz_id": tgaz_id,
                "source_url": (row.get("TGAZ_URI") or "").strip(),
                "data_source": data_source,
                "name_zh_hans": (row.get("NAME_SIM") or "").strip(),
                "name_pinyin": (row.get("NAME_ENG") or "").strip(),
                "valid_from": valid_from,
                "valid_to": valid_to,
                "source_object_type": normalized_object_type,
                "source_object_type_raw": raw_object_type,
                "lon": lon,
                "lat": lat,
                "feature_type": (row.get("TYPE_SIM") or "").strip(),
                "feature_type_pinyin": (row.get("TYPE_ENG") or "").strip(),
                "parent_source_id": (row.get("PARTOF_ID") or "").strip() or None,
                "parent_name": (row.get("PARTOF_SIM") or "").strip() or None,
                "parent_name_pinyin": (row.get("PARTOF_ENG") or "").strip() or None,
                "location_confidence": "source_point",
            }
        )

    NORMALIZED_POINTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = NORMALIZED_POINTS_PATH.with_name(f"{NORMALIZED_POINTS_PATH.name}.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        for row in output_rows:
            stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    os.replace(temporary, NORMALIZED_POINTS_PATH)

    QA_ISSUES_PATH.parent.mkdir(parents=True, exist_ok=True)
    with QA_ISSUES_PATH.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=("row", "tgaz_id", "issue", "raw_beg", "raw_end", "raw_x", "raw_y"),
        )
        writer.writeheader()
        writer.writerows(issues)

    report = {
        "normalized_at": utc_now(),
        "source_record_count": len(rows),
        "normalized_chgis_point_count": len(output_rows),
        "observed_temporal_extent": {
            "min_valid_from": min(
                (row["valid_from"] for row in output_rows), default=None
            ),
            "max_valid_to": max(
                (row["valid_to"] for row in output_rows), default=None
            ),
            "valid_to_1912_count": sum(
                row["valid_to"] == 1912 for row in output_rows
            ),
            "valid_to_after_1912_count": sum(
                row["valid_to"] > 1912 for row in output_rows
            ),
        },
        "qa_issue_count": len(issues),
        "qa_issue_types": dict(Counter(issue["issue"] for issue in issues)),
        "skipped_non_chgis": dict(skipped_sources),
        "skipped_non_point": dict(skipped_object_types),
        "normalized_path": str(NORMALIZED_POINTS_PATH),
        "qa_issues_path": str(QA_ISSUES_PATH),
    }
    write_json(NORMALIZATION_REPORT_PATH, report)
    return report


def load_normalized_points(path: Path = NORMALIZED_POINTS_PATH) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]
