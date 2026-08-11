from chronochina.qa.phase1_3_1f import (
    build_type_coverage_by_year,
    build_unclassified_audit,
    display_family,
)


def record(record_id: str, raw_type: str, begin: int, end: int) -> dict[str, object]:
    return {
        "tgaz_id": record_id,
        "name_zh_hans": "name tokens are irrelevant",
        "feature_type": raw_type,
        "valid_from": begin,
        "valid_to": end,
        "parent_name": None,
    }


def test_type_coverage_is_inclusive_and_accounts_by_raw_type() -> None:
    coverage = build_type_coverage_by_year([
        record("village", "村镇", -1, 1),
        record("province", "行省", 1, 2),
        record("unknown", "未知类型", 2, 2),
    ])
    assert [row["year"] for row in coverage] == [-1, 1, 2]
    assert coverage[1]["active_record_count"] == 2
    assert coverage[1]["settlement_count"] == 1
    assert coverage[1]["high_admin_count"] == 1
    assert coverage[2]["by_raw_type"] == {"未知类型": 1, "行省": 1}


def test_unclassified_mapping_uses_source_type_not_name_tokens() -> None:
    assert display_family("侨县") == "county"
    assert display_family("军镇") == "regional_admin"
    assert display_family("行省") == "high_admin"
    assert display_family("未知类型") == "other"
    audit = build_unclassified_audit([
        record("safe", "侨县", 1, 2),
        record("not-name-guessed", "未知类型", 1, 2),
    ])
    assert audit["safely_reclassified_record_count"] == 1
    assert audit["remaining_unclassified_record_count"] == 1
