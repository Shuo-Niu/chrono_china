import csv
from pathlib import Path

import pytest

from chronochina.config import REQUIRED_TGAZ_FIELDS
from chronochina.tgaz_index import (
    SchemaError,
    load_normalized_points,
    normalize_tgaz_points,
    validate_tgaz_index,
)


def write_csv(path: Path, rows: list[dict[str, str]], fields: tuple[str, ...] = REQUIRED_TGAZ_FIELDS) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def complete_row(**overrides: str) -> dict[str, str]:
    row = {
        "TGAZ_ID": "test_1",
        "TGAZ_URI": "https://example.invalid/test_1",
        "DATA_SRC": "CHGIS",
        "NAME_SIM": "结构测试",
        "NAME_ENG": "Jiegou Ceshi",
        "BEG": "-10",
        "END": "10",
        "OBJ_TYPE": "Point",
        "X": "120.0",
        "Y": "30.0",
        "TYPE_SIM": "县",
        "TYPE_ENG": "xian",
        "PARTOF_ID": "parent_1",
        "PARTOF_SIM": "上级",
        "PARTOF_ENG": "Shangji",
    }
    row.update(overrides)
    return row


def test_schema_validation_reports_count_and_null_rate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "index.csv"
    write_csv(source, [complete_row(PARTOF_ID="", PARTOF_SIM="", PARTOF_ENG="")])
    monkeypatch.setattr("chronochina.tgaz_index.SCHEMA_REPORT_PATH", tmp_path / "schema.json")
    report = validate_tgaz_index(source)
    assert report["record_count"] == 1
    assert report["null_rates"]["PARTOF_ID"] == 1.0
    assert report["status"] == "PASS"


def test_schema_validation_rejects_missing_required_field(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "index.csv"
    fields = tuple(field for field in REQUIRED_TGAZ_FIELDS if field != "TGAZ_ID")
    write_csv(source, [{key: value for key, value in complete_row().items() if key in fields}], fields)
    monkeypatch.setattr("chronochina.tgaz_index.SCHEMA_REPORT_PATH", tmp_path / "schema.json")
    with pytest.raises(SchemaError, match="TGAZ_ID"):
        validate_tgaz_index(source)


def test_normalization_quarantines_duplicates_invalid_coordinates_and_times(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "index.csv"
    rows = [
        complete_row(TGAZ_ID="valid"),
        complete_row(TGAZ_ID="duplicate"),
        complete_row(TGAZ_ID="duplicate", NAME_SIM="冲突值"),
        complete_row(TGAZ_ID="bad_coord", X="999"),
        complete_row(TGAZ_ID="bad_time", BEG="20", END="10"),
        complete_row(TGAZ_ID="polygon", OBJ_TYPE="Polygon"),
    ]
    write_csv(source, rows)
    points_path = tmp_path / "points.jsonl"
    monkeypatch.setattr("chronochina.tgaz_index.NORMALIZED_POINTS_PATH", points_path)
    monkeypatch.setattr("chronochina.tgaz_index.QA_ISSUES_PATH", tmp_path / "issues.csv")
    monkeypatch.setattr("chronochina.tgaz_index.NORMALIZATION_REPORT_PATH", tmp_path / "report.json")
    report = normalize_tgaz_points(source)
    points = load_normalized_points(points_path)
    assert [point["tgaz_id"] for point in points] == ["valid"]
    assert report["qa_issue_types"] == {
        "duplicate_tgaz_id_quarantined": 2,
        "invalid_coordinate": 1,
        "invalid_time_bounds": 1,
    }
    assert report["skipped_non_point"] == {"Polygon": 1}
    assert report["observed_temporal_extent"] == {
        "min_valid_from": -10,
        "max_valid_to": 10,
        "valid_to_1912_count": 0,
        "valid_to_after_1912_count": 0,
    }
    assert points[0]["valid_from"] == -10
    assert points[0]["source_url"] == "https://example.invalid/test_1"
