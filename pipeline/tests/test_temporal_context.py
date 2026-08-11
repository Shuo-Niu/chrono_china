from __future__ import annotations

import pytest

from chronochina.config import PROCESSED_DIR
from chronochina.io import read_json
from chronochina.temporal_context import (
    REVIEWED_CONTEXTS,
    SOURCES,
    deterministic_shortcut_target,
    format_year_zh,
    timeline_positions,
)


def test_chinese_year_formatter_and_no_year_zero() -> None:
    assert format_year_zh(-201) == "公元前 201 年"
    assert format_year_zh(14) == "公元 14 年"
    assert format_year_zh(1911) == "公元 1911 年"
    with pytest.raises(ValueError, match="year zero"):
        format_year_zh(0)


def test_review_table_covers_exactly_twenty_snapshots_with_provenance() -> None:
    assert len(REVIEWED_CONTEXTS) == 20
    assert all(context.broad_era_label for context in REVIEWED_CONTEXTS.values())
    assert all(context.source_ids for context in REVIEWED_CONTEXTS.values())
    assert 0 not in {year for _, year in REVIEWED_CONTEXTS}


def test_timeline_positions_preserve_order_and_minimum_visual_spacing() -> None:
    layout = timeline_positions([14, 556, 596, 1911])
    assert [item["year"] for item in layout] == [14, 556, 596, 1911]
    assert [item["linear_normalized_position"] for item in layout] == sorted(
        item["linear_normalized_position"] for item in layout
    )
    display = [item["display_normalized_position"] for item in layout]
    assert display[0] == 0
    assert display[-1] == 1
    assert all(right - left >= 0.099999 for left, right in zip(display, display[1:]))
    assert layout[2]["position_adjusted"] is True


def test_timeline_rejects_unsorted_duplicate_and_zero_years() -> None:
    for years in ([14, 0, 1911], [220, 14], [14, 14]):
        with pytest.raises(ValueError):
            timeline_positions(list(years))


def test_shortcut_mapping_is_deterministic_and_never_creates_snapshot() -> None:
    snapshots = [
        {"snapshot_year": -201, "shortcut_label": "汉"},
        {"snapshot_year": 14, "shortcut_label": "汉"},
        {"snapshot_year": 190, "shortcut_label": "汉"},
        {"snapshot_year": 1911, "shortcut_label": "清"},
    ]
    assert deterministic_shortcut_target(snapshots, "汉", 100) == 14
    assert deterministic_shortcut_target(snapshots, "汉", 102) == 14
    assert deterministic_shortcut_target(snapshots, "清", 500) == 1911
    assert deterministic_shortcut_target(snapshots, "唐", 500) is None
    assert deterministic_shortcut_target(snapshots, "汉", 100) in {
        item["snapshot_year"] for item in snapshots
    }


def test_generated_manifests_match_all_frozen_anchor_snapshots() -> None:
    expected: set[tuple[str, int]] = set()
    actual: set[tuple[str, int]] = set()
    for anchor_path in sorted((PROCESSED_DIR / "anchors").glob("*/manifest.json")):
        anchor = read_json(anchor_path)
        expected.update((anchor["anchor_id"], year) for year in anchor["available_periods"])
        context = read_json(
            PROCESSED_DIR / "temporal_context" / f"{anchor['anchor_id']}.json"
        )
        snapshots = context["snapshots"]
        assert [item["snapshot_year"] for item in snapshots] == anchor["available_periods"]
        assert all(item["display_year"] for item in snapshots)
        assert all(item["broad_era_label"] for item in snapshots)
        assert all(item["whether_context_is_safe_for_user_display"] for item in snapshots)
        assert all(set(item["source_ids"]) <= SOURCES.keys() for item in snapshots)
        assert all(item["timeline"]["year"] == item["snapshot_year"] for item in snapshots)
        actual.update((item["anchor_id"], item["snapshot_year"]) for item in snapshots)
    assert actual == expected
    assert len(actual) == 20
