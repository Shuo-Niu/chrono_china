from chronochina.probe import probe_anchor, representative_years


def test_representative_years_come_from_actual_density() -> None:
    rows = [
        {"valid_from": -10, "valid_to": 10},
        {"valid_from": 100, "valid_to": 200},
        {"valid_from": 150, "valid_to": 250},
    ]
    years = representative_years(rows, slots=3)
    assert years
    assert all(-10 <= year <= 250 for year in years)
    assert any(150 <= year <= 200 for year in years)


def test_probe_reports_counts_without_claiming_lineage() -> None:
    anchor = {
        "anchor_id": "test",
        "modern_location": {"lat": 30.0, "lon": 120.0},
        "default_radius_km": 30.0,
    }
    rows = [
        {
            "tgaz_id": "record_1",
            "lat": 30.0,
            "lon": 120.1,
            "valid_from": -10,
            "valid_to": 200,
            "name_zh_hans": "结构测试",
            "parent_name": "结构上级",
            "feature_type": "县",
        }
    ]
    report = probe_anchor(rows, anchor)
    assert report["nonempty_period_count"] > 0
    assert "not historical lineage" in report["semantic_note"]
    for slice_ in report["slices"]:
        for result in slice_["sample"]:
            assert result["relation_to_anchor"] == "spatial_nearby"
            assert result["lineage_claim"] is None
