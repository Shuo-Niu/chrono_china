from __future__ import annotations

import json
from pathlib import Path

from chronochina.phase1 import (
    EXPECTED_ANCHOR_IDS,
    build_phase1_plan,
    record_phase1_api_attempt,
    select_display_rows,
    write_phase1_outputs,
    write_v6_parity_outliers,
)


def _anchors() -> list[dict[str, object]]:
    return [
        {
            "anchor_id": anchor_id,
            "display_name": anchor_id.title(),
            "query": anchor_id,
            "modern_location": {"lon": 100.0 + index * 5, "lat": 30.0},
            "source": {
                "provider": "GeoNames",
                "record_id": str(index),
                "record_url": f"https://example.invalid/geonames/{index}",
                "retrieved_at": "2026-01-01T00:00:00Z",
            },
            "default_radius_km": 75.0,
        }
        for index, anchor_id in enumerate(EXPECTED_ANCHOR_IDS)
    ]


def _rows(anchors: list[dict[str, object]]) -> list[dict[str, object]]:
    intervals = [(-100, 0), (0, 50), (51, 100), (80, 150)]
    rows = []
    for anchor in anchors:
        location = anchor["modern_location"]
        for index, (valid_from, valid_to) in enumerate(intervals):
            tgaz_id = f"{anchor['anchor_id']}_{index}"
            rows.append(
                {
                    "tgaz_id": tgaz_id,
                    "source_url": f"https://example.invalid/csv/{tgaz_id}",
                    "name_zh_hans": tgaz_id,
                    "name_pinyin": tgaz_id,
                    "valid_from": valid_from,
                    "valid_to": valid_to,
                    "lon": location["lon"] + index * 0.01,
                    "lat": location["lat"] + index * 0.01,
                    "feature_type": "county",
                    "parent_name": "parent",
                }
            )
    return rows


def _detail(row: dict[str, object]) -> dict[str, object]:
    return {
        "tgaz_id": row["tgaz_id"],
        "canonical_uri": f"https://example.invalid/api/{row['tgaz_id']}",
        "names": {
            "simplified_chinese": row["name_zh_hans"],
            "traditional_chinese": row["name_zh_hans"],
            "pinyin": row["name_pinyin"],
            "all_spellings": [],
        },
        "feature_type": {
            "name": row["feature_type"],
            "alternate_name": None,
            "transcription": None,
            "english": "county",
        },
        "location": {"lon": row["lon"] + 0.001, "lat": row["lat"] + 0.001},
        "temporal": {
            "valid_from": row["valid_from"],
            "valid_to": row["valid_to"],
        },
        "relationships": {
            "part_of": [],
            "subordinate_units": [],
            "preceded_by": [],
        },
        "source": {
            "system": "TGAZ",
            "data_source": "CHGIS",
            "source_note": "test source note",
            "source_uri": "https://example.invalid/source",
            "license": "CC BY-NC 4.0",
        },
    }


def test_five_anchor_plan_uses_real_snapshot_changes() -> None:
    anchors = _anchors()
    plan = build_phase1_plan(_rows(anchors), anchors, max_year=150)

    assert [item["anchor"]["anchor_id"] for item in plan["anchors"]] == list(
        EXPECTED_ANCHOR_IDS
    )
    assert all(item["status"] == "PASS" for item in plan["anchors"])
    for anchor_plan in plan["anchors"]:
        periods = anchor_plan["periods"]
        assert 3 <= len(periods) <= 6
        assert len({period["snapshot_signature_sha256"] for period in periods}) == len(
            periods
        )
        assert all(period["active_feature_count"] > 0 for period in periods)


def test_display_filter_does_not_merge_colocated_identities() -> None:
    selected = select_display_rows(
        [
            {"tgaz_id": "a", "lon": 100.0, "lat": 30.0, "distance_km": 1.0},
            {"tgaz_id": "b", "lon": 100.0, "lat": 30.0, "distance_km": 2.0},
            {"tgaz_id": "c", "lon": 100.1, "lat": 30.1, "distance_km": 3.0},
        ],
        limit=3,
    )
    assert [row["tgaz_id"] for row in selected] == ["a", "c", "b"]
    assert len({row["tgaz_id"] for row in selected}) == 3


