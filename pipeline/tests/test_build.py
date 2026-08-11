from chronochina.build import build_feature


def test_feature_contract_preserves_provenance_and_coordinate_conflict() -> None:
    row = {
        "tgaz_id": "test_1",
        "source_url": "https://example.invalid/csv/test_1",
        "name_zh_hans": "CSV 名称",
        "name_pinyin": "CSV Name",
        "valid_from": 100,
        "valid_to": 200,
        "lon": 120.0,
        "lat": 30.0,
        "feature_type": "县",
        "parent_name": "CSV 上级",
    }
    detail = {
        "tgaz_id": "test_1",
        "canonical_uri": "https://example.invalid/api/test_1",
        "names": {
            "simplified_chinese": "API 名称",
            "traditional_chinese": "API 名稱",
            "pinyin": "API Name",
            "all_spellings": [],
        },
        "feature_type": {"name": "县", "alternate_name": None, "transcription": "xian", "english": "county"},
        "location": {"lon": 120.1, "lat": 30.1},
        "temporal": {"valid_from": 100, "valid_to": 200},
        "relationships": {
            "part_of": [{"begin year": "100", "end year": "200", "name": "API 上级"}],
            "subordinate_units": [],
            "preceded_by": [],
        },
        "source": {
            "system": "Test",
            "data_source": "CHGIS",
            "source_note": "note",
            "source_uri": "",
            "license": "CC BY-NC 4.0",
        },
    }
    anchor = {"modern_location": {"lat": 30.0, "lon": 120.0}}
    feature, detail_card, conflict = build_feature(row, detail, anchor, 150)
    assert feature["geometry"]["coordinates"] == [120.1, 30.1]
    assert feature["properties"]["location_confidence"] == "unresolved_conflict"
    assert feature["properties"]["relation_to_anchor"] == "spatial_nearby"
    assert feature["properties"]["lineage_claim"] is None
    assert feature["properties"]["source_record_id"] == "test_1"
    assert feature["properties"]["license"] == "CC BY-NC 4.0"
    assert detail_card["parent_name"] == "API 上级"
    assert len(detail_card["location_assertion"]["competing_assertions"]) == 2
    assert conflict["newest_write_wins_used"] is False
