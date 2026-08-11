from __future__ import annotations

import json
from pathlib import Path

from chronochina.qa.phase1_4 import _compare, _interval_series


REPO_ROOT = Path(__file__).resolve().parents[2]
QA_ROOT = REPO_ROOT / "data/qa/source_upgrade"


def read_json(name: str) -> dict:
    return json.loads((QA_ROOT / name).read_text(encoding="utf-8"))


def test_interval_series_uses_closed_intervals_and_omits_year_zero() -> None:
    rows = [
        {"valid_from": -1, "valid_to": 1},
        {"valid_from": 1, "valid_to": 1},
    ]
    series = _interval_series(rows)
    assert 0 not in series
    assert series[-1] == 1
    assert series[1] == 2
    assert series[2] == 0


def test_candidate_without_shared_id_is_not_matched_by_name_or_coordinate() -> None:
    candidate = {
        "candidate_id": "hvd_new",
        "name": "同名",
        "feature_type": "县",
        "valid_from": 100,
        "valid_to": 110,
        "lon": 116.0,
        "lat": 40.0,
    }
    assert _compare(candidate, None)["classification"] == ["uncertain_match"]


def test_exact_id_parity_reports_coordinate_time_and_type_revisions() -> None:
    candidate = {
        "candidate_id": "hvd_1",
        "name": "甲县",
        "feature_type": "县",
        "valid_from": 100,
        "valid_to": 120,
        "lon": 116.1,
        "lat": 40.0,
    }
    canonical = {
        "tgaz_id": "hvd_1",
        "name_zh_hans": "甲县",
        "feature_type": "州",
        "valid_from": 101,
        "valid_to": 120,
        "lon": 116.0,
        "lat": 40.0,
    }
    classes = _compare(candidate, canonical)["classification"]
    assert "same_entity_revised_coordinate" in classes
    assert "same_entity_revised_time_interval" in classes
    assert "same_entity_revised_type" in classes


def test_settlement_coverage_keeps_v6_as_two_time_slices() -> None:
    payload = read_json("settlement_coverage_by_year.json")
    by_year = {row["year"]: row for row in payload["by_year"]}
    assert len(by_year) == 2133
    assert payload["candidate_layers"]["chgis_v6_towns"]["coverage_kind"] == "time_slice"
    assert by_year[1500]["chgis_v6_static_town_points"] == 0
    assert by_year[1820]["chgis_v6_static_town_points"] == 8659
    assert by_year[1911]["chgis_v6_static_town_points"] == 40020


def test_high_admin_coverage_distinguishes_static_province_from_time_series() -> None:
    payload = read_json("high_admin_coverage_by_year.json")
    by_year = {row["year"]: row for row in payload["by_year"]}
    assert by_year[750]["chgis_v6_static_province_points"] == 0
    assert by_year[750]["chgis_v6_prefecture_candidate_id_increment"] > 0
    assert by_year[1820]["chgis_v6_static_province_points"] == 24
    assert payload["candidate_layers"]["chgis_v6_province"]["coverage_kind"] == "time_slice"


def test_entity_parity_uses_exact_ids_and_accounts_for_invalid_coordinates() -> None:
    payload = read_json("entity_parity.json")
    summary = payload["summary"]
    assert summary["candidate_rows_with_invalid_coordinate"] == 10
    assert summary["exact_id_matches"] > 0
    assert summary["candidate_ids_absent_from_canonical"] > 0
    assert summary["genuinely_new_record_confirmed"] == 0
    assert payload["hartwell_parity"]["classification"] == "uncertain_match"


def test_source_access_catalog_records_actual_access_and_license_constraints() -> None:
    payload = read_json("source_access_catalog.json")
    sources = {source["name"]: source for source in payload["sources"]}
    assert sources["CHGIS V6"]["access_result"] == "success"
    assert sources["CHGIS V6"]["commercial_app"] == "separate_commercial_license_required"
    assert sources["Chinese Civilization in Time and Space (CCTS)"]["account_or_token"] is True
    assert sources["World Historical Gazetteer (WHG)"]["catalog_count"] > 0
