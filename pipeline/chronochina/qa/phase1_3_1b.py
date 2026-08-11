from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from chronochina.config import PROJECT_ROOT, QA_DIR
from chronochina.io import read_json, utc_now, write_json


OBSERVATIONS = QA_DIR / "phase1_3_1b_browser_observations.json"
RAW_INDEX = PROJECT_ROOT / "data/raw/tgaz_index/tgaz_chgis_2016-07-06.csv"
SLICE_ROOT = PROJECT_ROOT / "data/processed/phase1_1/anchors"
PARSED_DETAIL_ROOT = PROJECT_ROOT / "data/intermediate/tgaz_detail"

TYPE_FAMILIES = {
    "政权": "polity",
    "国": "polity",
    "省": "high_admin",
    "王畿": "high_admin",
    "郡": "regional_admin",
    "府": "regional_admin",
    "州": "regional_admin",
    "直隶州": "regional_admin",
    "路": "regional_admin",
    "侯国": "regional_admin",
    "厅": "regional_admin",
    "军": "regional_admin",
    "防镇": "regional_admin",
    "县": "county",
    "村镇": "settlement",
    "亭": "settlement",
}

FAMILY_POLICIES = {
    "polity": {
        "point_style": "16px diamond",
        "label_priority": 5,
        "label_min_zoom": 0,
        "label_max_zoom": None,
        "user_mode_visibility": "hidden in 75 km local view",
        "developer_mode_visibility": "visible",
    },
    "high_admin": {
        "point_style": "15px square, emphasized stroke",
        "label_priority": 0,
        "label_min_zoom": 0,
        "label_max_zoom": None,
        "user_mode_visibility": "visible when selected by Strategy C",
        "developer_mode_visibility": "visible",
    },
    "regional_admin": {
        "point_style": "13px circle, 3px light stroke",
        "label_priority": 1,
        "label_min_zoom": 0,
        "label_max_zoom": None,
        "user_mode_visibility": "visible when selected by Strategy C",
        "developer_mode_visibility": "visible",
    },
    "county": {
        "point_style": "11px circle",
        "label_priority": 2,
        "label_min_zoom": 0,
        "label_max_zoom": None,
        "user_mode_visibility": "visible when selected by Strategy C",
        "developer_mode_visibility": "visible",
    },
    "settlement": {
        "point_style": "8px circle, reduced opacity",
        "label_priority": 3,
        "label_min_zoom": 0,
        "label_max_zoom": None,
        "user_mode_visibility": "visible when selected by Strategy C",
        "developer_mode_visibility": "visible",
    },
    "other": {
        "point_style": "11px circle",
        "label_priority": 4,
        "label_min_zoom": 0,
        "label_max_zoom": None,
        "user_mode_visibility": "visible when selected by Strategy C",
        "developer_mode_visibility": "visible",
    },
}


def _raw_rows() -> dict[str, dict[str, str]]:
    with RAW_INDEX.open(encoding="utf-8-sig", newline="") as stream:
        return {row["TGAZ_ID"]: row for row in csv.DictReader(stream)}


def _slices() -> dict[tuple[str, int], dict[str, Any]]:
    result = {}
    for path in sorted(SLICE_ROOT.glob("*/slices/*.geojson")):
        result[(path.parent.parent.name, int(path.stem))] = read_json(path)
    return result


def _family(raw_type: str) -> str:
    return TYPE_FAMILIES.get(raw_type, "other")


