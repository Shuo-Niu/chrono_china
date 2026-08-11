import pytest

from chronochina.assertions import AssertionSelectionError, select_preferred_location


def assertion(source: str, lon: float, *, canonical: bool = True, **values: object) -> dict[str, object]:
    result: dict[str, object] = {
        "source_id": source,
        "lon": lon,
        "lat": 30.0,
        "valid_from": 100,
        "valid_to": 200,
        "canonical_source": canonical,
        "confidence": None,
        "accuracy_radius_m": None,
        "fallback_rank": 10,
    }
    result.update(values)
    return result


def test_selection_requires_current_time_validity() -> None:
    selected = select_preferred_location(
        [assertion("old", 119.0, valid_to=149), assertion("current", 120.0, valid_from=150)],
        175,
    )
    assert selected["selected"]["source_id"] == "current"


def test_canonical_then_confidence_then_accuracy() -> None:
    selected = select_preferred_location(
        [
            assertion("aux", 118.0, canonical=False, confidence=1.0, accuracy_radius_m=1),
            assertion("lower-confidence", 119.0, confidence=0.5, accuracy_radius_m=10),
            assertion("less-accurate", 120.0, confidence=0.9, accuracy_radius_m=100),
            assertion("preferred", 121.0, confidence=0.9, accuracy_radius_m=20),
        ],
        150,
    )
    assert selected["selected"]["source_id"] == "preferred"
    assert selected["status"] == "resolved"


def test_unresolved_conflict_preserves_all_candidates_without_newest_write_wins() -> None:
    selected = select_preferred_location(
        [assertion("csv", 120.0, fallback_rank=2), assertion("api", 121.0, fallback_rank=1)],
        150,
    )
    assert selected["status"] == "unresolved_conflict"
    assert selected["selected"]["source_id"] == "api"
    assert len(selected["competing_assertions"]) == 2
    assert selected["newest_write_wins_used"] is False


def test_missing_or_out_of_period_assertions_fail() -> None:
    with pytest.raises(AssertionSelectionError):
        select_preferred_location([assertion("future", 120.0, valid_from=300)], 150)
