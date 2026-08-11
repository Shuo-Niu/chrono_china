from chronochina.config import REQUIRED_TGAZ_FIELDS
from chronochina.qa.phase1_3_1e import build_year_density, classify_raw_rows


def test_ingestion_reconciliation_accounts_for_every_raw_row() -> None:
    base = {field: "\\N" for field in REQUIRED_TGAZ_FIELDS} | {
        "TGAZ_ID": "ok", "DATA_SRC": "CHGIS", "OBJ_TYPE": "POINT",
        "BEG": "1", "END": "2", "X": "110", "Y": "30",
    }
    rows = [
        base,
        {**base, "TGAZ_ID": "polygon", "OBJ_TYPE": "POLYGON"},
        {**base, "TGAZ_ID": "inverted", "BEG": "2", "END": "1"},
        {**base, "TGAZ_ID": "bad-coordinate", "X": "999"},
    ]
    categories, _ = classify_raw_rows(rows)
    assert sum(categories.values()) == len(rows)
    assert categories == {
        "valid_normalized_point": 1,
        "polygon_excluded": 1,
        "inverted_time_quarantined": 1,
        "invalid_coordinate": 1,
    }


def test_year_density_is_inclusive_and_omits_year_zero() -> None:
    density = build_year_density([
        {"valid_from": -1, "valid_to": 1, "feature_type": "县"},
        {"valid_from": 1, "valid_to": 2, "feature_type": "政权"},
    ])
    assert [item["year"] for item in density] == [-1, 1, 2]
    assert [item["total_active_records"] for item in density] == [1, 2, 1]
    assert density[1]["user_eligible_records_all_layers"] == 1