def _write_markdown(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def generate() -> dict[str, Any]:
    observations = read_json(OBSERVATIONS)
    slices = _slices()
    raw = _raw_rows()
    generated_at = utc_now()

    type_rows: dict[str, dict[str, Any]] = {}
    family_counts: Counter[str] = Counter()
    for (anchor, year), collection in slices.items():
        for feature in collection["features"]:
            raw_type = feature["properties"]["feature_type"]
            family = _family(raw_type)
            family_counts[family] += 1
            row = type_rows.setdefault(
                raw_type,
                {
                    "raw_type": raw_type,
                    "count": 0,
                    "examples": [],
                    "anchors": set(),
                    "years": set(),
                    "source_fields": "TYPE_SIM / TYPE_ENG from TGAZ CHGIS CSV",
                    "display_family": family,
                    "user_mode_behavior": "hidden" if family == "polity" else "visible when selected by Strategy C",
                    "developer_mode_behavior": "visible when selected by active strategy",
                },
            )
            row["count"] += 1
            row["anchors"].add(anchor)
            row["years"].add(year)
            if len(row["examples"]) < 5:
                row["examples"].append(
                    {"tgaz_id": feature["id"], "name": feature["properties"]["name"]}
                )
    for row in type_rows.values():
        row["anchors"] = sorted(row["anchors"])
        row["years"] = sorted(row["years"])
    type_audit = {
        "generated_at": generated_at,
        "snapshot_count": len(slices),
        "source": str(RAW_INDEX.relative_to(PROJECT_ROOT)).replace("\\", "/"),
        "rows": sorted(type_rows.values(), key=lambda item: (-item["count"], item["raw_type"])),
    }
    write_json(QA_DIR / "phase1_3_1b_feature_type_audit.json", type_audit)
    _write_markdown(
        QA_DIR / "phase1_3_1b_feature_type_audit.md",
        [
            "# Phase 1.3.1b raw feature-type audit",
            "",
            "All raw types are preserved. `display_family` is a presentation-only classification.",
            "",
            "| Raw type | Count | Family | User Mode | Anchors | Years |",
            "| --- | ---: | --- | --- | --- | --- |",
            *[
                f"| {row['raw_type']} | {row['count']} | {row['display_family']} | "
                f"{row['user_mode_behavior']} | {', '.join(row['anchors'])} | "
                f"{', '.join(map(str, row['years']))} |"
                for row in type_audit["rows"]
            ],
        ],
    )

    name_occurrences = []
    parity_cases = []
    comparison = read_json(QA_DIR / "phase1_1_display_strategy_comparison.json")
    expected_strategy = {
        (case["anchor"], case["year"]): case["displayed_point_ids"]
        for case in comparison["cases"]
        if case["strategy"] == "type_diverse_spatial"
    }
    for observation in observations:
        key = (observation["anchor"], observation["year"])
        collection = slices[key]
        by_id = {feature["id"]: feature for feature in collection["features"]}
        for tgaz_id in observation["displayedLabelIds"]:
            feature = by_id[tgaz_id]
            source = raw[tgaz_id]
            parsed_path = PARSED_DETAIL_ROOT / f"{tgaz_id}.json"
            parsed = read_json(parsed_path) if parsed_path.exists() else None
            displayed = feature["properties"]["name"]
            name_sim = source["NAME_SIM"]
            raw_type = source["TYPE_SIM"]
            expected_suffix = raw_type if raw_type and not name_sim.endswith(raw_type) else ""
            name_occurrences.append(
                {
                    "anchor": key[0],
                    "year": key[1],
                    "tgaz_id": tgaz_id,
                    "displayed_name": displayed,
                    "NAME_SIM": name_sim,
                    "NAME_ENG": source["NAME_ENG"],
                    "TYPE_SIM": raw_type,
                    "TYPE_ENG": source["TYPE_ENG"],
                    "source_note": (
                        parsed["source"].get("source_note")
                        if parsed
                        else "canonical detail not cached; TGAZ CHGIS CSV frozen snapshot"
                    ),
                    "suffix_present_in_source_name": bool(raw_type and name_sim.endswith(raw_type)),
                    "possible_missing_suffix": expected_suffix or None,
                    "possible_inconsistency_category": (
                        "source_name_does_not_end_with_raw_type"
                        if expected_suffix
                        else "none"
                    ),
                    "current_display_rule": "verbatim processed name derived from NAME_SIM",
                    "inconsistency": None if displayed == name_sim else "displayed_name != NAME_SIM",
                }
            )
        active_ids = [feature["id"] for feature in collection["features"]]
        expected = expected_strategy[key]
        parity_cases.append(
            {
                "anchor": key[0],
                "year": key[1],
                "active_feature_ids": active_ids,
                "strategy_c_ranked_ids": observation["strategyRankedPointIds"],
                "frozen_strategy_c_ranked_ids": expected,
                "strategy_c_ids_unchanged": observation["strategyRankedPointIds"] == expected,
                "displayed_point_ids": observation["displayedPointIds"],
                "displayed_label_ids": observation["displayedLabelIds"],
                "labels_are_displayed_points": set(observation["displayedLabelIds"]).issubset(
                    observation["displayedPointIds"]
                ),
            }
        )

    special_ids = ["hvd_113648", "hvd_116125", "hvd_116126", "hvd_116218"]
    investigations = []
    for tgaz_id in special_ids:
        source = raw[tgaz_id]
        detail_path = PARSED_DETAIL_ROOT / f"{tgaz_id}.json"
        detail = read_json(detail_path) if detail_path.exists() else None
        investigations.append(
            {
                "tgaz_id": tgaz_id,
                "name": source["NAME_SIM"],
                "name_eng": source["NAME_ENG"],
                "type": source["TYPE_SIM"],
                "type_eng": source["TYPE_ENG"],
                "valid_from": int(source["BEG"]),
                "valid_to": int(source["END"]),
                "coordinate": [float(source["X"]), float(source["Y"])],
                "parent_csv": None if source["PARTOF_SIM"] == "\\N" else source["PARTOF_SIM"],
                "canonical_detail_available": detail is not None,
                "canonical_name": detail["names"]["simplified_chinese"] if detail else None,
                "canonical_type": detail["feature_type"]["name"] if detail else None,
                "canonical_parent_units": detail["relationships"]["part_of"] if detail else None,
                "canonical_source_note": detail["source"].get("source_note") if detail else None,
                "canonical_uri": detail["canonical_uri"] if detail else None,
                "semantic_finding": (
                    "canonical polity/regime point; hidden only in local User Mode"
                    if tgaz_id == "hvd_113648"
                    else "distinct canonical TGAZ record; source name retained verbatim"
                ),
                "display_reason": (
                    "available in Developer Mode for provenance QA"
                    if tgaz_id == "hvd_113648"
                    else "no suffix normalization without source evidence"
                ),
            }
        )
    name_audit = {
        "generated_at": generated_at,
        "scope": "all persistent User Mode labels at baseline zoom across 20 snapshots",
        "occurrence_count": len(name_occurrences),
        "unique_tgaz_id_count": len({row["tgaz_id"] for row in name_occurrences}),
        "inconsistency_count": sum(row["inconsistency"] is not None for row in name_occurrences),
        "rows": name_occurrences,
        "special_investigations": investigations,
    }
    write_json(QA_DIR / "phase1_3_1b_name_display_audit.json", name_audit)
    _write_markdown(
        QA_DIR / "phase1_3_1b_name_display_audit.md",
        [
            "# Phase 1.3.1b User Mode name audit",
            "",
            f"Audited {len(name_occurrences)} label occurrences / {name_audit['unique_tgaz_id_count']} unique TGAZ IDs.",
            f"Displayed/source inconsistencies: {name_audit['inconsistency_count']}.",
            "",
            "The display rule is verbatim `NAME_SIM`; suffixes are not inferred from `TYPE_SIM`.",
            "Therefore `右扶风` (hvd_116125), `右扶风郡` (hvd_116126), and `左冯翊` "
            "(hvd_116218) remain distinct source records. Coordinate proximity or similar naming does not merge them.",
            "Canonical API responses independently return those same three simplified names and type `郡`; "
            "all three have empty `part_of` and source-note fields. Their validity/coordinates differ: "
            "右扶风 -300–573 at 108.93719/34.31799; 右扶风郡 23–265 at 108.50215/34.26251; "
            "左冯翊 -456–486 at 109.08048/34.53333.",
            "",
            "Answers to the focused review: (1) `郡` in `右扶风郡` is part of canonical `NAME_SIM`, not a frontend suffix. "
            "(2) `左冯翊` lacks it because that is the canonical source name; no source note explains why. "
            "(3) The source uses varying naming forms for records sharing type `郡`. "
            "(4) A historical naming explanation is plausible but not evidenced by these records, so none is asserted. "
            "(5) This is not a display-composition bug: processed labels exactly equal `NAME_SIM` and canonical API names.",
            "",
            "`清` (hvd_113648) is a canonical `政权` / independent regime record covering 1645–1911. "
            "It is hidden in local User Mode and retained in Developer Mode.",
        ],
    )

    hierarchy = {
        "generated_at": generated_at,
        "raw_type_to_display_family": TYPE_FAMILIES,
        "rows": [
            {
                "raw_type": raw_type,
                "display_family": family,
                **FAMILY_POLICIES[family],
            }
            for raw_type, family in sorted(TYPE_FAMILIES.items())
        ],
        "family_occurrence_counts_across_20_snapshots": dict(sorted(family_counts.items())),
        "user_mode_hidden_families": ["polity"],
        "developer_mode_hidden_families": [],
        "raw_types_preserved": True,
        "visual_channels": ["size", "stroke", "shape", "label priority"],
        "color_policy": "single historical accent with confidence halo; no raw-type rainbow",
        "zoom_label_budgets": {
            "low_below_6_8": 6,
            "baseline_6_8_to_8_6": 12,
            "high_8_6_and_above": 24,
        },
    }
    write_json(QA_DIR / "phase1_3_1b_feature_hierarchy.json", hierarchy)

    parity = {
        "generated_at": generated_at,
        "case_count": len(parity_cases),
        "strategy_c_all_unchanged": all(case["strategy_c_ids_unchanged"] for case in parity_cases),
        "all_labels_are_displayed_points": all(case["labels_are_displayed_points"] for case in parity_cases),
        "cases": parity_cases,
    }
    write_json(QA_DIR / "phase1_3_1b_display_parity.json", parity)
    result = {
        "type_audit_rows": len(type_rows),
        "name_occurrences": len(name_occurrences),
        "strategy_c_all_unchanged": parity["strategy_c_all_unchanged"],
        "all_labels_are_displayed_points": parity["all_labels_are_displayed_points"],
    }
    print(result)
    return result


if __name__ == "__main__":
    generate()
