from __future__ import annotations

from typing import Any

from .config import (
    ANCHOR_SPECS,
    COUNTY_CANDIDATE_SPECS,
    DEFAULT_RADIUS_KM,
    INTERMEDIATE_DIR,
    NEGATIVE_CONTROL_SPEC,
    QA_DIR,
)
from .geonames import load_anchors
from .io import utc_now, write_json
from .probe import probe_anchor
from .tgaz_index import load_normalized_points


FINAL_ANCHORS_PATH = INTERMEDIATE_DIR / "anchors.json"
G5_REPORT_PATH = QA_DIR / "g5_anchor_density.json"
EXCLUDED_ADMIN1_TOKENS = ("inner mongolia", "qinghai", "xinjiang", "tibet", "xizang")


def _compact_probe(probe: dict[str, Any]) -> dict[str, Any]:
    compact = {key: value for key, value in probe.items() if key != "slices"}
    compact["slices"] = [
        {
            "year": slice_["year"],
            "count": slice_["count"],
            "feature_types": slice_["feature_types"],
            "sample_tgaz_ids": [row["tgaz_id"] for row in slice_["sample"][:5]],
        }
        for slice_ in probe["slices"]
    ]
    return compact


def _admin1_name(anchor: dict[str, Any]) -> str | None:
    admin1 = anchor["resolution"].get("selected_admin1")
    return admin1.get("ascii_name") if admin1 else None


def _outside_excluded_regions(anchor: dict[str, Any]) -> bool:
    admin1 = (_admin1_name(anchor) or "").casefold()
    return bool(admin1) and not any(token in admin1 for token in EXCLUDED_ADMIN1_TOKENS)


def run_g5() -> dict[str, Any]:
    all_anchors = load_anchors()
    by_id = {anchor["anchor_id"]: anchor for anchor in all_anchors}
    points = load_normalized_points()
    fixed_ids = [spec["anchor_id"] for spec in ANCHOR_SPECS]
    candidate_ids = [spec["anchor_id"] for spec in COUNTY_CANDIDATE_SPECS]

    fixed_probes = {
        anchor_id: probe_anchor(points, by_id[anchor_id], DEFAULT_RADIUS_KM)
        for anchor_id in fixed_ids
    }
    candidate_probes = {
        anchor_id: probe_anchor(points, by_id[anchor_id], DEFAULT_RADIUS_KM)
        for anchor_id in candidate_ids
    }
    candidate_assessments = []
    for anchor_id in candidate_ids:
        anchor = by_id[anchor_id]
        probe = candidate_probes[anchor_id]
        eligible = (
            _outside_excluded_regions(anchor)
            and probe["nonempty_period_count"] >= 3
            and probe["neighborhood_distinct_name_count"] >= 3
            and probe["neighborhood_distinct_parent_count"] >= 2
        )
        candidate_assessments.append(
            {
                "anchor_id": anchor_id,
                "display_name": anchor["display_name"],
                "geonames_record_id": anchor["source"]["record_id"],
                "admin1": anchor["resolution"].get("selected_admin1"),
                "outside_excluded_regions": _outside_excluded_regions(anchor),
                "eligible": eligible,
                "score": [
                    probe["nonempty_period_count"],
                    probe["unique_tgaz_id_count"],
                    probe["neighborhood_distinct_name_count"],
                    probe["neighborhood_distinct_parent_count"],
                ],
                "probe": _compact_probe(probe),
            }
        )
    eligible_candidates = [item for item in candidate_assessments if item["eligible"]]
    selected_assessment = max(
        eligible_candidates,
        key=lambda item: tuple(item["score"]),
        default=None,
    )

    selected_anchor = None
    if selected_assessment:
        selected_anchor = by_id[selected_assessment["anchor_id"]]
        selected_probe = candidate_probes[selected_anchor["anchor_id"]]
        selected_anchor["anchor_role"] = "selected_county_anchor"
        selected_anchor["selection_reason"] = (
            "Highest deterministic density score among eligible county candidates; "
            "name/parent diversity is neighborhood evidence only, not lineage."
        )
        selected_anchor["available_periods"] = selected_probe["representative_years"]
        selected_anchor["coverage"]["pre_1912"] = "available"

    final_anchors = []
    for anchor_id in fixed_ids:
        anchor = by_id[anchor_id]
        anchor["anchor_role"] = "fixed_mvp_anchor"
        anchor["available_periods"] = fixed_probes[anchor_id]["representative_years"]
        anchor["coverage"]["pre_1912"] = (
            "available" if fixed_probes[anchor_id]["nonempty_period_count"] else "no_matching_records"
        )
        final_anchors.append(anchor)
    if selected_anchor:
        final_anchors.append(selected_anchor)
        write_json(FINAL_ANCHORS_PATH, final_anchors)

    negative = by_id[NEGATIVE_CONTROL_SPEC["anchor_id"]]
    negative_control = {
        "anchor_id": negative["anchor_id"],
        "display_name": negative["display_name"],
        "geonames_record_id": negative["source"]["record_id"],
        "admin1": negative["resolution"].get("selected_admin1"),
        "coverage_status": "outside_source_scope",
        "radius_expansion_attempted": False,
        "counts_toward_five_anchors": False,
    }
    fixed_pass = all(
        probe["nonempty_period_count"] >= 3 for probe in fixed_probes.values()
    )
    report = {
        "gate": "G5",
        "status": "PASS" if fixed_pass and selected_anchor is not None else "FAIL",
        "verified_at": utc_now(),
        "radius_km": DEFAULT_RADIUS_KM,
        "fixed_anchors": [
            {
                "anchor_id": anchor_id,
                "display_name": by_id[anchor_id]["display_name"],
                "geonames_record_id": by_id[anchor_id]["source"]["record_id"],
                "admin1": by_id[anchor_id]["resolution"].get("selected_admin1"),
                "probe": _compact_probe(fixed_probes[anchor_id]),
            }
            for anchor_id in fixed_ids
        ],
        "county_candidate_selection": {
            "hard_exclusions": ["Inner Mongolia", "Qinghai", "Xinjiang", "Tibet/Xizang"],
            "candidates": candidate_assessments,
            "selected_anchor_id": selected_anchor["anchor_id"] if selected_anchor else None,
            "selected_display_name": selected_anchor["display_name"] if selected_anchor else None,
            "selection_semantics": "Density selection only; no same-entity or lineage inference.",
        },
        "negative_control": negative_control,
        "final_anchor_ids": [anchor["anchor_id"] for anchor in final_anchors],
        "final_anchors_path": str(FINAL_ANCHORS_PATH),
    }
    write_json(G5_REPORT_PATH, report)
    if report["status"] != "PASS":
        raise RuntimeError("G5 failed: fixed-anchor density or county-candidate eligibility insufficient")
    return report
