from __future__ import annotations

import gzip
import json
import math
import statistics
from collections import defaultdict
from time import perf_counter
from typing import Any

from chronochina.config import INTERMEDIATE_DIR, PROCESSED_DIR, QA_DIR
from chronochina.io import read_json, sha256_file, utc_now, write_json


NORMALIZED_PATH = INTERMEDIATE_DIR / "tgaz_points.jsonl"
OUTPUT_DIR = PROCESSED_DIR / "explore"
INDEX_PATH = OUTPUT_DIR / "tgaz_compact.json"
FIELDS = [
    "tgaz_id",
    "name",
    "name_pinyin",
    "valid_from",
    "valid_to",
    "lon",
    "lat",
    "feature_type",
    "parent_source_id",
    "parent_name",
    "location_confidence",
]


def _records() -> list[dict[str, Any]]:
    with NORMALIZED_PATH.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def _tuple(row: dict[str, Any]) -> list[Any]:
    return [
        row["tgaz_id"],
        row["name_zh_hans"],
        row["name_pinyin"],
        row["valid_from"],
        row["valid_to"],
        row["lon"],
        row["lat"],
        row["feature_type"],
        row["parent_source_id"],
        row["parent_name"],
        row["location_confidence"],
    ]


def _inside(row: dict[str, Any], bbox: list[float], year: int) -> bool:
    west, south, east, north = bbox
    longitude_match = west <= row["lon"] <= east if west <= east else row["lon"] >= west or row["lon"] <= east
    return (
        longitude_match and south <= row["lat"] <= north and
        row["valid_from"] <= year <= row["valid_to"]
    )


def _query_cases() -> list[dict[str, Any]]:
    targets = [
        ("beijing_1911_dense", 116.40, 39.90, 1911, "dense"),
        ("beijing_1368", 116.40, 39.90, 1368, "temporal"),
        ("nanjing_1911", 118.80, 32.06, 1911, "east_china"),
        ("shanghai_1911", 121.47, 31.23, 1911, "east_china"),
        ("hangzhou_742", 120.16, 30.25, 742, "east_china"),
        ("jinan_1911", 117.00, 36.67, 1911, "north_china"),
        ("zhengzhou_1911", 113.63, 34.75, 1911, "north_china"),
        ("wuhan_1911", 114.31, 30.59, 1911, "central_china"),
        ("fuzhou_1911", 119.30, 26.08, 1911, "southeast"),
        ("guangzhou_1911", 113.26, 23.13, 1911, "south_china"),
        ("xian_23", 108.94, 34.34, 23, "five_anchor"),
        ("chengdu_553", 104.07, 30.67, 553, "five_anchor"),
        ("qingdao_bce201", 120.38, 36.07, -201, "five_anchor_bce"),
        ("qufu_556", 116.99, 35.58, 556, "five_anchor"),
        ("taiyuan_1911", 112.55, 37.87, 1911, "north_china"),
        ("shenyang_1911", 123.43, 41.80, 1911, "northeast"),
        ("random_east_14", 118.50, 33.00, 14, "random_covered"),
        ("random_north_607", 114.00, 38.50, 607, "random_covered"),
        ("urumqi_1911", 87.62, 43.82, 1911, "known_source_gap"),
        ("lhasa_1911", 91.13, 29.65, 1911, "known_source_gap"),
        ("xining_1911", 101.78, 36.62, 1911, "known_source_gap"),
        ("yellow_sea_1911", 124.50, 34.00, 1911, "empty_or_gap"),
    ]
    return [
        {
            "case_id": case_id,
            "center": [lon, lat],
            "bbox": [lon - 1, lat - 0.75, lon + 1, lat + 0.75],
            "year": year,
            "category": category,
        }
        for case_id, lon, lat, year, category in targets
    ]


def _five_anchor_parity(rows: list[dict[str, Any]], tuples: list[list[Any]]) -> dict[str, Any]:
    cases = []
    for anchor_item in read_json(PROCESSED_DIR / "anchors/index.json")["anchors"]:
        manifest = read_json(PROCESSED_DIR / anchor_item["manifest_path"])
        lon = manifest["modern_location"]["lon"]
        lat = manifest["modern_location"]["lat"]
        radius = manifest["default_radius_km"]
        lat_delta = radius / 110.574
        lon_delta = radius / (111.32 * math.cos(math.radians(lat)))
        bbox = [lon - lon_delta, lat - lat_delta, lon + lon_delta, lat + lat_delta]
        for year in manifest["available_periods"]:
            expected = sorted(row["tgaz_id"] for row in rows if _inside(row, bbox, year))
            actual = sorted(
                item[0]
                for item in tuples
                if (
                    bbox[0] <= item[5] <= bbox[2] and bbox[1] <= item[6] <= bbox[3] and
                    item[3] <= year <= item[4]
                )
            )
            cases.append(
                {
                    "anchor": manifest["anchor_id"],
                    "year": year,
                    "bbox": bbox,
                    "normalized_count": len(expected),
                    "compact_count": len(actual),
                    "ids_equal": expected == actual,
                }
            )
    return {
        "generated_at": utc_now(),
        "case_count": len(cases),
        "all_ids_equal": all(case["ids_equal"] for case in cases),
        "comparison": "same exact-year bbox query over normalized JSONL and compact browser tuples",
        "cases": cases,
    }


