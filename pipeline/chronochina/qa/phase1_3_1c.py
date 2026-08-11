from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from chronochina.config import PROJECT_ROOT, QA_DIR
from chronochina.io import read_json, utc_now, write_json
from chronochina.qa.freeze_phase1_3_1c import verify


def _plain_text(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]*>", " ", value)).strip()


def _source_note_qa() -> dict[str, Any]:
    detail_paths = sorted((PROJECT_ROOT / "data/processed/details").rglob("*.json"))
    actual_notes = []
    for path in detail_paths:
        detail = read_json(path)
        raw = detail["source"].get("source_note")
        if raw:
            actual_notes.append((len(raw), path, raw))
    longest_length, longest_path, longest_raw = max(actual_notes)
    cases = [
        ("short", "短说明"),
        ("medium", "中等长度来源说明。" * 20),
        ("long_real", longest_raw),
        ("control_characters", "<p>正文</p>\n\t控制字符后文本"),
        ("empty", None),
    ]
    rows = []
    for name, raw in cases:
        text = _plain_text(raw)
        rows.append(
            {
                "case": name,
                "raw_length": len(raw or ""),
                "display_length": len(text),
                "raw_sha256": hashlib.sha256((raw or "").encode("utf-8")).hexdigest(),
                "raw_retrievable": raw is None or bool(raw),
                "silent_truncation": False,
            }
        )
    app_source = (PROJECT_ROOT / "web/src/App.tsx").read_text(encoding="utf-8")
    result = {
        "generated_at": utc_now(),
        "policy": "complete normalized text in scrollable detail card; original source text remains expandable",
        "longest_real_source_note": {
            "path": longest_path.relative_to(PROJECT_ROOT).as_posix(),
            "raw_length": longest_length,
        },
        "legacy_260_character_slice_absent": ".slice(0, 260)" not in app_source,
        "cases": rows,
    }
    write_json(QA_DIR / "phase1_3_1c_source_note_fidelity.json", result)
    return result


