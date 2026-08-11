from __future__ import annotations

import argparse
import json
import math
import os
import time
from collections import Counter, defaultdict
from html import escape
from pathlib import Path
from typing import Any, Iterable

import httpx
from shapely.geometry import box
from shapely.geometry.base import BaseGeometry

from chronochina.config import INTERMEDIATE_DIR, PROCESSED_DIR, PROJECT_ROOT, QA_DIR, RAW_DIR, TGAZ_DETAIL_URL
from chronochina.io import USER_AGENT, read_json, sha256_bytes, utc_now, write_json
from chronochina.qa.geographic_plausibility import (
    DEFAULT_CONFIG,
    OpenFreeMapWaterProvider,
    PlausibilityConfig,
    WaterMosaic,
    api_coordinate_crosscheck,
    classify_feature,
    classify_point,
    config_as_dict,
    load_v6_index,
    safe_v6_crosscheck,
    visual_dot_coordinate,
)
from chronochina.spatial import haversine
from chronochina.tgaz_detail import decode_tgaz_json, parse_tgaz_detail


PHASE1_1_INDEX_PATH = PROCESSED_DIR / "phase1_1" / "index.json"
STRATEGY_COMPARISON_PATH = QA_DIR / "phase1_1_display_strategy_comparison.json"
PARITY_OUTLIERS_PATH = QA_DIR / "v6_parity_outliers.json"
OUTPUT_DIR = QA_DIR / "geographic_plausibility"
OCCURRENCES_PATH = OUTPUT_DIR / "all_occurrences.json"
UNIQUE_FEATURES_PATH = OUTPUT_DIR / "unique_features.json"
SUMMARY_PATH = OUTPUT_DIR / "summary.md"
QINGDAO_JSON_PATH = OUTPUT_DIR / "qingdao_bce201_diagnostic.json"
QINGDAO_MD_PATH = OUTPUT_DIR / "qingdao_bce201_diagnostic.md"
V6_CROSSCHECK_PATH = OUTPUT_DIR / "v6_water_crosscheck.json"
CORRECTION_CANDIDATES_PATH = OUTPUT_DIR / "coordinate_correction_candidates.json"
ARTIFACT_DIR = PROJECT_ROOT / "artifacts" / "phase1_2_1"
QINGDAO_SVG_PATH = ARTIFACT_DIR / "qingdao_bce201_geographic_qa.svg"
QA_API_DIR = RAW_DIR / "geographic_plausibility" / "tgaz_api"


def _feature_from_occurrence(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "Feature",
        "id": row["tgaz_id"],
        "geometry": {
            "type": "Point",
            "coordinates": [row["longitude"], row["latitude"]],
        },
        "properties": {
            "tgaz_id": row["tgaz_id"],
            "name": row["name"],
            "feature_type": row["feature_type"],
            "valid_from": row["valid_from"],
            "valid_to": row["valid_to"],
            "parent_name": row["parent"],
        },
    }


def _load_strategy_c_sets() -> dict[tuple[str, int], dict[str, set[str]]]:
    report = read_json(STRATEGY_COMPARISON_PATH)
    result: dict[tuple[str, int], dict[str, set[str]]] = {}
    for case in report["cases"]:
        if case["strategy"] != "type_diverse_spatial":
            continue
        result[(case["anchor"], case["year"])] = {
            "points": set(case["displayed_point_ids"]),
            "labels": set(case["displayed_label_ids"]),
        }
    return result


def load_occurrences() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    index = read_json(PHASE1_1_INDEX_PATH)
    strategy = _load_strategy_c_sets()
    occurrences: list[dict[str, Any]] = []
    for anchor_id, anchor in index["anchors"].items():
        for year_text, relative_path in anchor["slices"].items():
            year = int(year_text)
            collection = read_json(PROCESSED_DIR / relative_path)
            display = strategy[(anchor_id, year)]
            for feature in collection["features"]:
                properties = feature["properties"]
                lon, lat = feature["geometry"]["coordinates"]
                occurrences.append(
                    {
                        "occurrence_key": f"{anchor_id}|{year}|{feature['id']}",
                        "anchor_id": anchor_id,
                        "anchor_display_name": anchor["display_name"],
                        "year": year,
                        "active": True,
                        "displayed_by_strategy_c": feature["id"] in display["points"],
                        "displayed_label_by_strategy_c": feature["id"] in display["labels"],
                        "tgaz_id": properties["tgaz_id"],
                        "name": properties["name"],
                        "valid_from": properties["valid_from"],
                        "valid_to": properties["valid_to"],
                        "latitude": lat,
                        "longitude": lon,
                        "feature_type": properties["feature_type"],
                        "parent": properties.get("parent_name"),
                        "distance_from_modern_anchor_km": properties[
                            "distance_to_anchor_km"
                        ],
                        "source": {
                            "source_id": properties.get("source_id"),
                            "source_record_id": properties.get("source_record_id"),
                            "source_url": properties.get("source_url"),
                            "source_data_source": properties.get(
                                "source_data_source"
                            ),
                        },
                    }
                )
    return occurrences, index


