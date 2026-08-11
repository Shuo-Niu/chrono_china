from __future__ import annotations

from copy import deepcopy

from chronochina.phase1_1 import (
    STRATEGY_NEAREST,
    STRATEGY_TYPE_DIVERSE,
    STRATEGY_TYPE_SPATIAL,
    DisplayConfig,
    build_strategy_case,
    select_display_labels,
    select_display_points,
    spatial_coverage_grid_cells,
)


ANCHOR = {
    "anchor_id": "test",
    "display_name": "测试",
    "modern_location": {"lon": 0.0, "lat": 0.0},
    "default_radius_km": 75.0,
}


def make_row(
    tgaz_id: str,
    distance_km: float,
    feature_type: str,
    *,
    lon: float = 0.0,
    lat: float = 0.0,
) -> dict[str, object]:
    return {
        "tgaz_id": tgaz_id,
        "distance_km": distance_km,
        "feature_type": feature_type,
        "name_zh_hans": tgaz_id,
        "lon": lon,
        "lat": lat,
        "relation_to_anchor": "spatial_nearby",
        "lineage_claim": None,
    }


def test_nearest_n_is_stable_and_handles_limit_above_available() -> None:
    rows = [
        make_row("b", 2.0, "县"),
        make_row("c", 1.0, "州"),
        make_row("a", 1.0, "府"),
    ]
    config = DisplayConfig(nearest_point_limit=10)

    selected = select_display_points(rows, STRATEGY_NEAREST, config=config)

    assert [row["tgaz_id"] for row in selected] == ["a", "c", "b"]
    assert len(selected) == len(rows)


def test_empty_snapshot_does_not_crash() -> None:
    assert select_display_points([], STRATEGY_NEAREST) == []
    assert select_display_points([], STRATEGY_TYPE_DIVERSE) == []
    assert select_display_points([], STRATEGY_TYPE_SPATIAL) == []
    assert select_display_labels([], ANCHOR, 75.0)["labels"] == []


def test_type_diversity_prevents_dominant_type_from_using_every_slot() -> None:
    rows = [make_row(f"county-{index}", index + 1, "县") for index in range(8)]
    rows.extend(
        [
            make_row("prefecture", 2.5, "府"),
            make_row("department", 3.5, "州"),
        ]
    )
    config = DisplayConfig(diverse_point_limit=3)

    selected = select_display_points(rows, STRATEGY_TYPE_DIVERSE, config=config)

    assert {row["feature_type"] for row in selected} == {"县", "府", "州"}


def test_spatial_strategy_increases_grid_coverage_when_alternatives_exist() -> None:
    rows = [
        make_row("near-1", 1.0, "县", lon=0.001, lat=0.001),
        make_row("near-2", 2.0, "县", lon=0.002, lat=0.002),
        make_row("near-3", 3.0, "县", lon=0.003, lat=0.003),
        make_row("near-4", 4.0, "县", lon=0.004, lat=0.004),
        make_row("east", 55.0, "县", lon=0.5, lat=0.0),
        make_row("west", 56.0, "县", lon=-0.5, lat=0.0),
        make_row("north", 57.0, "县", lon=0.0, lat=0.5),
    ]
    config = DisplayConfig(diverse_point_limit=4)
    type_only = select_display_points(rows, STRATEGY_TYPE_DIVERSE, config=config)
    spatial = select_display_points(rows, STRATEGY_TYPE_SPATIAL, config=config)

    assert spatial_coverage_grid_cells(spatial, ANCHOR, 75.0) > spatial_coverage_grid_cells(
        type_only, ANCHOR, 75.0
    )


def test_all_strategies_are_deterministic_and_do_not_mutate_identity() -> None:
    rows = [
        make_row("one", 1.0, "县", lon=0.01),
        make_row("two", 2.0, "府", lon=-0.02),
        make_row("three", 3.0, "县", lat=0.03),
        make_row("four", 4.0, "州", lat=-0.04),
    ]
    original = deepcopy(rows)
    active_ids = {row["tgaz_id"] for row in rows}

    for strategy in (STRATEGY_NEAREST, STRATEGY_TYPE_DIVERSE, STRATEGY_TYPE_SPATIAL):
        first = select_display_points(rows, strategy)
        second = select_display_points(rows, strategy)
        assert [row["tgaz_id"] for row in first] == [
            row["tgaz_id"] for row in second
        ]
        assert {row["tgaz_id"] for row in first} <= active_ids
        assert all(row["lineage_claim"] is None for row in first)

    assert rows == original


def test_points_and_labels_are_separate_subsets() -> None:
    rows = [
        make_row(
            f"row-{index:02d}",
            float(index + 1),
            "县" if index % 2 else "州",
            lon=(index - 10) * 0.03,
            lat=((index % 5) - 2) * 0.05,
        )
        for index in range(20)
    ]
    config = DisplayConfig(diverse_point_limit=15, label_limit=3)
    points = select_display_points(rows, STRATEGY_TYPE_DIVERSE, config=config)
    labels = select_display_labels(points, ANCHOR, 75.0, config=config)["labels"]

    assert len(points) == 15
    assert len(labels) <= 3
    assert len(points) > len(labels)
    assert {row["tgaz_id"] for row in labels} <= {
        row["tgaz_id"] for row in points
    }


def test_strategy_case_exposes_required_metrics_without_winner_score() -> None:
    rows = [
        make_row("one", 1.0, "县", lon=0.01),
        make_row("two", 2.0, "府", lon=-0.02),
    ]

    case = build_strategy_case(rows, ANCHOR, 1911, STRATEGY_NEAREST)

    assert case["active_feature_count"] == 2
    assert case["displayed_point_count"] == 2
    assert case["displayed_label_count"] <= 2
    assert case["collision_metric_kind"] == "estimated"
    assert case["spatial_coverage_metric_name"] == "occupied_anchor_grid_cells_4x4"
    assert "quality_score" not in case
