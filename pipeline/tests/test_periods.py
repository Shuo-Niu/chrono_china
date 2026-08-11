from chronochina.periods import (
    candidate_change_years,
    select_representative_periods,
    snapshot_signature,
    unique_snapshot_events,
)


def rows() -> list[dict[str, object]]:
    return [
        {"tgaz_id": "a", "valid_from": 1, "valid_to": 5},
        {"tgaz_id": "b", "valid_from": 3, "valid_to": 7},
    ]


def test_closed_interval_candidates_include_end_plus_one_for_removal() -> None:
    assert candidate_change_years(rows()) == [1, 3, 5, 6, 7]
    assert snapshot_signature(rows(), 5) == ("a", "b")
    assert snapshot_signature(rows(), 6) == ("b",)


def test_identical_snapshots_are_deduplicated() -> None:
    events = unique_snapshot_events(rows())
    assert [(event["year"], event["signature"]) for event in events] == [
        (1, ("a",)),
        (3, ("a", "b")),
        (6, ("b",)),
    ]


def test_representative_period_manifest_is_explainable() -> None:
    periods = select_representative_periods(rows(), target_count=3)
    assert [period["year"] for period in periods] == [1, 3, 6]
    assert periods[0]["active_feature_count"] == 1
    assert periods[1]["added_since_previous"] == 1
    assert periods[2]["removed_since_previous"] == 1
    assert all(period["snapshot_signature_sha256"] for period in periods)


def test_empty_snapshot_input_returns_no_periods() -> None:
    assert select_representative_periods([], target_count=3) == []


def test_period_selection_is_deterministic() -> None:
    first = select_representative_periods(rows(), target_count=3)
    second = select_representative_periods(list(reversed(rows())), target_count=3)
    assert first == second


def test_max_year_respects_a_known_coverage_boundary() -> None:
    extended = rows() + [{"tgaz_id": "late", "valid_from": 8, "valid_to": 10}]
    periods = select_representative_periods(extended, target_count=3, max_year=7)
    assert all(period["year"] <= 7 for period in periods)
    assert all("late" not in snapshot_signature(extended, period["year"]) for period in periods)
