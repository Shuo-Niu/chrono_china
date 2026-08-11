from chronochina.identity import feature_identity_violations, source_record_identity


def test_nearby_feature_has_no_automatic_lineage() -> None:
    feature = {
        "tgaz_id": "record_1",
        "relation_to_anchor": "spatial_nearby",
        "lineage_claim": None,
    }
    assert feature_identity_violations(feature) == []


def test_nearest_to_predecessor_or_rename_is_explicitly_rejected() -> None:
    predecessor = {
        "tgaz_id": "record_1",
        "relation_to_anchor": "spatial_nearby",
        "lineage_claim": None,
        "predecessor_of": "modern_anchor",
    }
    renamed = {
        "tgaz_id": "record_2",
        "relation_to_anchor": "spatial_nearby",
        "lineage_claim": "renamed_to",
        "renamed_to": "modern_anchor",
    }
    assert "forbidden_relation_key:predecessor_of" in feature_identity_violations(predecessor)
    assert "lineage_claim_generated_without_evidence" in feature_identity_violations(renamed)
    assert "forbidden_relation_key:renamed_to" in feature_identity_violations(renamed)


def test_coordinate_or_name_changes_do_not_change_source_identity() -> None:
    first = {"tgaz_id": "stable_id", "name": "名称甲", "lat": 30.0, "lon": 120.0}
    second = {"tgaz_id": "stable_id", "name": "名称乙", "lat": 31.0, "lon": 121.0}
    assert source_record_identity(first) == source_record_identity(second) == "stable_id"


def test_same_name_and_coordinate_do_not_merge_distinct_source_records() -> None:
    first = {"tgaz_id": "id_1", "name": "同名", "lat": 30.0, "lon": 120.0}
    second = {"tgaz_id": "id_2", "name": "同名", "lat": 30.0, "lon": 120.0}
    assert source_record_identity(first) != source_record_identity(second)
