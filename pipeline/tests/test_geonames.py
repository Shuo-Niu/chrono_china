from pathlib import Path

import pytest

from chronochina.geonames import resolve_anchor, select_candidate


def record(
    geonameid: str,
    *,
    feature_class: str = "P",
    feature_code: str = "PPL",
    population: str = "100",
) -> dict[str, str]:
    return {
        "geonameid": geonameid,
        "name": "Test Place",
        "asciiname": "Test Place",
        "alternatenames": "测试地,Test Place",
        "latitude": "30.0",
        "longitude": "120.0",
        "feature_class": feature_class,
        "feature_code": feature_code,
        "country_code": "CN",
        "cc2": "",
        "admin1_code": "00",
        "admin2_code": "",
        "admin3_code": "",
        "admin4_code": "",
        "population": population,
        "elevation": "",
        "dem": "0",
        "timezone": "Asia/Shanghai",
        "modification_date": "2026-01-01",
    }


def test_resolver_prefers_populated_place_and_feature_rank() -> None:
    candidates = [
        record("1", feature_class="A", feature_code="ADM2", population="999999"),
        record("2", feature_code="PPL", population="500000"),
        record("3", feature_code="PPLA2", population="1000"),
    ]
    assert select_candidate(candidates)["geonameid"] == "3"


def test_anchor_keeps_query_record_id_coordinates_and_provenance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    selected = record("123", feature_code="PPLA2", population="50000")
    monkeypatch.setattr("chronochina.geonames.iter_geonames", lambda: iter([selected]))
    monkeypatch.setattr("chronochina.geonames.load_admin1_codes", lambda: {})
    monkeypatch.setattr("chronochina.geonames.RESOLUTION_RAW_DIR", tmp_path)
    manifest = {
        "artifact": {"sha256": "abc", "retrieved_at": "2026-01-02T03:04:05Z"},
        "license_notice_from_source": "Creative Commons Attribution 4.0",
    }
    anchor = resolve_anchor(
        {"anchor_id": "test", "query": "测试地", "display_name": "测试地"}, manifest
    )
    assert anchor["source"]["provider"] == "GeoNames"
    assert anchor["source"]["record_id"] == "123"
    assert anchor["source"]["retrieved_at"] == "2026-01-02T03:04:05Z"
    assert anchor["modern_location"] == {"lon": 120.0, "lat": 30.0}
    assert anchor["override_reason"] is None
    assert (tmp_path / "test.json").exists()
