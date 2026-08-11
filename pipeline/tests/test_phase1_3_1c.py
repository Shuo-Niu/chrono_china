from __future__ import annotations

from chronochina.config import QA_DIR
from chronochina.io import read_json
from chronochina.qa.freeze_phase1_3_1c import verify
from chronochina.qa.phase1_3_1c import generate_track_a_gate, generate_track_b_gate


def test_phase1_3_1c_immutable_inputs_are_unchanged() -> None:
    assert verify()["result"] == "UNCHANGED_IMMUTABLES"


def test_phase1_3_1c_freeze_covers_required_groups() -> None:
    freeze = read_json(QA_DIR / "phase1_3_1c_input_freeze.json")
    groups = {group["name"]: group for group in freeze["groups"]}
    assert freeze["phase"] == "1.3.1c"
    assert {
        "normalized_historical_index",
        "five_anchor_processed_slices",
        "strategy_c_artifacts",
        "strategy_c_point_ranking_code",
        "display_family_registry_baseline",
        "legend_configuration_baseline",
        "temporal_context_manifests",
        "marker_alignment_qa",
        "geographic_plausibility_qa",
        "r2_reference_configuration",
        "prior_user_mode_screenshots",
        "detail_source_content",
        "name_display_policy_baseline",
    }.issubset(groups)
    assert all(group["files"] for group in groups.values())


def test_phase1_3_1c_track_a_gate_passes() -> None:
    gate = generate_track_a_gate()
    assert gate["result"] == "PASS"
    assert gate["semantic_zoom"]["case_count"] == 12
    assert gate["colocated_groups"]["required_ids_preserved"] is True
    assert gate["source_note_fidelity"]["longest_real_source_note"]["raw_length"] > 260


def test_phase1_3_1c_track_b_gate_passes() -> None:
    gate = generate_track_b_gate()
    assert gate["result"] == "PASS"
    assert gate["index"]["record_count"] == 71_393
    assert gate["parity"]["case_count"] >= 20
    assert gate["browser_queries"]["case_count"] >= 20
    assert gate["browser_queries"]["max_query_ms"] < 100
