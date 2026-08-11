from chronochina.config import PROJECT_ROOT
from chronochina.io import read_json


def test_phase1_3_1_freeze_covers_required_input_groups() -> None:
    freeze = read_json(PROJECT_ROOT / "data" / "qa" / "phase1_3_1_input_freeze.json")
    assert freeze["phase"] == "1.3.1"
    assert freeze["result"] in {"BASELINE_CAPTURED", "UNCHANGED"}
    groups = {group["name"]: group for group in freeze["groups"]}
    assert set(groups) == {
        "five_anchor_manifest",
        "representative_snapshots",
        "processed_historical_slices",
        "strategy_c_outputs",
        "r2_configuration",
        "temporal_context_manifests",
        "temporal_context_source_qa",
        "marker_alignment_qa",
        "geographic_plausibility_qa",
        "user_mode_screenshot_baseline",
    }
    for group in groups.values():
        assert group["files"]
        for item in group["files"]:
            assert item["path"]
            assert item.get("size_bytes", item.get("before_size_bytes")) >= 0
            assert len(item.get("sha256", item.get("before_sha256"))) == 64


def test_phase1_3_1_external_test_package_is_complete_and_unfilled() -> None:
    usability_dir = PROJECT_ROOT / "docs" / "usability"
    required = [
        "phase1_3_1_test_script.md",
        "phase1_3_1_test_script.txt",
        "phase1_3_1_observation_template.md",
        "phase1_3_1_observation_template.txt",
        "phase1_3_1_acceptance_criteria.md",
        "phase1_3_1_runbook.md",
        "phase1_3_1_results_template.md",
    ]
    assert all((usability_dir / name).is_file() for name in required)

    script = (usability_dir / required[0]).read_text(encoding="utf-8")
    for task in range(1, 7):
        assert f"任务 {task}" in script
    for question in range(1, 11):
        assert f"{question}." in script
    assert "不要透露目标年份是 1368" in script
    assert "青岛以前叫即墨县" in script

    observation = (usability_dir / required[2]).read_text(encoding="utf-8")
    for field in (
        "participant_id",
        "prior_history_interest",
        "prior_map_or_GIS_familiarity",
        "Misclicks",
        "Spatial Neighborhood comprehension",
        "timeline_comprehension",
        "broad_era_comprehension",
        "modern_anchor_comprehension",
        "exact user quotes",
    ):
        assert field in observation

    criteria = (usability_dir / required[4]).read_text(encoding="utf-8")
    assert "至少 4/5" in criteria
    assert "3/3" in criteria
    assert "2` 名或更多" in criteria
    assert "P0 product-semantics issue" in criteria

    results = (usability_dir / required[6]).read_text(encoding="utf-8")
    for section in "ABCDEFGHIJKLM":
        assert f"## {section}." in results
    assert "这是空白模板" in results