def build_mosaics(
    occurrences: list[dict[str, Any]],
    index: dict[str, Any],
    provider: OpenFreeMapWaterProvider,
    *,
    config: PlausibilityConfig = DEFAULT_CONFIG,
) -> tuple[dict[str, WaterMosaic], WaterMosaic]:
    by_anchor: dict[str, set[tuple[float, float]]] = defaultdict(set)
    for row in occurrences:
        by_anchor[row["anchor_id"]].add((row["longitude"], row["latitude"]))
    mosaics: dict[str, WaterMosaic] = {}
    for anchor_id, coordinates in sorted(by_anchor.items()):
        anchor = index["anchors"][anchor_id]
        mosaics[anchor_id] = provider.build_mosaic(
            coordinates,
            anchor_id=anchor_id,
            zoom=config.analysis_zoom,
            padding_tiles=config.tile_padding,
            origin_lon=anchor["modern_location"]["lon"],
            origin_lat=anchor["modern_location"]["lat"],
        )
    qingdao_bce = [
        (row["longitude"], row["latitude"])
        for row in occurrences
        if row["anchor_id"] == "qingdao" and row["year"] == -201
    ]
    qingdao = index["anchors"]["qingdao"]
    r1_mosaic = provider.build_mosaic(
        qingdao_bce,
        anchor_id="qingdao_bce201_r1_reproduction",
        zoom=config.r1_reproduction_zoom,
        padding_tiles=config.tile_padding,
        origin_lon=qingdao["modern_location"]["lon"],
        origin_lat=qingdao["modern_location"]["lat"],
    )
    return mosaics, r1_mosaic


def _world_pixel(lon: float, lat: float, zoom: float, tile_size: int) -> tuple[float, float]:
    world = tile_size * 2**zoom
    x = (lon + 180.0) / 360.0 * world
    sine = math.sin(math.radians(max(-85.05112878, min(85.05112878, lat))))
    y = (0.5 - math.log((1 + sine) / (1 - sine)) / (4 * math.pi)) * world
    return x, y


def _world_pixel_to_lonlat(x: float, y: float, zoom: float, tile_size: int) -> tuple[float, float]:
    world = tile_size * 2**zoom
    lon = x / world * 360.0 - 180.0
    mercator = math.pi - 2 * math.pi * y / world
    lat = math.degrees(math.atan(math.sinh(mercator)))
    return lon, lat


def _visual_dot_observation(
    feature: dict[str, Any],
    mosaic: WaterMosaic,
    config: PlausibilityConfig,
) -> dict[str, Any]:
    lon, lat = feature["geometry"]["coordinates"]
    anchor_x, anchor_y = _world_pixel(
        lon, lat, config.phase1_2_map_zoom, config.maplibre_world_tile_size_px
    )
    center_lon, center_lat = visual_dot_coordinate(lon, lat, config=config)
    center = classify_point(center_lon, center_lat, mosaic, config=config)
    radius_px = 5.5
    samples: list[dict[str, Any]] = []
    for index in range(24):
        angle = index / 24 * math.tau
        sample_x = anchor_x + config.history_dot_center_offset_px + radius_px * math.cos(angle)
        sample_y = anchor_y + radius_px * math.sin(angle)
        sample_lon, sample_lat = _world_pixel_to_lonlat(
            sample_x,
            sample_y,
            config.phase1_2_map_zoom,
            config.maplibre_world_tile_size_px,
        )
        observation = classify_point(sample_lon, sample_lat, mosaic, config=config)
        samples.append(
            {
                "longitude": sample_lon,
                "latitude": sample_lat,
                "water_membership": observation.get("water_membership"),
            }
        )
    marine_overlap = any(sample["water_membership"] == "marine" for sample in samples)
    inland_overlap = any(sample["water_membership"] == "inland" for sample in samples)
    return {
        "marker_anchor": "left",
        "css_dot_box": "11px border-box after 4px button padding",
        "source_coordinate_is_marker_element_left_midpoint": True,
        "dot_center_offset_px_east": config.history_dot_center_offset_px,
        "dot_radius_px": radius_px,
        "dot_center_coordinate": {
            "longitude": round(center_lon, 8),
            "latitude": round(center_lat, 8),
        },
        "dot_center_geometry": center,
        "dot_footprint_overlaps_modern_marine_water": marine_overlap,
        "dot_footprint_overlaps_modern_inland_water": inland_overlap,
        "interpretation": (
            "rendered_symbol_overlap_only; source coordinate remains separate"
            if marine_overlap or inland_overlap
            else "no rendered-symbol water overlap"
        ),
    }


def classify_occurrences(
    occurrences: list[dict[str, Any]],
    mosaics: dict[str, WaterMosaic],
    *,
    config: PlausibilityConfig = DEFAULT_CONFIG,
) -> None:
    for row in occurrences:
        row["geometry_observation"] = classify_feature(
            _feature_from_occurrence(row), mosaics[row["anchor_id"]], config=config
        )


def _existing_parity_outliers() -> dict[str, dict[str, Any]]:
    payload = read_json(PARITY_OUTLIERS_PATH)
    return {row["hypothesized_tgaz_id"]: row for row in payload["outliers"]}


def _load_existing_api_detail(tgaz_id: str) -> dict[str, Any] | None:
    parsed = INTERMEDIATE_DIR / "tgaz_detail" / f"{tgaz_id}.json"
    if parsed.exists():
        return read_json(parsed)
    qa_parsed = QA_API_DIR / f"{tgaz_id}.parsed.json"
    return read_json(qa_parsed) if qa_parsed.exists() else None


