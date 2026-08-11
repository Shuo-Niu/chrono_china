from __future__ import annotations

from chronochina.config import PROJECT_ROOT, QA_DIR
from chronochina.io import read_json, utc_now, write_json


def main() -> None:
    freeze = read_json(QA_DIR / "phase1_3_1e_input_freeze.json")
    download = read_json(QA_DIR / "phase1_3_1e_download_completeness.json")
    reconciliation = read_json(QA_DIR / "phase1_3_1e_ingestion_reconciliation.json")
    density = read_json(QA_DIR / "phase1_3_1e_year_density.json")
    collisions = read_json(QA_DIR / "phase1_3_1e_overlay_collision.json")
    browser = read_json(PROJECT_ROOT / "artifacts/phase1_3_1e/browser_evidence.json")
    other_types = density["other_unclassified_source_type_counts"]
    checks = {
        "historical_source_unchanged": freeze["result"] == "UNCHANGED_IMMUTABLES",
        "official_download_complete": download["status"] == "PASS",
        "ingestion_reconciliation_complete": reconciliation["status"] == "PASS",
        "overlay_collision_matrix_passed": collisions["status"] == "PASS",
        "manual_layer_and_timeline_browser_flow_passed": browser["result"] == "PASS",
        "reign_title_feasibility_exists": (PROJECT_ROOT / "docs/design/reign_title_feasibility.md").exists(),
        "coverage_audit_exists": (PROJECT_ROOT / "docs/data/phase1_3_1e_coverage_audit.md").exists(),
        "literal_other_type_legend_fits_single_line": False,
    }
    result = {
        "phase": "1.3.1e",
        "generated_at": utc_now(),
        "status": "BLOCKED",
        "checks": checks,
        "blocking_issue": {
            "category": "legend_constraint_conflict",
            "actual_unclassified_raw_type_count": len(other_types),
            "actual_unclassified_record_count": sum(other_types.values()),
            "reason": (
                "The existing User Mode other family contains 81 distinct unreviewed raw types. "
                "Listing every raw type visibly on one line at the 900–1024 px supported widths is "
                "physically incompatible with the no-wrap/no-scroll/no-omission requirement."
            ),
            "safe_fallback_implemented": "single visible toggle labelled 其他未分类来源类型; no fabricated taxonomy",
        },
    }
    write_json(QA_DIR / "phase1_3_1e_gate.json", result)
    print(result["status"])


if __name__ == "__main__":
    main()