def build_explore_index() -> dict[str, Any]:
    rows = _records()
    tuples = [_tuple(row) for row in rows]
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "1.0",
        "generated_at": utc_now(),
        "fields": FIELDS,
        "source": {
            "dataset": "TGAZ / CHGIS CSV spatial index",
            "normalized_path": "data/intermediate/tgaz_points.jsonl",
            "normalized_sha256": sha256_file(NORMALIZED_PATH),
            "record_count": len(tuples),
            "canonical_uri_template": "http://maps.cga.harvard.edu/tgaz/placename/{TGAZ_ID}",
            "license": None,
        },
        "records": tuples,
    }
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    INDEX_PATH.write_bytes(encoded)

    object_encoded = json.dumps(rows, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    shards: dict[tuple[int, int], list[list[Any]]] = defaultdict(list)
    for item in tuples:
        shards[(math.floor(item[5] / 5), math.floor(item[6] / 5))].append(item)
    shard_sizes = sorted(
        len(json.dumps(items, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        for items in shards.values()
    )
    query_cases = _query_cases()
    measured_cases = []
    for case in query_cases:
        started = perf_counter()
        matches = [row["tgaz_id"] for row in rows if _inside(row, case["bbox"], case["year"])]
        elapsed_ms = (perf_counter() - started) * 1000
        measured_cases.append(
            {
                **case,
                "normalized_match_count": len(matches),
                "normalized_scan_ms": round(elapsed_ms, 3),
            }
        )
    write_json(
        OUTPUT_DIR / "query_cases_manifest.json",
        {"generated_at": utc_now(), "cases": query_cases},
    )
    benchmark = {
        "generated_at": utc_now(),
        "selected": "compact_global_client_index",
        "selection_reason": "single static payload is reproducible and needs no server; browser latency is measured separately",
        "options": [
            {
                "id": "compact_global_client_index",
                "implemented": True,
                "bytes": len(encoded),
                "gzip_bytes": len(gzip.compress(encoded, mtime=0)),
                "request_count": 1,
            },
            {
                "id": "five_degree_static_shards",
                "implemented": False,
                "measured_serialized_total_bytes": sum(shard_sizes),
                "shard_count": len(shard_sizes),
                "largest_shard_bytes": max(shard_sizes),
                "median_shard_bytes": int(statistics.median(shard_sizes)),
                "reason_not_selected": "adds shard routing and multi-request invalidation before global payload is proven inadequate",
            },
            {
                "id": "sqlite_rtree",
                "implemented": False,
                "reason_not_selected": "browser delivery would add WASM/OPFS or a local service",
            },
            {
                "id": "backend_api",
                "implemented": False,
                "reason_not_selected": "production service is outside this bounded MVP",
            },
        ],
        "object_json_bytes_for_comparison": len(object_encoded),
        "compact_reduction_percent": round((1 - len(encoded) / len(object_encoded)) * 100, 2),
        "python_normalized_scan_cases": measured_cases,
    }
    write_json(QA_DIR / "phase1_3_1c_storage_architecture_benchmark.json", benchmark)
    parity = _five_anchor_parity(rows, tuples)
    write_json(QA_DIR / "phase1_3_1c_five_anchor_viewport_parity.json", parity)
    result = {
        "phase": "1.3.1c",
        "track": "B",
        "status": "INDEX_BUILT",
        "record_count": len(tuples),
        "index_path": INDEX_PATH.relative_to(PROCESSED_DIR.parent.parent).as_posix(),
        "index_bytes": len(encoded),
        "gzip_bytes": benchmark["options"][0]["gzip_bytes"],
        "parity_case_count": parity["case_count"],
        "parity_pass": parity["all_ids_equal"],
    }
    write_json(QA_DIR / "phase1_3_1c_explore_generation.json", result)
    return result