def _fetch_qa_api_details(tgaz_ids: Iterable[str]) -> dict[str, Any]:
    requested = sorted(set(tgaz_ids))
    records: dict[str, Any] = {}
    failures: list[dict[str, Any]] = []
    with httpx.Client(
        follow_redirects=True,
        timeout=httpx.Timeout(20.0),
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    ) as client:
        for index, tgaz_id in enumerate(requested):
            existing = _load_existing_api_detail(tgaz_id)
            if existing:
                records[tgaz_id] = {"status": "existing_frozen_cache"}
                continue
            raw_path = QA_API_DIR / f"{tgaz_id}.json"
            parsed_path = QA_API_DIR / f"{tgaz_id}.parsed.json"
            try:
                if raw_path.exists():
                    content = raw_path.read_bytes()
                    cache_status = "existing_phase1_2_1_raw"
                else:
                    response = client.get(TGAZ_DETAIL_URL.format(tgaz_id=tgaz_id))
                    response.raise_for_status()
                    content = response.content
                    payload, _, _ = decode_tgaz_json(content)
                    if payload.get("sys_id") != tgaz_id:
                        raise RuntimeError(
                            f"requested {tgaz_id}; API returned {payload.get('sys_id')!r}"
                        )
                    raw_path.parent.mkdir(parents=True, exist_ok=True)
                    temporary = raw_path.with_name(f"{raw_path.name}.part")
                    temporary.write_bytes(content)
                    os.replace(temporary, raw_path)
                    cache_status = "downloaded_phase1_2_1_raw"
                payload, parse_mode, parse_warning = decode_tgaz_json(content)
                parsed = parse_tgaz_detail(payload)
                write_json(parsed_path, parsed)
                records[tgaz_id] = {
                    "status": cache_status,
                    "source_url": TGAZ_DETAIL_URL.format(tgaz_id=tgaz_id),
                    "sha256": sha256_bytes(content),
                    "size_bytes": len(content),
                    "json_parse_mode": parse_mode,
                    "json_parse_warning": parse_warning,
                }
            except Exception as error:
                failures.append(
                    {
                        "tgaz_id": tgaz_id,
                        "error_type": type(error).__name__,
                        "error": str(error),
                    }
                )
            if index < len(requested) - 1 and records.get(tgaz_id, {}).get(
                "status"
            ) == "downloaded_phase1_2_1_raw":
                time.sleep(0.4)
    manifest = {
        "generated_at_utc": utc_now(),
        "purpose": "Phase 1.2.1 read-only source crosscheck; never merged into frozen detail cache",
        "requested_count": len(requested),
        "records": records,
        "failures": failures,
    }
    write_json(QA_API_DIR / "manifest.json", manifest)
    return manifest


def _qa_category(
    observation: dict[str, Any],
    api: dict[str, Any],
    v6: dict[str, Any],
    v6_observation: dict[str, Any] | None,
) -> str | None:
    if observation["classification"] not in {"modern_water", "boundary_uncertain"}:
        return None
    if v6["match_status"] == "exact_id_metadata_conflict":
        return "MATCHING_ERROR_OR_AMBIGUITY"
    api_agrees = api.get("coordinate_within_10m") is True
    if observation["classification"] == "modern_water":
        if api_agrees and observation.get("water_membership") == "inland":
            return "POSSIBLE_MODERN_RESERVOIR_OR_HYDROLOGY_CHANGE"
        if (
            api_agrees
            and v6.get("reliable_match")
            and v6_observation
            and v6_observation["classification"] == "modern_land"
            and (v6.get("distance_csv_to_v6_km") or 0) >= 1.0
            and (observation.get("distance_to_modern_land_km") or 0) >= 2.0
        ):
            return "LIKELY_STALE_COORDINATE"
        if (
            api_agrees
            and v6.get("reliable_match")
            and v6_observation
            and v6_observation["classification"] in {"modern_water", "boundary_uncertain"}
        ):
            return "SOURCE_AGREEMENT_BUT_GEOGRAPHICALLY_SUSPICIOUS"
        if v6["match_status"] == "no_exact_id_match":
            return "MATCHING_UNCERTAINTY"
    return "UNRESOLVED"


