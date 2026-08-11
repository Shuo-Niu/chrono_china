from __future__ import annotations

from typing import Any

from .temporal import valid_for


class AssertionSelectionError(RuntimeError):
    pass


def select_preferred_location(
    assertions: list[dict[str, Any]], year: int
) -> dict[str, Any]:
    valid = [
        assertion
        for assertion in assertions
        if assertion.get("lon") is not None
        and assertion.get("lat") is not None
        and valid_for(assertion.get("valid_from"), assertion.get("valid_to"), year)
    ]
    if not valid:
        raise AssertionSelectionError(f"no location assertion is valid for year {year}")

    canonical = [assertion for assertion in valid if assertion.get("canonical_source")]
    candidates = canonical or valid

    confidence_values = [
        assertion["confidence"]
        for assertion in candidates
        if isinstance(assertion.get("confidence"), (int, float))
    ]
    if confidence_values:
        highest = max(confidence_values)
        candidates = [assertion for assertion in candidates if assertion.get("confidence") == highest]

    accuracy_values = [
        assertion["accuracy_radius_m"]
        for assertion in candidates
        if isinstance(assertion.get("accuracy_radius_m"), (int, float))
    ]
    if accuracy_values:
        smallest = min(accuracy_values)
        candidates = [
            assertion for assertion in candidates if assertion.get("accuracy_radius_m") == smallest
        ]

    coordinate_values = {(assertion["lon"], assertion["lat"]) for assertion in candidates}
    unresolved = len(coordinate_values) > 1
    selected = min(
        candidates,
        key=lambda assertion: (
            assertion.get("fallback_rank", 999),
            assertion.get("source_id", ""),
        ),
    )
    return {
        "status": "unresolved_conflict" if unresolved else "resolved",
        "selected": selected,
        "competing_assertions": valid,
        "selection_reason": (
            "canonical/time/confidence/accuracy rules did not uniquely resolve coordinates; "
            "deterministic fallback_rank used for display only"
            if unresolved
            else "time validity, canonical source, confidence and accuracy rules"
        ),
        "newest_write_wins_used": False,
    }