def test_outputs_are_reproducible_fresh_and_provenance_complete(tmp_path: Path) -> None:
    anchors = _anchors()
    rows = _rows(anchors)
    plan = build_phase1_plan(rows, anchors, max_year=150)
    details = {row["tgaz_id"]: _detail(row) for row in rows}
    processed = tmp_path / "processed"
    evidence = tmp_path / "evidence"
    source_index = {
        "dataset": "real-test-snapshot",
        "snapshot_date": "2026-01-01",
        "source_url": "https://example.invalid/index.csv",
        "sha256": "abc123",
        "retrieved_at": "2026-01-01T00:00:00Z",
    }

    first = write_phase1_outputs(
        plan,
        details,
        processed_dir=processed,
        evidence_dir=evidence,
        generated_at="2026-01-01T00:00:00Z",
        input_fingerprint="same-input",
        source_index=source_index,
    )
    second = write_phase1_outputs(
        plan,
        details,
        processed_dir=processed,
        evidence_dir=evidence,
        generated_at="2026-01-02T00:00:00Z",
        input_fingerprint="same-input",
        source_index=source_index,
    )

    assert first["semantic_sha256"] == second["semantic_sha256"]
    assert len(second["anchors"]) == 5
    for anchor in second["anchors"]:
        manifest_path = Path(anchor["manifest_path"])
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["history_source"] == source_index
        assert manifest["display_filter"]["identity_records_merged"] is False
        slice_path = processed / manifest["slices"][str(manifest["default_period"])]
        collection = json.loads(slice_path.read_text(encoding="utf-8"))
        assert collection["features"]
        assert collection["metadata"]["underlying_active_record_count"] >= len(
            collection["features"]
        )
        feature = collection["features"][0]
        assert feature["properties"]["source_record_id"]
        assert feature["properties"]["source_url"]
        assert feature["properties"]["license"] == "CC BY-NC 4.0"
        assert feature["properties"]["lineage_claim"] is None
        assert slice_path.stat().st_mtime_ns >= manifest_path.stat().st_mtime_ns - 2_000_000_000


def test_v6_outlier_artifact_keeps_identifiers_and_coordinates(tmp_path: Path) -> None:
    source = tmp_path / "g6.json"
    output = tmp_path / "outliers.json"
    source.write_text(
        json.dumps(
            {
                "parity": {
                    "sample_size": 1,
                    "comparisons": [
                        {
                            "chgis_id": "v6_1",
                            "hypothesized_tgaz_id": "tgaz_1",
                            "tgaz_record_found": True,
                            "matches": {
                                "coordinate_within_10m": False,
                                "valid_from": True,
                                "valid_to": True,
                                "name": True,
                                "feature_type": True,
                            },
                            "coordinate_distance_m": 1250.0,
                            "v6": {"name": "Place", "lon": 101.0, "lat": 31.0},
                            "tgaz": {"lon": 100.99, "lat": 30.99},
                        }
                    ],
                }
            }
        ),
        encoding="utf-8",
    )

    result = write_v6_parity_outliers(source, output)
    assert result["capability"] == "V6 parity = NOT_EQUIVALENT"
    assert result["outliers"][0]["v6_id"] == "v6_1"
    assert result["outliers"][0]["hypothesized_tgaz_id"] == "tgaz_1"
    assert result["outliers"][0]["distance_km"] == 1.25


def test_api_attempt_log_preserves_prior_real_failures(tmp_path: Path) -> None:
    path = tmp_path / "failures.json"
    path.write_text(
        json.dumps(
            {
                "generated_at": "2026-01-01T00:00:00Z",
                "failures": [{"tgaz_id": "hvd_bad", "error": "invalid JSON"}],
            }
        ),
        encoding="utf-8",
    )
    result = record_phase1_api_attempt(
        {
            "requested_ids": ["hvd_bad"],
            "success_count": 1,
            "failure_count": 0,
            "failures": [],
        },
        path,
    )
    assert result["latest_failure_count"] == 0
    assert result["attempts"][0]["failures"][0]["tgaz_id"] == "hvd_bad"
    assert result["attempts"][1]["failure_count"] == 0