def enrich_unique_features(
    occurrences: list[dict[str, Any]],
    mosaics: dict[str, WaterMosaic],
    *,
    config: PlausibilityConfig = DEFAULT_CONFIG,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in occurrences:
        grouped[row["tgaz_id"]].append(row)
    abnormal_ids = {
        tgaz_id
        for tgaz_id, rows in grouped.items()
        if any(
            row["geometry_observation"]["classification"]
            in {"modern_water", "boundary_uncertain"}
            for row in rows
        )
    }
    qingdao_ids = {
        row["tgaz_id"]
        for row in occurrences
        if row["anchor_id"] == "qingdao" and row["year"] == -201
    }
    api_manifest = _fetch_qa_api_details(abnormal_ids | qingdao_ids)
    v6_index = load_v6_index()
    parity = _existing_parity_outliers()
    unique: list[dict[str, Any]] = []
    v6_rows: list[dict[str, Any]] = []
    correction_candidates: list[dict[str, Any]] = []

    for tgaz_id, rows in sorted(grouped.items()):
        representative = rows[0]
        coordinates = sorted({(row["longitude"], row["latitude"]) for row in rows})
        observations = {
            row["geometry_observation"]["classification"] for row in rows
        }
        abnormal_rows = [
            row
            for row in rows
            if row["geometry_observation"]["classification"]
            in {"modern_water", "boundary_uncertain"}
        ]
        feature = _feature_from_occurrence(representative)
        item: dict[str, Any] = {
            "tgaz_id": tgaz_id,
            "name": representative["name"],
            "valid_from": representative["valid_from"],
            "valid_to": representative["valid_to"],
            "feature_type": representative["feature_type"],
            "parent": representative["parent"],
            "occurrence_count": len(rows),
            "occurrence_keys": sorted(row["occurrence_key"] for row in rows),
            "coordinates": [
                {"longitude": lon, "latitude": lat} for lon, lat in coordinates
            ],
            "coordinate_consistent_across_occurrences": len(coordinates) == 1,
            "geometry_classifications": sorted(observations),
            "abnormal_occurrence_count": len(abnormal_rows),
            "qa_category": None,
        }
        if abnormal_rows or tgaz_id in qingdao_ids:
            focus = abnormal_rows[0] if abnormal_rows else representative
            feature = _feature_from_occurrence(focus)
            api = api_coordinate_crosscheck(
                feature, _load_existing_api_detail(tgaz_id)
            )
            v6 = safe_v6_crosscheck(feature, v6_index.get(tgaz_id))
            v6_observation = None
            if v6.get("reliable_match") and v6.get("v6_coordinate"):
                candidate = v6["v6_coordinate"]
                v6_observation = classify_point(
                    candidate["longitude"],
                    candidate["latitude"],
                    mosaics[focus["anchor_id"]],
                    config=config,
                )
            category = _qa_category(
                focus["geometry_observation"], api, v6, v6_observation
            )
            item.update(
                {
                    "focus_geometry_observation": focus["geometry_observation"],
                    "api_crosscheck": api,
                    "v6_crosscheck": v6,
                    "v6_geometry_observation": v6_observation,
                    "existing_v6_parity_outlier": parity.get(tgaz_id),
                    "qa_category": category,
                }
            )
            if abnormal_rows:
                v6_row = {
                    "tgaz_id": tgaz_id,
                    "name": representative["name"],
                    "current_coordinate": {
                        "longitude": focus["longitude"],
                        "latitude": focus["latitude"],
                    },
                    "current_geometry_observation": focus[
                        "geometry_observation"
                    ],
                    "api_crosscheck": api,
                    "v6_crosscheck": v6,
                    "v6_geometry_observation": v6_observation,
                    "in_existing_v6_parity_outliers": tgaz_id in parity,
                    "existing_parity_outlier": parity.get(tgaz_id),
                    "qa_category": category,
                }
                v6_rows.append(v6_row)
                recommended_action = (
                    "review_for_future_migration"
                    if category == "LIKELY_STALE_COORDINATE"
                    else "retain_current"
                    if category
                    == "SOURCE_AGREEMENT_BUT_GEOGRAPHICALLY_SUSPICIOUS"
                    else "insufficient_evidence"
                )
                correction_candidates.append(
                    {
                        "tgaz_id": tgaz_id,
                        "name": representative["name"],
                        "current_canonical_coordinate": v6_row[
                            "current_coordinate"
                        ],
                        "candidate_source": (
                            "CHGIS V6 Time Series County Points"
                            if v6.get("v6_coordinate")
                            else None
                        ),
                        "candidate_coordinate": v6.get("v6_coordinate"),
                        "distance_between_coordinates_km": v6.get(
                            "distance_csv_to_v6_km"
                        ),
                        "current_modern_land_water_status": focus[
                            "geometry_observation"
                        ],
                        "candidate_modern_land_water_status": v6_observation,
                        "match_confidence": v6.get("match_confidence"),
                        "evidence": {
                            "api_crosscheck": api,
                            "v6_field_checks": v6.get("field_checks"),
                            "qa_category": category,
                        },
                        "recommended_action": recommended_action,
                    }
                )
        unique.append(item)

    api_failures = api_manifest["failures"]
    if api_failures:
        for item in unique:
            if item["tgaz_id"] in {failure["tgaz_id"] for failure in api_failures}:
                item["api_fetch_failure"] = next(
                    failure
                    for failure in api_failures
                    if failure["tgaz_id"] == item["tgaz_id"]
                )
    return unique, v6_rows, correction_candidates


def _qingdao_diagnostic(
    occurrences: list[dict[str, Any]],
    unique_by_id: dict[str, dict[str, Any]],
    analysis_mosaic: WaterMosaic,
    r1_mosaic: WaterMosaic,
    *,
    config: PlausibilityConfig = DEFAULT_CONFIG,
) -> dict[str, Any]:
    rows = [
        row
        for row in occurrences
        if row["anchor_id"] == "qingdao" and row["year"] == -201
    ]
    points: list[dict[str, Any]] = []
    screenshot_water_ids: list[str] = []
    source_water_ids: list[str] = []
    for row in rows:
        feature = _feature_from_occurrence(row)
        r1_observation = classify_feature(feature, r1_mosaic, config=config)
        visual = _visual_dot_observation(feature, r1_mosaic, config)
        if visual["dot_footprint_overlaps_modern_marine_water"]:
            screenshot_water_ids.append(row["tgaz_id"])
        if r1_observation.get("water_membership") == "marine":
            source_water_ids.append(row["tgaz_id"])
        crosscheck = unique_by_id[row["tgaz_id"]]
        points.append(
            {
                **{
                    key: row[key]
                    for key in (
                        "tgaz_id",
                        "name",
                        "valid_from",
                        "valid_to",
                        "latitude",
                        "longitude",
                        "feature_type",
                        "parent",
                        "distance_from_modern_anchor_km",
                        "active",
                        "displayed_by_strategy_c",
                        "displayed_label_by_strategy_c",
                    )
                },
                "analysis_geometry_observation": row["geometry_observation"],
                "r1_zoom_geometry_observation": r1_observation,
                "phase1_2_visual_dot_observation": visual,
                "api_crosscheck": crosscheck.get("api_crosscheck"),
                "v6_crosscheck": crosscheck.get("v6_crosscheck"),
                "v6_geometry_observation": crosscheck.get(
                    "v6_geometry_observation"
                ),
                "existing_v6_parity_outlier": crosscheck.get(
                    "existing_v6_parity_outlier"
                ),
                "qa_category": crosscheck.get("qa_category"),
            }
        )
    reliable_v6_matches = [
        point
        for point in points
        if (point.get("v6_crosscheck") or {}).get("reliable_match")
    ]
    v6_coordinate_differences = [
        point["tgaz_id"]
        for point in reliable_v6_matches
        if ((point.get("v6_crosscheck") or {}).get("distance_csv_to_v6_km") or 0)
        > 0.01
    ]
    v6_water_to_land = [
        point["tgaz_id"]
        for point in reliable_v6_matches
        if point["r1_zoom_geometry_observation"]["classification"]
        == "modern_water"
        and (point.get("v6_geometry_observation") or {}).get("classification")
        == "modern_land"
    ]
    api_agreement_ids = [
        point["tgaz_id"]
        for point in points
        if (point.get("api_crosscheck") or {}).get("coordinate_within_10m") is True
    ]
    existing_parity_outlier_ids = [
        point["tgaz_id"]
        for point in points
        if point.get("existing_v6_parity_outlier") is not None
    ]
    boundary_review_ids = [
        point["tgaz_id"]
        for point in points
        if point["analysis_geometry_observation"]["classification"]
        == "boundary_uncertain"
    ]
    return {
        "case": "Qingdao BCE201",
        "generated_at_utc": utc_now(),
        "active_record_count": len(rows),
        "displayed_point_count": sum(row["displayed_by_strategy_c"] for row in rows),
        "source_coordinate_modern_water_count_r1_zoom": len(source_water_ids),
        "source_coordinate_modern_water_tgaz_ids_r1_zoom": sorted(source_water_ids),
        "rendered_dot_footprint_marine_overlap_count": len(screenshot_water_ids),
        "rendered_dot_footprint_marine_overlap_tgaz_ids": sorted(
            screenshot_water_ids
        ),
        "api_coordinate_agreement_count": len(api_agreement_ids),
        "api_coordinate_agreement_tgaz_ids": sorted(api_agreement_ids),
        "reliable_v6_match_count": len(reliable_v6_matches),
        "v6_coordinate_difference_count": len(v6_coordinate_differences),
        "v6_coordinate_difference_tgaz_ids": sorted(v6_coordinate_differences),
        "v6_water_to_land_count": len(v6_water_to_land),
        "v6_water_to_land_tgaz_ids": sorted(v6_water_to_land),
        "existing_parity_outlier_count": len(existing_parity_outlier_ids),
        "existing_parity_outlier_tgaz_ids": sorted(existing_parity_outlier_ids),
        "remaining_boundary_review_tgaz_ids": sorted(boundary_review_ids),
        "key_diagnosis": (
            "The R1 screenshot's orange DOM symbols can overlap water even when the "
            "source coordinate is on modern land because Marker(anchor='left') places "
            "the coordinate at the element edge, not at the orange dot center. Geometry "
            "observation and rendered-symbol observation are reported separately."
        ),
        "analysis_reference": analysis_mosaic.reference_source,
        "r1_reproduction_reference": r1_mosaic.reference_source,
        "points": points,
    }


def _count_geometry(items: Iterable[dict[str, Any]]) -> Counter[str]:
    return Counter(item["geometry_observation"]["classification"] for item in items)


def _summary_payload(
    occurrences: list[dict[str, Any]],
    unique: list[dict[str, Any]],
    v6_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    occurrence_counts = _count_geometry(occurrences)
    abnormal_unique = [item for item in unique if item["qa_category"]]
    unique_class = Counter(
        classification
        for item in unique
        for classification in item["geometry_classifications"]
    )
    water_occurrences = [
        row
        for row in occurrences
        if row["geometry_observation"]["classification"] == "modern_water"
    ]
    category_counts = Counter(item["qa_category"] for item in abnormal_unique)
    category_names = (
        "LIKELY_STALE_COORDINATE",
        "SOURCE_AGREEMENT_BUT_GEOGRAPHICALLY_SUSPICIOUS",
        "POSSIBLE_MODERN_COASTLINE_CHANGE",
        "POSSIBLE_MODERN_RESERVOIR_OR_HYDROLOGY_CHANGE",
        "MATCHING_UNCERTAINTY",
        "MATCHING_ERROR_OR_AMBIGUITY",
        "UNRESOLVED",
    )
    return {
        "total_occurrences_checked": len(occurrences),
        "unique_features_checked": len(unique),
        "modern_land_occurrence_count": occurrence_counts["modern_land"],
        "modern_water_occurrence_count": occurrence_counts["modern_water"],
        "marine_water_occurrence_count": sum(
            row["geometry_observation"].get("water_membership") == "marine"
            for row in water_occurrences
        ),
        "inland_water_occurrence_count": sum(
            row["geometry_observation"].get("water_membership") == "inland"
            for row in water_occurrences
        ),
        "boundary_uncertain_occurrence_count": occurrence_counts[
            "boundary_uncertain"
        ],
        "unknown_occurrence_count": occurrence_counts["unknown"],
        "unique_feature_classification_membership_counts": dict(unique_class),
        "unique_abnormal_feature_count": len(abnormal_unique),
        "high_priority_review_count": sum(
            item.get("focus_geometry_observation", {}).get("triage")
            in {"moderate_offshore", "far_offshore", "inland_far_interior"}
            for item in abnormal_unique
        ),
        "v6_matched_anomaly_count": sum(
            row["v6_crosscheck"].get("reliable_match") for row in v6_rows
        ),
        "v6_corrected_to_land_candidate_count": category_counts[
            "LIKELY_STALE_COORDINATE"
        ],
        "unresolved_count": category_counts["UNRESOLVED"]
        + category_counts["MATCHING_UNCERTAINTY"]
        + category_counts["MATCHING_ERROR_OR_AMBIGUITY"],
        "qa_category_counts": {
            name: category_counts[name] for name in category_names
        },
    }


def _write_summary(summary: dict[str, Any], qingdao: dict[str, Any]) -> None:
    category_lines = "\n".join(
        f"- `{name}`: {count}"
        for name, count in summary["qa_category_counts"].items()
    ) or "- None"
    text = f"""# Phase 1.2.1 Geographic Plausibility Summary

Generated: {utc_now()}

Modern water is a QA warning, not proof that a historical coordinate is wrong.

## Coverage

- total occurrences checked: {summary['total_occurrences_checked']}
- unique features checked: {summary['unique_features_checked']}
- modern-land occurrences: {summary['modern_land_occurrence_count']}
- modern-water occurrences: {summary['modern_water_occurrence_count']}
- marine-water occurrences: {summary['marine_water_occurrence_count']}
- inland-water occurrences: {summary['inland_water_occurrence_count']}
- boundary-uncertain occurrences: {summary['boundary_uncertain_occurrence_count']}
- geometry unknown occurrences: {summary['unknown_occurrence_count']}
- high-priority review features: {summary['high_priority_review_count']}
- V6 matched anomaly features: {summary['v6_matched_anomaly_count']}
- V6 corrected-to-land candidates: {summary['v6_corrected_to_land_candidate_count']}
- unresolved / matching-uncertain features: {summary['unresolved_count']}

## Qingdao BCE201

- active/displayed points: {qingdao['active_record_count']} / {qingdao['displayed_point_count']}
- source coordinates in R1 modern water: {qingdao['source_coordinate_modern_water_count_r1_zoom']}
- rendered orange dot footprints overlapping R1 marine water: {qingdao['rendered_dot_footprint_marine_overlap_count']}
- affected IDs: {', '.join(qingdao['rendered_dot_footprint_marine_overlap_tgaz_ids']) or 'None'}

The source-coordinate result and rendered-symbol result are intentionally separate.

## Root-cause categories

{category_lines}
"""
    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text(text, encoding="utf-8")


def _write_qingdao_markdown(diagnostic: dict[str, Any]) -> None:
    lines = [
        "# Qingdao BCE201 Geographic Diagnostic",
        "",
        f"Generated: {diagnostic['generated_at_utc']}",
        "",
        "> `modern_water` is a geometry observation and never an automatic historical-error verdict.",
        "",
        f"Active/displayed: {diagnostic['active_record_count']} / {diagnostic['displayed_point_count']}.",
        f"Source coordinates in R1 water: {diagnostic['source_coordinate_modern_water_count_r1_zoom']}.",
        "Rendered orange-dot footprints overlapping R1 marine water: "
        f"{diagnostic['rendered_dot_footprint_marine_overlap_count']} "
        f"({', '.join(diagnostic['rendered_dot_footprint_marine_overlap_tgaz_ids']) or 'None'}).",
        "",
        "The screenshot observation is reproducible at the rendered-symbol level, but it must not be attributed to the source coordinate unless the point-in-polygon result also says water. `Marker(anchor='left')` anchors the coordinate at the DOM element's left edge; the orange dot is drawn east of that anchor.",
        "",
        "## Required diagnostic answers",
        "",
        f"1. Active records: **{diagnostic['active_record_count']}**.",
        f"2. Strategy C displayed points: **{diagnostic['displayed_point_count']}**.",
        "3. Source coordinates in modern marine water: "
        f"**{diagnostic['source_coordinate_modern_water_count_r1_zoom']}**; visually affected IDs are rendered-symbol overlaps, not source-water IDs.",
        "4. Visually sea-overlapping IDs: "
        f"**{', '.join(diagnostic['rendered_dot_footprint_marine_overlap_tgaz_ids']) or 'None'}**. Their source-coordinate distance to modern land is 0 km; see coastline distance in the table.",
        f"5. Canonical API agrees within 10 m for **{diagnostic['api_coordinate_agreement_count']}/{diagnostic['active_record_count']}** records.",
        f"6. Reliable exact-metadata V6 matches: **{diagnostic['reliable_v6_match_count']}/{diagnostic['active_record_count']}**.",
        "7. V6 coordinate differs by more than 0.01 km for: "
        f"**{', '.join(diagnostic['v6_coordinate_difference_tgaz_ids']) or 'None'}**.",
        f"8. V6 changes a source coordinate from water to land: **{diagnostic['v6_water_to_land_count']}**.",
        f"9. Existing parity outlier evidence: **{diagnostic['existing_parity_outlier_count']}** matching records.",
        "10. Remaining coordinate review: no Qingdao BCE201 marine source-coordinate anomaly; "
        f"boundary review remains for **{', '.join(diagnostic['remaining_boundary_review_tgaz_ids']) or 'None'}**, and the UI marker-anchor defect remains open.",
        "",
        "| TGAZ_ID | Name | CSV coordinate | R1 source status | Coast distance km | API=CSV | V6 match | V6 delta km | Visual dot overlaps sea |",
        "|---|---|---|---|---:|---|---|---:|---|",
    ]
    for point in diagnostic["points"]:
        api = point["api_crosscheck"] or {}
        v6 = point["v6_crosscheck"] or {}
        r1 = point["r1_zoom_geometry_observation"]
        visual = point["phase1_2_visual_dot_observation"]
        lines.append(
            "| {id} | {name} | {lon:.5f}, {lat:.5f} | {status} | {distance} | {api} | {match} | {delta} | {visual} |".format(
                id=point["tgaz_id"],
                name=point["name"],
                lon=point["longitude"],
                lat=point["latitude"],
                status=r1["classification"],
                distance=r1.get("distance_to_modern_coastline_km"),
                api=api.get("coordinate_within_10m"),
                match=v6.get("match_status"),
                delta=v6.get("distance_csv_to_v6_km"),
                visual=visual["dot_footprint_overlaps_modern_marine_water"],
            )
        )
    QINGDAO_MD_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _svg_path(geometry: BaseGeometry, project) -> str:
    commands: list[str] = []
    polygons = (
        [geometry]
        if geometry.geom_type == "Polygon"
        else list(geometry.geoms)
        if geometry.geom_type in {"MultiPolygon", "GeometryCollection"}
        else []
    )
    for polygon in polygons:
        if polygon.geom_type != "Polygon":
            continue
        for ring in [polygon.exterior, *polygon.interiors]:
            coordinates = list(ring.coords)
            if not coordinates:
                continue
            x, y = project(*coordinates[0])
            commands.append(f"M{x:.1f},{y:.1f}")
            for lon, lat in coordinates[1:]:
                x, y = project(lon, lat)
                commands.append(f"L{x:.1f},{y:.1f}")
            commands.append("Z")
    return " ".join(commands)


def render_qingdao_svg(
    diagnostic: dict[str, Any],
    mosaic: WaterMosaic,
) -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    points = diagnostic["points"]
    longitudes = [point["longitude"] for point in points]
    latitudes = [point["latitude"] for point in points]
    west, east = min(longitudes) - 0.12, max(longitudes) + 0.12
    south, north = min(latitudes) - 0.10, max(latitudes) + 0.10
    width, height = 1440, 900
    map_left, map_top, map_width, map_height = 55, 80, 970, 760
    clipped = mosaic.marine_wgs84.intersection(box(west, south, east, north))

    def project(lon: float, lat: float) -> tuple[float, float]:
        x = map_left + (lon - west) / (east - west) * map_width
        y = map_top + (north - lat) / (north - south) * map_height
        return x, y

    water_path = _svg_path(clipped, project)
    elements = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1440" height="900" viewBox="0 0 1440 900">',
        '<rect width="1440" height="900" fill="#f6f1e7"/>',
        '<text x="55" y="42" font-family="Microsoft YaHei, sans-serif" font-size="25" font-weight="700" fill="#18333f">青岛 · 公元前201年 Geographic Plausibility QA</text>',
        f'<rect x="{map_left}" y="{map_top}" width="{map_width}" height="{map_height}" fill="#e8e0d1" stroke="#66777c"/>',
        f'<path d="{water_path}" fill="#a9ccd3" fill-rule="evenodd" stroke="#548997" stroke-width="1.4"/>',
    ]
    label_offsets = [(12, -8), (12, 18), (-138, -8)]
    label_offsets_by_id = {
        "hvd_112389": (-138, -10),
        "hvd_85344": (20, 28),
        "hvd_112412": (12, 18),
        "hvd_85487": (-138, -8),
    }
    for index, point in enumerate(points):
        x, y = project(point["longitude"], point["latitude"])
        v6 = point.get("v6_crosscheck") or {}
        candidate = v6.get("v6_coordinate")
        if candidate and v6.get("reliable_match"):
            vx, vy = project(candidate["longitude"], candidate["latitude"])
            if (v6.get("distance_csv_to_v6_km") or 0) > 0.01:
                delta = v6["distance_csv_to_v6_km"]
                elements.append(
                    f'<line x1="{x:.1f}" y1="{y:.1f}" x2="{vx:.1f}" y2="{vy:.1f}" stroke="#5b6470" stroke-width="1.3" stroke-dasharray="5 4"/>'
                )
                elements.append(
                    f'<text x="{(x + vx) / 2 + 5:.1f}" y="{(y + vy) / 2 - 5:.1f}" font-family="Microsoft YaHei, sans-serif" font-size="11" fill="#4d5960">{delta:.3f} km</text>'
                )
                elements.append(
                    f'<polygon points="{vx:.1f},{vy-7:.1f} {vx-6:.1f},{vy+5:.1f} {vx+6:.1f},{vy+5:.1f}" fill="#1c7182" stroke="#fff" stroke-width="1.5"/>'
                )
        elements.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6" fill="#b54e2e" stroke="#fff" stroke-width="2"/>'
        )
        visual = point["phase1_2_visual_dot_observation"]
        if visual["dot_footprint_overlaps_modern_marine_water"]:
            visual_coordinate = visual["dot_center_coordinate"]
            dx, dy = project(
                visual_coordinate["longitude"], visual_coordinate["latitude"]
            )
            elements.append(
                f'<line x1="{x:.1f}" y1="{y:.1f}" x2="{dx:.1f}" y2="{dy:.1f}" stroke="#c18222" stroke-width="2"/>'
            )
            elements.append(
                f'<path d="M{dx-5:.1f},{dy-5:.1f} L{dx+5:.1f},{dy+5:.1f} M{dx+5:.1f},{dy-5:.1f} L{dx-5:.1f},{dy+5:.1f}" stroke="#c18222" stroke-width="2.5"/>'
            )
        offset_x, offset_y = label_offsets_by_id.get(
            point["tgaz_id"], label_offsets[index % len(label_offsets)]
        )
        label = escape(f"{point['tgaz_id']} {point['name']}")
        elements.append(
            f'<text x="{x+offset_x:.1f}" y="{y+offset_y:.1f}" font-family="Microsoft YaHei, sans-serif" font-size="13" fill="#253f48">{label}</text>'
        )

    overlap_ids = diagnostic["rendered_dot_footprint_marine_overlap_tgaz_ids"]
    elements.extend(
        [
            '<g font-family="Microsoft YaHei, sans-serif" font-size="14" fill="#263f48">',
            '<text x="1055" y="105" font-size="19" font-weight="700">诊断图例</text>',
            '<circle cx="1070" cy="145" r="6" fill="#b54e2e" stroke="#fff" stroke-width="2"/><text x="1090" y="150">CSV / canonical source coordinate</text>',
            '<polygon points="1070,178 1064,190 1076,190" fill="#1c7182"/><text x="1090" y="190">可靠 V6 candidate</text>',
            '<path d="M1064,225 L1076,237 M1076,225 L1064,237" stroke="#c18222" stroke-width="2.5"/><text x="1090" y="235">Phase 1.2 rendered dot center</text>',
            '<text x="1055" y="285" font-size="18" font-weight="700">关键结果</text>',
            f'<text x="1055" y="320">Source coordinates in R1 water: {diagnostic["source_coordinate_modern_water_count_r1_zoom"]}</text>',
            f'<text x="1055" y="350">Orange-dot water overlaps: {diagnostic["rendered_dot_footprint_marine_overlap_count"]}</text>',
            f'<text x="1055" y="380">IDs: {escape(", ".join(overlap_ids) or "None")}</text>',
            '<text x="1055" y="430" font-size="13">OpenFreeMap © OpenMapTiles · Data from OpenStreetMap.</text>',
            '<text x="1055" y="452" font-size="13">Modern coastline ≠ historical coastline.</text>',
            '<text x="1055" y="474" font-size="13">No coordinate was modified.</text>',
            '<text x="1055" y="530" font-size="18" font-weight="700">视觉重叠个案</text>',
            '<text x="1055" y="565" font-size="13">hvd_112389 琅邪郡</text>',
            '<text x="1055" y="587" font-size="13">source: land · coast 5.267 km · no county V6 match</text>',
            '<text x="1055" y="625" font-size="13">hvd_85344 琅邪县</text>',
            '<text x="1055" y="647" font-size="13">source: land · coast 5.267 km · V6 Δ 0.460 km</text>',
            '<text x="1055" y="685" font-size="13">Root cause: left-anchored DOM marker footprint.</text>',
            '</g>',
            '</svg>',
        ]
    )
    QINGDAO_SVG_PATH.write_text("\n".join(elements) + "\n", encoding="utf-8")


