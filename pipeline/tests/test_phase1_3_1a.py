from __future__ import annotations

from chronochina.config import QA_DIR
from chronochina.io import read_json
from chronochina.qa.freeze_phase1_3_1a import verify


def test_phase1_3_1a_only_changes_later_authorized_display_and_explore_scope() -> None:
    result = verify()
    assert result["result"] == "CHANGED"
    freeze = read_json(QA_DIR / "phase1_3_1a_input_freeze.json")
    assert freeze["phase"] == "1.3.1a"
    assert freeze["result"] == "CHANGED"
    groups = {group["name"]: group for group in freeze["groups"]}
    assert {
        "representative_snapshots",
        "processed_historical_slices",
        "strategy_c_artifacts",
        "temporal_context_manifests",
        "marker_alignment_qa",
        "geographic_plausibility_qa",
        "representative_visual_baseline",
        "r0_r1_r3_definitions",
        "user_mode_temporal_ui",
        "historical_marker_rendering",
        "historical_marker_css",
    } <= groups.keys()
    changed_paths = {
        item["path"]
        for group in groups.values()
        for item in group["files"]
        if not item["unchanged"]
    }
    assert changed_paths == {
        "web/src/display/ranking.ts",
        "web/src/map/referenceLayers.ts#r0-r1-r3-definitions",
        "web/src/App.tsx#historical-marker-rendering",
        "web/src/App.tsx#user-mode-temporal-ui",
        "web/src/styles.css#historical-marker-css",
    }