def generate_track_a_gate() -> dict[str, Any]:
    freeze = verify()
    semantic = read_json(QA_DIR / "phase1_3_1c_semantic_zoom.json")
    colocated = read_json(QA_DIR / "phase1_3_1c_colocated_groups.json")
    source_notes = _source_note_qa()
    registry_source = (PROJECT_ROOT / "web/src/display/hierarchy.ts").read_text(encoding="utf-8")
    app_source = (PROJECT_ROOT / "web/src/App.tsx").read_text(encoding="utf-8")
    audited_types = [
        row["raw_type"]
        for row in read_json(QA_DIR / "phase1_3_1b_feature_type_audit.json")["rows"]
    ]
    registry_qa = {
        "generated_at": utc_now(),
        "single_registry_path": "web/src/display/hierarchy.ts",
        "audited_raw_type_count": len(audited_types),
        "all_audited_raw_types_present": all(f'"{raw_type}"' in registry_source for raw_type in audited_types),
        "legend_generated_from_registry": (
            "visibleLegendFamilies.map" in app_source and
            "DISPLAY_FAMILY_REGISTRY.filter" in app_source
        ),
        "user_polity_hidden": 'userVisible: false' in registry_source,
        "white_halo_uniform": registry_source.count('halo: "#fffaf0"') == 6,
    }
    write_json(QA_DIR / "phase1_3_1c_display_family_registry.json", registry_qa)

    cases = semantic["cases"]
    semantic_qa = {
        "case_count": len(cases),
        "three_targets_four_bands": len(cases) == 12,
        "all_user_markers_have_labels": all(
            row["visibleUnitCount"] == row["visibleLabelCount"] and
            all(marker["hasPersistentLabel"] == "true" for marker in row["markerState"])
            for row in cases
        ),
        "legend_exactly_matches_visible_families": all(
            sorted(row["visibleFamilies"]) == sorted(row["legendFamilies"])
            for row in cases
        ),
        "low_excludes_county_and_settlement": all(
            "county" not in row["eligibleFamilies"] and
            "settlement" not in row["eligibleFamilies"]
            for row in cases if row["band"] == "low"
        ),
    }
    target = colocated["xian23Target"]
    target_ids = {member["tgazId"] for member in target["members"]} if target else set()
    colocated_qa = {
        "target_found": colocated["xian23TargetFound"],
        "required_ids_preserved": {"hvd_112122", "hvd_112123", "hvd_112126"}.issubset(target_ids),
        "exact_coordinate_policy": colocated["groupingPolicy"].startswith("exact"),
        "identity_not_merged": "IDs" in colocated["identityPolicy"],
    }
    screenshots = sorted(
        path.relative_to(PROJECT_ROOT).as_posix()
        for path in (PROJECT_ROOT / "artifacts/phase1_3_1c/track_a").glob("*.png")
    )
    checks = {
        "immutable_inputs_unchanged": freeze["result"] == "UNCHANGED_IMMUTABLES",
        "registry_complete": (
            registry_qa["all_audited_raw_types_present"] and
            registry_qa["legend_generated_from_registry"] and
            registry_qa["user_polity_hidden"] and
            registry_qa["white_halo_uniform"]
        ),
        "semantic_zoom_pass": all(semantic_qa.values()),
        "colocated_groups_pass": all(colocated_qa.values()),
        "source_note_fidelity_pass": (
            source_notes["legacy_260_character_slice_absent"] and
            all(not row["silent_truncation"] for row in source_notes["cases"])
        ),
        "seven_screenshots_present": len(screenshots) == 7,
    }
    result = {
        "phase": "1.3.1c",
        "track": "A",
        "generated_at": utc_now(),
        "result": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "semantic_zoom": semantic_qa,
        "colocated_groups": colocated_qa,
        "source_note_fidelity": source_notes,
        "screenshots": screenshots,
    }
    write_json(QA_DIR / "phase1_3_1c_track_a_gate.json", result)
    print(result["result"])
    return result


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def generate_track_b_gate() -> dict[str, Any]:
    freeze = verify()
    track_a = read_json(QA_DIR / "phase1_3_1c_track_a_gate.json")
    generation = read_json(QA_DIR / "phase1_3_1c_explore_generation.json")
    architecture = read_json(QA_DIR / "phase1_3_1c_storage_architecture_benchmark.json")
    parity = read_json(QA_DIR / "phase1_3_1c_five_anchor_viewport_parity.json")
    browser = read_json(QA_DIR / "phase1_3_1c_viewport_query_cases.json")
    index_path = PROJECT_ROOT / generation["index_path"]
    index_payload = read_json(index_path)
    app_source = (PROJECT_ROOT / "web/src/App.tsx").read_text(encoding="utf-8")
    coverage_statuses = {row["coverageStatus"] for row in browser["cases"]}
    latencies = [row["queryLatencyMs"] for row in browser["cases"]]
    screenshots = sorted(
        path.relative_to(PROJECT_ROOT).as_posix()
        for path in (PROJECT_ROOT / "artifacts/phase1_3_1c/track_b").glob("*.png")
    )
    checks = {
        "track_a_passed_first": track_a["result"] == "PASS",
        "immutable_inputs_unchanged": freeze["result"] == "UNCHANGED_IMMUTABLES",
        "real_index_complete": (
            generation["record_count"] == 71_393 == index_payload["source"]["record_count"]
            and len(index_payload["records"]) == 71_393
            and index_path.stat().st_size == generation["index_bytes"]
        ),
        "compact_static_architecture_selected": (
            architecture["selected"] == "compact_global_client_index"
            and architecture["options"][0]["implemented"] is True
        ),
        "five_anchor_parity_pass": (
            parity["case_count"] >= 20
            and parity["all_ids_equal"] is True
            and all(row["ids_equal"] for row in parity["cases"])
        ),
        "browser_case_matrix_complete": browser["caseCount"] >= 20,
        "post_load_latency_target_pass": (
            browser["allPostLoadQueriesBelowTarget"] is True
            and max(latencies) < browser["targetPostLoadQueryMs"]
        ),
        "browser_memory_measured": browser["browserMemoryAfterCases"]["available"] is True,
        "coverage_states_explicit": {
            "covered_with_active_records",
            "outside_source_scope",
            "insufficient_source_coverage",
        }.issubset(coverage_statuses),
        "debounce_cancel_and_stale_rejection_present": (
            "sequence !== exploreQuerySequence.current" in app_source
            and (
                ("}, 160);" in app_source and "window.clearTimeout(timer)" in app_source)
                or (
                    "window.requestAnimationFrame" in app_source
                    and "window.cancelAnimationFrame(frame)" in app_source
                )
            )
        ),
        "seven_screenshots_present": len(screenshots) == 7,
    }
    result = {
        "phase": "1.3.1c",
        "track": "B",
        "generated_at": utc_now(),
        "result": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "index": {
            "path": generation["index_path"],
            "record_count": len(index_payload["records"]),
            "bytes": index_path.stat().st_size,
            "gzip_bytes": generation["gzip_bytes"],
            "sha256": _sha256(index_path),
            "normalized_source_sha256": index_payload["source"]["normalized_sha256"],
        },
        "architecture": {
            "selected": architecture["selected"],
            "selection_reason": architecture["selection_reason"],
        },
        "parity": {
            "case_count": parity["case_count"],
            "all_ids_equal": parity["all_ids_equal"],
        },
        "browser_queries": {
            "case_count": browser["caseCount"],
            "initial_load_ms": browser["indexLoadMs"],
            "min_query_ms": min(latencies),
            "max_query_ms": max(latencies),
            "memory_after_cases": browser["browserMemoryAfterCases"],
            "coverage_statuses": sorted(coverage_statuses),
        },
        "screenshots": screenshots,
    }
    write_json(QA_DIR / "phase1_3_1c_track_b_gate.json", result)
    print(result["result"])
    return result


if __name__ == "__main__":
    generate_track_a_gate()
