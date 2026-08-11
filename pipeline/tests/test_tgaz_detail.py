import pytest

from chronochina.tgaz_detail import DetailParseError, decode_tgaz_json, parse_tgaz_detail


def detail_payload() -> dict[str, object]:
    return {
        "system": "Test source system",
        "license": "CC BY-NC 4.0",
        "uri": "https://example.invalid/tgaz/test_1",
        "sys_id": "test_1",
        "sys_id of alternate": "",
        "spellings": [
            {"written form": "測試", "script": "traditional Chinese"},
            {"written form": "测试", "script": "simplified Chinese"},
            {"written form": "Ceshi", "transcribed in": "Pinyin"},
        ],
        "feature_type": {"name": "县", "English": "county"},
        "temporal": {"begin": "-10", "end": "10", "begin rule": "3", "end rule": "3"},
        "spatial": {
            "object_type": "POINT",
            "xy_type": "point",
            "latitude": "30.0",
            "longitude": "120.0",
            "source": "Test",
            "present_location": [],
        },
        "historical_context": {
            "part of": [{"parent id": "parent_1", "name": "上级"}],
            "subordinate units": [{"child id": "child_1", "name": "下级"}],
            "preceded by": [],
        },
        "data source": "CHGIS",
        "source note": "A source note",
        "source uri": "https://example.invalid/source",
    }


def test_api_parser_preserves_required_fields_and_relationship_evidence() -> None:
    parsed = parse_tgaz_detail(detail_payload())
    assert parsed["tgaz_id"] == "test_1"
    assert parsed["names"] == {
        "simplified_chinese": "测试",
        "traditional_chinese": "測試",
        "pinyin": "Ceshi",
        "all_spellings": detail_payload()["spellings"],
    }
    assert parsed["feature_type"]["name"] == "县"
    assert parsed["location"]["lat"] == 30.0
    assert parsed["temporal"]["valid_from"] == -10
    assert parsed["relationships"]["part_of"][0]["parent id"] == "parent_1"
    assert parsed["source"]["source_note"] == "A source note"
    assert parsed["source"]["license"] == "CC BY-NC 4.0"


def test_api_parser_rejects_response_without_canonical_id() -> None:
    with pytest.raises(DetailParseError, match="sys_id"):
        parse_tgaz_detail({"license": "CC BY-NC 4.0"})


def test_api_decoder_explicitly_handles_unescaped_control_characters() -> None:
    payload, mode, warning = decode_tgaz_json(
        b'{"sys_id":"hvd_1","source note":"line one\x0bline two"}'
    )
    assert payload["sys_id"] == "hvd_1"
    assert mode == "non_strict_control_characters"
    assert warning and "Invalid control character" in warning


def test_api_decoder_does_not_hide_other_invalid_json() -> None:
    with pytest.raises(ValueError):
        decode_tgaz_json(b'{"sys_id":')
