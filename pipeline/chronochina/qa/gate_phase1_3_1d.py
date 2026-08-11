from __future__ import annotations

from xml.etree import ElementTree

from chronochina.config import PROJECT_ROOT, QA_DIR
from chronochina.io import read_json, utc_now, write_json


def check(name: str, passed: bool, evidence: object) -> dict[str, object]:
    return {"name": name, "result": "PASS" if passed else "FAIL", "evidence": evidence}


def main() -> None:
    freeze = read_json(QA_DIR / "phase1_3_1d_input_freeze.json")
    semantic = read_json(QA_DIR / "phase1_3_1d_semantic_zoom_consistency.json")
    pans = read_json(QA_DIR / "phase1_3_1d_pan_consistency.json")
    colocation = read_json(QA_DIR / "phase1_3_1d_colocation_exact_year.json")
    nationwide = read_json(QA_DIR / "phase1_3_1d_nationwide_low_zoom.json")
    performance = read_json(QA_DIR / "phase1_3_1d_performance.json")
    browser = read_json(PROJECT_ROOT / "artifacts" / "phase1_3_1d" / "browser_evidence.json")
    playwright = read_json(PROJECT_ROOT / "artifacts" / "playwright-results.json")
    vitest_root = ElementTree.parse(PROJECT_ROOT / "artifacts" / "vitest-results.xml").getroot()
    screenshots = sorted((PROJECT_ROOT / "artifacts" / "phase1_3_1d").glob("*.png"))
    immutable_groups = [group for group in freeze["groups"] if group["immutable"]]
    colocation_valid = all(
        snapshot["all_members_valid_at_exact_year"]
        for snapshot in colocation["snapshots"]
    )
    checks = [
        check(
            "frozen historical inputs",
            freeze["result"] == "UNCHANGED_IMMUTABLES" and all(group["unchanged"] for group in immutable_groups),
            {"freeze_result": freeze["result"], "immutable_group_count": len(immutable_groups)},
        ),
        check(
            "semantic zoom consistency",
            semantic["result"] == "PASS" and semantic["anchor_case_count"] >= 5
            and semantic["non_anchor_case_count"] >= 5
            and all(case["hidden_by_center_ranking"] == 0 for case in semantic["cases"]),
            {"case_count": semantic["case_count"], "hidden_by_center_ranking": 0},
        ),
        check(
            "pan and label consistency",
            pans["result"] == "PASS" and pans["case_count"] >= 10
            and pans["eligibility_change_count"] == 0
            and pans["maximum_label_placement_churn_rate"] == 0,
            {
                "case_count": pans["case_count"],
                "eligibility_change_count": pans["eligibility_change_count"],
                "maximum_label_placement_churn_rate": pans["maximum_label_placement_churn_rate"],
            },
        ),
        check(
            "nationwide low zoom",
            nationwide["result"] == "PASS"
            and nationwide["active_high_level_feature_count"] == nationwide["displayed_high_level_feature_count"]
            and nationwide["active_high_level_feature_count"] > 1
            and nationwide["hidden_by_center_ranking"] == 0,
            nationwide,
        ),
        check(
            "co-location exact year",
            colocation["result"] == "PASS" and colocation_valid
            and colocation["snapshots"][0]["active_member_ids"] != colocation["snapshots"][1]["active_member_ids"],
            {"coordinate": colocation["coordinate"], "snapshots": colocation["snapshots"]},
        ),
        check(
            "performance",
            performance["result"] == "PASS"
            and performance["maximum_viewport_query_latency_ms"] < 100,
            performance,
        ),
        check(
            "browser evidence and screenshots",
            browser["result"] == "PASS" and browser["screenshot_count"] >= 10
            and len(screenshots) >= 10
            and browser["pan_label_placement_churn_count"] == 0
            and len(browser["five_anchor_regression"]) == 5
            and all(item["first_marker_alignment_error_px"] <= 1 for item in browser["five_anchor_regression"]),
            {"screenshot_count": len(screenshots), "browser_evidence": browser},
        ),
        check(
            "Vitest",
            int(vitest_root.attrib.get("failures", "0")) == 0
            and int(vitest_root.attrib.get("errors", "0")) == 0,
            dict(vitest_root.attrib),
        ),
        check(
            "Playwright",
            playwright["stats"]["unexpected"] == 0 and playwright["stats"]["expected"] >= 1,
            playwright["stats"],
        ),
    ]
    result = "PASS" if all(item["result"] == "PASS" for item in checks) else "FAIL"
    write_json(QA_DIR / "phase1_3_1d_gate.json", {
        "phase": "1.3.1d",
        "generated_at_utc": utc_now(),
        "result": result,
        "checks": checks,
    })
    print(result)


if __name__ == "__main__":
    main()
