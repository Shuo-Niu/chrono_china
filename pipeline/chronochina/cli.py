from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

from .tgaz_index import fetch_tgaz_index, normalize_tgaz_points, validate_tgaz_index
from .probe import run_g1
from .tgaz_detail import run_g2
from .identity import run_g3
from .build import run_g4
from .verification import finalize_g4
from .g5 import run_g5
from .chgis_v6 import run_g6
from .g7 import run_g7
from .phase1 import run_phase1
from .phase1_1 import run_phase1_1
from .explore import build_explore_index


def run_g0() -> dict[str, object]:
    manifest = fetch_tgaz_index()
    schema = validate_tgaz_index()
    normalization = normalize_tgaz_points()
    return {
        "gate": "G0",
        "status": "PASS",
        "manifest": manifest,
        "schema": schema,
        "normalization": normalization,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ChronoChina Phase 0/1 data pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("g0", help="Fetch, validate, and normalize the TGAZ CSV index")
    subparsers.add_parser("g1", help="Resolve anchors and run a real spatial/temporal query")
    subparsers.add_parser("g2", help="Fetch and parse 10 canonical TGAZ detail records")
    subparsers.add_parser("g3", help="Audit identity safety on real spatial query results")
    subparsers.add_parser("g4", help="Build the first real Beijing map dataset")
    subparsers.add_parser("g4-verify", help="Finalize G4 from fresh build and test evidence")
    subparsers.add_parser("g5", help="Probe five anchors and select the county-level anchor")
    subparsers.add_parser("g6", help="Probe CHGIS V6 via Dataverse and produce a parity report")
    subparsers.add_parser("g7", help="Probe operational access to the 1912-1949 dataset")
    subparsers.add_parser("phase1", help="Generate the real five-anchor Phase 1 dataset")
    subparsers.add_parser(
        "phase1-1", help="Generate the frozen-data Phase 1.1 display experiment"
    )
    subparsers.add_parser(
        "phase1-3-1c-explore", help="Build the compact viewport exploration index"
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    arguments = build_parser().parse_args(argv)
    if arguments.command == "g0":
        result = run_g0()
        output = {
            "gate": result["gate"],
            "status": result["status"],
            "record_count": result["schema"]["record_count"],
            "normalized_point_count": result["normalization"]["normalized_chgis_point_count"],
        }
    elif arguments.command == "g1":
        result = run_g1()
        output = {
            "gate": result["gate"],
            "status": result["status"],
            "anchor_id": result["anchor"]["anchor_id"],
            "geonames_record_id": result["anchor"]["source"]["record_id"],
            "representative_years": result["probe"]["representative_years"],
            "best_year": result["best_slice"]["year"],
            "best_year_count": result["best_slice"]["count"],
        }
    elif arguments.command == "g2":
        result = run_g2()
        output = {
            "gate": result["gate"],
            "status": result["status"],
            "requested_count": result["requested_count"],
            "success_count": result["success_count"],
            "complete_parse_count": result["complete_parse_count"],
            "failure_count": result["failure_count"],
        }
    elif arguments.command == "g3":
        result = run_g3()
        output = {
            "gate": result["gate"],
            "status": result["status"],
            "audited_real_feature_count": result["audited_real_feature_count"],
            "violation_count": len(result["violations"]),
        }
    elif arguments.command == "g4":
        result = run_g4()
        output = {
            "gate": result["gate"],
            "status": result["status"],
            "anchor_id": result["anchor_id"],
            "year": result["year"],
            "feature_count": result["feature_count"],
            "detail_count": result["detail_count"],
            "location_status_counts": result["location_status_counts"],
        }
    elif arguments.command == "g4-verify":
        result = finalize_g4()
        output = {
            "gate": result["gate"],
            "status": result["status"],
            "vitest": result["vitest"],
            "playwright": result["playwright"],
            "freshness": result["freshness"],
        }
    elif arguments.command == "g5":
        result = run_g5()
        selection = result["county_candidate_selection"]
        output = {
            "gate": result["gate"],
            "status": result["status"],
            "final_anchor_ids": result["final_anchor_ids"],
            "selected_county_anchor": selection["selected_anchor_id"],
            "selected_county_name": selection["selected_display_name"],
            "negative_control_status": result["negative_control"]["coverage_status"],
        }
    elif arguments.command == "g6":
        result = run_g6()
        parity = result["parity"]
        output = {
            "gate": result["gate"],
            "status": result["status"],
            "capability": result["capability"],
            "record_count": result["shapefile"]["record_count"],
            "sample_size": parity["sample_size"],
            "tgaz_record_found_count": parity["tgaz_record_found_count"],
            "metric_match_counts": parity["metric_match_counts"],
            "license_conflict": result["dataset"]["license_conflict"],
        }
    elif arguments.command == "g7":
        result = run_g7()
        output = {
            "gate": result["gate"],
            "status": result["status"],
            "capability": result["capability"],
            "access_classification": result["access_classification"],
            "dataset_existence": result["dataset_existence"],
            "public_download": result["public_download"],
            "api": result["api"],
        }
    elif arguments.command == "phase1":
        result = run_phase1()
        output = {
            "phase": result["phase"],
            "status": result["status"],
            "anchor_statuses": result["anchor_statuses"],
            "enrichment": result["enrichment"],
            "semantic_matches_previous_same_input": result[
                "semantic_matches_previous_same_input"
            ],
            "freshness": result["freshness"],
        }
    elif arguments.command == "phase1-1":
        result = run_phase1_1()
        output = {
            "phase": result["phase"],
            "status": result["status"],
            "snapshot_count": result["snapshot_count"],
            "strategy_case_count": result["strategy_case_count"],
            "active_feature_occurrence_count": result[
                "active_feature_occurrence_count"
            ],
            "type_count": result["type_count"],
            "winner_selected": result["winner_selected"],
        }
    elif arguments.command == "phase1-3-1c-explore":
        output = build_explore_index()
    else:  # pragma: no cover - argparse enforces the known subcommands.
        raise AssertionError(arguments.command)
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