def run(*, config: PlausibilityConfig = DEFAULT_CONFIG) -> dict[str, Any]:
    occurrences, index = load_occurrences()
    provider = OpenFreeMapWaterProvider()
    mosaics, r1_mosaic = build_mosaics(
        occurrences, index, provider, config=config
    )
    classify_occurrences(occurrences, mosaics, config=config)
    unique, v6_rows, correction_candidates = enrich_unique_features(
        occurrences, mosaics, config=config
    )
    unique_by_id = {item["tgaz_id"]: item for item in unique}
    qingdao = _qingdao_diagnostic(
        occurrences,
        unique_by_id,
        mosaics["qingdao"],
        r1_mosaic,
        config=config,
    )
    summary = _summary_payload(occurrences, unique, v6_rows)
    source_manifest = provider.write_manifest()

    write_json(
        OCCURRENCES_PATH,
        {
            "generated_at_utc": utc_now(),
            "phase": "1.2.1",
            "config": config_as_dict(config),
            "occurrence_key_semantics": "anchor_id|year|TGAZ_ID",
            "count": len(occurrences),
            "occurrences": occurrences,
        },
    )
    write_json(
        UNIQUE_FEATURES_PATH,
        {
            "generated_at_utc": utc_now(),
            "phase": "1.2.1",
            "deduplication_key": "TGAZ_ID",
            "count": len(unique),
            "features": unique,
        },
    )
    write_json(QINGDAO_JSON_PATH, qingdao)
    write_json(
        V6_CROSSCHECK_PATH,
        {
            "generated_at_utc": utc_now(),
            "existing_parity_outlier_source": PARITY_OUTLIERS_PATH.relative_to(
                PROJECT_ROOT
            ).as_posix(),
            "matching_policy": "exact SYS_ID/TGAZ_ID plus name, BEG, END, feature type; no fuzzy match",
            "anomaly_count": len(v6_rows),
            "records": v6_rows,
        },
    )
    write_json(
        CORRECTION_CANDIDATES_PATH,
        {
            "generated_at_utc": utc_now(),
            "automatic_migration_performed": False,
            "allowed_actions": [
                "review_for_future_migration",
                "retain_current",
                "insufficient_evidence",
            ],
            "review_record_count": len(correction_candidates),
            "correction_candidate_count": sum(
                row["recommended_action"] == "review_for_future_migration"
                for row in correction_candidates
            ),
            "records": correction_candidates,
        },
    )
    _write_qingdao_markdown(qingdao)
    _write_summary(summary, qingdao)
    render_qingdao_svg(qingdao, mosaics["qingdao"])
    result = {
        "generated_at_utc": utc_now(),
        "summary": summary,
        "qingdao": {
            key: qingdao[key]
            for key in (
                "active_record_count",
                "displayed_point_count",
                "source_coordinate_modern_water_count_r1_zoom",
                "source_coordinate_modern_water_tgaz_ids_r1_zoom",
                "rendered_dot_footprint_marine_overlap_count",
                "rendered_dot_footprint_marine_overlap_tgaz_ids",
            )
        },
        "source_manifest": {
            "path": source_manifest["tilejson"]["path"],
            "snapshot_id": source_manifest["snapshot_id"],
            "tile_count": source_manifest["tile_count"],
        },
        "outputs": {
            "occurrences": OCCURRENCES_PATH.relative_to(PROJECT_ROOT).as_posix(),
            "unique_features": UNIQUE_FEATURES_PATH.relative_to(PROJECT_ROOT).as_posix(),
            "qingdao": QINGDAO_JSON_PATH.relative_to(PROJECT_ROOT).as_posix(),
            "v6_crosscheck": V6_CROSSCHECK_PATH.relative_to(PROJECT_ROOT).as_posix(),
            "correction_candidates": CORRECTION_CANDIDATES_PATH.relative_to(
                PROJECT_ROOT
            ).as_posix(),
            "visualization": QINGDAO_SVG_PATH.relative_to(PROJECT_ROOT).as_posix(),
        },
    }
    write_json(OUTPUT_DIR / "run_report.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.parse_args()
    result = run()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
