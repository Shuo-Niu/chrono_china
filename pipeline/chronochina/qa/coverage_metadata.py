from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ..io import sha256_file, write_json
from .phase1_3_1f import display_family


PROJECT_ROOT = Path(__file__).resolve().parents[3]
CANONICAL_INDEX_PATH = "data/processed/explore/tgaz_compact.json"
REQUIRED_FIELDS = {"tgaz_id", "valid_from", "valid_to", "feature_type"}
SETTLEMENT_RAW_TYPES = {"村镇", "亭"}
HIGH_ADMIN_RAW_TYPES = {"王畿", "省", "行省", "省级"}
FAMILY_SUPPORT = {
    "settlement": "UNSUPPORTED",
    "high_admin": "LIMITED",
    "regional_admin": "SUPPORTED",
    "county": "SUPPORTED",
    "polity": "UNKNOWN",
    "other": "UNKNOWN",
}


def load_compact_index(path: Path) -> dict[str, object]:
    """Load and minimally validate tuple records against their declared fields."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"Compact index is not valid JSON: {path}") from error
    if not isinstance(payload, dict):
        raise ValueError("Compact index must be a JSON object")

    fields = payload.get("fields")
    records = payload.get("records")
    if not isinstance(fields, list) or not all(isinstance(field, str) for field in fields):
        raise ValueError("Compact index fields must be a list of strings")
    if len(fields) != len(set(fields)) or not REQUIRED_FIELDS.issubset(fields):
        raise ValueError("Compact index fields are missing required values")
    if not isinstance(records, list):
        raise ValueError("Compact index records must be a list")
    if any(not isinstance(record, list) or len(record) != len(fields) for record in records):
        raise ValueError("Compact index record tuple does not match declared fields")
    return payload


def _records(payload: Mapping[str, object]) -> list[dict[str, object]]:
    fields = payload["fields"]
    tuples = payload["records"]
    assert isinstance(fields, list)
    assert isinstance(tuples, list)
    return [dict(zip(fields, record, strict=True)) for record in tuples if isinstance(record, list)]


def _years(record: Mapping[str, object]) -> tuple[int, int]:
    begin = record["valid_from"]
    end = record["valid_to"]
    if isinstance(begin, bool) or isinstance(end, bool):
        raise ValueError("Compact index validity years must be integers")
    try:
        start_year = int(begin)
        end_year = int(end)
    except (TypeError, ValueError) as error:
        raise ValueError("Compact index validity years must be integers") from error
    if start_year > end_year:
        raise ValueError("Compact index has an inverted validity interval")
    return start_year, end_year


def derive_canonical_identity(path: Path, payload: Mapping[str, object]) -> dict[str, object]:
    records = _records(payload)
    if not records:
        raise ValueError("Compact index must contain records")
    intervals = [_years(record) for record in records]
    return {
        "path": CANONICAL_INDEX_PATH,
        "bytes": path.stat().st_size,
        "record_count": len(records),
        "sha256": sha256_file(path),
        "observed_envelope": {
            "min_year": min(begin for begin, _ in intervals),
            "max_year": max(end for _, end in intervals),
        },
    }


def _merged_periods(records: list[Mapping[str, object]]) -> list[list[int]]:
    intervals = sorted({_years(record) for record in records})
    merged: list[list[int]] = []
    for begin, end in intervals:
        if merged and begin <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([begin, end])
    return merged


def _component_id(raw_type: str) -> str:
    return "raw_" + "_".join(f"{ord(character):x}" for character in raw_type)


def _time_series_component(
    raw_type: str,
    records: list[Mapping[str, object]],
    support: str,
) -> dict[str, object]:
    return {
        "id": _component_id(raw_type),
        "raw_types": [raw_type],
        "temporal_model": "TIME_SERIES",
        "support": support,
        "supported_periods": _merged_periods(records),
        "record_count": len(records),
    }


def _settlement_components(records: list[Mapping[str, object]]) -> list[dict[str, object]]:
    by_type = {
        raw_type: [record for record in records if record["feature_type"] == raw_type]
        for raw_type in SETTLEMENT_RAW_TYPES
    }
    if set(raw_type for raw_type, rows in by_type.items() if rows) != SETTLEMENT_RAW_TYPES:
        raise ValueError("Settlement source types do not match the approved registry")

    towns = by_type["村镇"]
    town_counts: dict[str, int] = {}
    for record in towns:
        begin, end = _years(record)
        if begin != end or begin not in {1820, 1911}:
            raise ValueError("Village/town records must be approved exact-year snapshots")
        town_counts[str(begin)] = town_counts.get(str(begin), 0) + 1
    if town_counts != {"1820": 8659, "1911": 40031}:
        raise ValueError("Village/town snapshot counts do not match the frozen index")

    pavilions = by_type["亭"]
    pavilion_counts: dict[str, int] = {}
    for record in pavilions:
        begin, end = _years(record)
        key = f"{begin}..{end}"
        pavilion_counts[key] = pavilion_counts.get(key, 0) + 1
    if pavilion_counts != {"14..22": 17, "623..959": 1}:
        raise ValueError("Pavilion interval counts do not match the frozen index")

    return [
        {
            "id": "raw_town_snapshots",
            "raw_types": ["村镇"],
            "temporal_model": "TIME_SLICE",
            "support": "SUPPORTED",
            "snapshot_years": [1820, 1911],
            "snapshot_record_counts": town_counts,
        },
        {
            "id": "raw_pavilion_intervals",
            "raw_types": ["亭"],
            "temporal_model": "TIME_SERIES",
            "support": "UNKNOWN",
            "supported_periods": _merged_periods(pavilions),
            "period_record_counts": pavilion_counts,
        },
    ]


def build_coverage_metadata(compact_path: Path) -> dict[str, object]:
    payload = load_compact_index(compact_path)
    records = _records(payload)
    family_records: dict[str, list[dict[str, object]]] = {
        family: [] for family in FAMILY_SUPPORT
    }
    for record in records:
        raw_type = record["feature_type"]
        if not isinstance(raw_type, str):
            raise ValueError("Compact index feature_type values must be strings")
        family_records[display_family(raw_type)].append(record)

    settlement_types = {str(record["feature_type"]) for record in family_records["settlement"]}
    if settlement_types != SETTLEMENT_RAW_TYPES:
        raise ValueError("Settlement source types do not match the approved registry")
    high_admin_types = {str(record["feature_type"]) for record in family_records["high_admin"]}
    if high_admin_types != HIGH_ADMIN_RAW_TYPES:
        raise ValueError("High-admin source types do not match the approved registry")

    families: dict[str, dict[str, object]] = {}
    for family, support in FAMILY_SUPPORT.items():
        if family == "settlement":
            components = _settlement_components(family_records[family])
        else:
            by_type: dict[str, list[dict[str, object]]] = {}
            for record in family_records[family]:
                by_type.setdefault(str(record["feature_type"]), []).append(record)
            components = [
                _time_series_component(raw_type, by_type[raw_type], support)
                for raw_type in sorted(by_type)
            ]
        families[family] = {
            "default_support": support,
            "components": components,
        }

    return {
        "schema_version": "1.0",
        "canonical_index": derive_canonical_identity(compact_path, payload),
        "provenance": {
            "canonical_source": "TGAZ/CHGIS 2016 snapshot",
            "tgaz_documentation_envelope": {
                "min_year": -222,
                "max_year": 1911,
                "role": "provenance_note_only",
            },
        },
        "families": families,
    }


def validate_coverage_metadata(metadata: Mapping[str, object], compact_path: Path) -> None:
    payload = load_compact_index(compact_path)
    actual_identity = derive_canonical_identity(compact_path, payload)
    canonical_index = metadata.get("canonical_index")
    if not isinstance(canonical_index, Mapping):
        raise ValueError("Coverage metadata has no canonical index identity")
    if canonical_index.get("sha256") != actual_identity["sha256"]:
        raise ValueError("Coverage metadata SHA-256 does not match the compact index")
    if canonical_index.get("observed_envelope") != actual_identity["observed_envelope"]:
        raise ValueError("Coverage metadata envelope does not match the compact index")
    if canonical_index.get("record_count") != actual_identity["record_count"]:
        raise ValueError("Coverage metadata record count does not match the compact index")
    if canonical_index.get("bytes") != actual_identity["bytes"]:
        raise ValueError("Coverage metadata byte size does not match the compact index")
    if dict(metadata) != build_coverage_metadata(compact_path):
        raise ValueError("Coverage metadata components do not reconcile with the compact index")


def generate(repo_root: Path = PROJECT_ROOT) -> dict[str, object]:
    compact_path = repo_root / CANONICAL_INDEX_PATH
    unchanged_sha = sha256_file(compact_path)
    metadata = build_coverage_metadata(compact_path)
    validate_coverage_metadata(metadata, compact_path)

    metadata_path = repo_root / "data/metadata/historical_layer_coverage.json"
    processed_path = repo_root / "data/processed/coverage/historical_layer_coverage.json"
    write_json(metadata_path, metadata)
    write_json(processed_path, metadata)
    after_sha = sha256_file(compact_path)
    if after_sha != unchanged_sha:
        raise RuntimeError("Coverage generation modified the frozen compact index")

    evidence = {
        "phase": "1.4.1",
        "canonical_index": metadata["canonical_index"],
        "metadata_paths": {
            "versioned_source": "data/metadata/historical_layer_coverage.json",
            "processed_copy": "data/processed/coverage/historical_layer_coverage.json",
        },
        "source_index_reconciliation": {
            "metadata_valid": True,
            "frozen_index_sha256_before": unchanged_sha,
            "frozen_index_sha256_after": after_sha,
            "frozen_index_unchanged": True,
        },
    }
    write_json(repo_root / "data/qa/phase1_4_1_coverage_metadata_evidence.json", evidence)
    return metadata
