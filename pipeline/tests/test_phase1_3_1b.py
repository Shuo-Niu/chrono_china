from __future__ import annotations

from chronochina.config import PROJECT_ROOT, QA_DIR
from chronochina.io import read_json
from chronochina.qa.freeze_phase1_3_1b import verify


def test_phase1_3_1b_frozen_inputs_are_unchanged() -> None:
    result = verify()
    changed_paths = {
        item["path"]
        for group in result["groups"]
        for item in group["files"]
        if not item["unchanged"]
    }
    assert changed_paths == {"web/src/map/referenceLayers.ts"}


def test_phase1_3_1b_audits_preserve_source_semantics() -> None:
    type_audit = read_json(QA_DIR / "phase1_3_1b_feature_type_audit.json")
    name_audit = read_json(QA_DIR / "phase1_3_1b_name_display_audit.json")
    assert len(type_audit["rows"]) == 16
    assert name_audit["inconsistency_count"] == 0
    findings = {row["tgaz_id"]: row for row in name_audit["special_investigations"]}
    assert findings["hvd_113648"]["type"] == "政权"
    assert findings["hvd_116125"]["name"] == "右扶风"
    assert findings["hvd_116126"]["name"] == "右扶风郡"
    assert findings["hvd_116218"]["name"] == "左冯翊"


def test_phase1_3_1b_strategy_and_display_parity() -> None:
    parity = read_json(QA_DIR / "phase1_3_1b_display_parity.json")
    assert parity["case_count"] == 20
    assert parity["strategy_c_all_unchanged"] is True
    assert parity["all_labels_are_displayed_points"] is True


def test_phase1_3_1b_visual_evidence_is_complete() -> None:
    root = PROJECT_ROOT / "artifacts/phase1_3_1b"
    assert len(list((root / "user_mode").glob("*.png"))) == 5
    assert len(list((root / "zoom_labels").glob("*.png"))) == 6
    metrics = read_json(QA_DIR / "phase1_3_1b_zoom_label_metrics.json")
    for offset in (0, 3):
        assert [row["labelCount"] for row in metrics[offset : offset + 3]] == [6, 12, 24]
        assert len({row["pointCount"] for row in metrics[offset : offset + 3]}) == 1
    overlap = read_json(QA_DIR / "phase1_3_1b_panel_overlap_qa.json")
    assert overlap["result"] == "PASS"
    assert overlap["panelZIndex"] > overlap["markerZIndex"]
    assert (PROJECT_ROOT / "docs/design/viewport_driven_exploration.md").is_file()
