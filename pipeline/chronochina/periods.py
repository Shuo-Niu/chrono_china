from __future__ import annotations

import hashlib
from typing import Any

from .temporal import valid_for


ALGORITHM_VERSION = "snapshot-change-segments-v1"
DEFAULT_PERIOD_COUNT = 4
MIN_PERIOD_COUNT = 3
MAX_PERIOD_COUNT = 6


def snapshot_signature(rows: list[dict[str, Any]], year: int) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                row["tgaz_id"]
                for row in rows
                if valid_for(row.get("valid_from"), row.get("valid_to"), year)
            }
        )
    )


def candidate_change_years(
    rows: list[dict[str, Any]], *, max_year: int | None = None
) -> list[int]:
    """Return real BEG/END events plus END+1 for closed-interval removals."""
    if not rows:
        return []
    observed_last_year = max(row["valid_to"] for row in rows)
    last_supported_year = min(observed_last_year, max_year) if max_year is not None else observed_last_year
    years: set[int] = set()
    for row in rows:
        if row["valid_from"] <= last_supported_year:
            years.add(row["valid_from"])
        if row["valid_to"] <= last_supported_year:
            years.add(row["valid_to"])
        if row["valid_to"] < last_supported_year:
            years.add(row["valid_to"] + 1)
    return sorted(year for year in years if year <= last_supported_year)


def unique_snapshot_events(
    rows: list[dict[str, Any]], *, max_year: int | None = None
) -> list[dict[str, Any]]:
    """Build chronological, globally unique, non-empty active-ID snapshots."""
    events: list[dict[str, Any]] = []
    seen: set[tuple[str, ...]] = set()
    previous_actual: set[str] = set()

    for year in candidate_change_years(rows, max_year=max_year):
        signature = snapshot_signature(rows, year)
        active = set(signature)
        if active == previous_actual:
            continue
        added = active - previous_actual
        removed = previous_actual - active
        previous_actual = active
        if not signature or signature in seen:
            continue
        seen.add(signature)
        events.append(
            {
                "year": year,
                "signature": signature,
                "active_feature_count": len(signature),
                "local_added_count": len(added),
                "local_removed_count": len(removed),
                "local_change_count": len(added) + len(removed),
            }
        )
    return events


def _signature_hash(signature: tuple[str, ...]) -> str:
    return hashlib.sha256("\n".join(signature).encode("utf-8")).hexdigest()


def select_representative_periods(
    rows: list[dict[str, Any]],
    *,
    target_count: int = DEFAULT_PERIOD_COUNT,
    max_year: int | None = None,
) -> list[dict[str, Any]]:
    """Select the largest active-set change in each chronological event segment."""
    if not MIN_PERIOD_COUNT <= target_count <= MAX_PERIOD_COUNT:
        raise ValueError(
            f"target_count must be between {MIN_PERIOD_COUNT} and {MAX_PERIOD_COUNT}"
        )
    events = unique_snapshot_events(rows, max_year=max_year)
    if not events:
        return []

    selected_count = min(target_count, len(events))
    selected: list[dict[str, Any]] = []
    for segment_index in range(selected_count):
        start = segment_index * len(events) // selected_count
        end = (segment_index + 1) * len(events) // selected_count
        bucket = events[start:end]
        chosen = max(
            bucket,
            key=lambda event: (
                event["local_change_count"],
                event["active_feature_count"],
                -event["year"],
            ),
        )
        selected.append({**chosen, "segment_index": segment_index})

    selected.sort(key=lambda event: event["year"])
    previous_selected: set[str] = set()
    periods = []
    for event in selected:
        active = set(event["signature"])
        added = active - previous_selected
        removed = previous_selected - active
        periods.append(
            {
                "year": event["year"],
                "reason": "largest_active_feature_set_change_in_chronological_segment",
                "active_feature_count": len(active),
                "added_since_previous": len(added),
                "removed_since_previous": len(removed),
                "change_since_previous": len(added) + len(removed),
                "local_change_at_candidate": event["local_change_count"],
                "snapshot_signature_sha256": _signature_hash(event["signature"]),
                "segment_index": event["segment_index"],
            }
        )
        previous_selected = active
    return periods
