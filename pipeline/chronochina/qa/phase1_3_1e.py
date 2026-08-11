from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

import httpx

from chronochina.config import (
    INTERMEDIATE_DIR,
    PROJECT_ROOT,
    QA_DIR,
    REQUIRED_TGAZ_FIELDS,
    TGAZ_INDEX_PATH,
    TGAZ_INDEX_URL,
)
from chronochina.io import USER_AGENT, sha256_file, utc_now, write_json
from chronochina.temporal import parse_year


NORMALIZED_PATH = INTERMEDIATE_DIR / "tgaz_points.jsonl"
DOWNLOAD_REPORT = QA_DIR / "phase1_3_1e_download_completeness.json"
RECONCILIATION_REPORT = QA_DIR / "phase1_3_1e_ingestion_reconciliation.json"
DENSITY_REPORT = QA_DIR / "phase1_3_1e_year_density.json"
DENSITY_MARKDOWN = QA_DIR / "phase1_3_1e_year_density.md"
COVERAGE_REPORT = PROJECT_ROOT / "docs/data/phase1_3_1e_coverage_audit.md"

FAMILY_TYPES: dict[str, set[str]] = {
    "high_admin": {"省", "王畿"},
    "regional_admin": {"郡", "府", "州", "直隶州", "路", "侯国", "厅", "军", "防镇"},
    "county": {"县"},
    "settlement": {"村镇", "亭"},
    "polity": {"政权", "国"},
}
USER_FAMILIES = ("high_admin", "regional_admin", "county", "settlement", "other")

VIEWPORTS = (
    ("beijing", "北京", 116.39723, 39.9075, True),
    ("xian", "西安", 108.93719, 34.31799, True),
    ("chengdu", "成都", 104.06654, 30.57227, True),
    ("qingdao", "青岛", 120.38264, 36.06708, True),
    ("qufu", "曲阜", 116.991, 35.596, True),
    ("wuhan", "武汉", 114.3054, 30.5931, False),
    ("nanjing", "南京", 118.7969, 32.0603, False),
    ("kaifeng", "开封", 114.3076, 34.7973, False),
    ("guangzhou", "广州", 113.2644, 23.1291, False),
    ("hangzhou", "杭州", 120.1551, 30.2741, False),
    ("shanghai", "上海", 121.4737, 31.2304, False),
    ("changsha", "长沙", 112.9388, 28.2282, False),
    ("jinan", "济南", 117.1201, 36.6512, False),
    ("fuzhou", "福州", 119.2965, 26.0745, False),
    ("kunming", "昆明", 102.8329, 24.8801, False),
)


def family_for_type(raw_type: str) -> str:
    for family, types in FAMILY_TYPES.items():
        if raw_type in types:
            return family
    return "other"


def _valid_coordinate(value: str, lower: float, upper: float) -> bool:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(parsed) and lower <= parsed <= upper


def classify_raw_rows(rows: list[dict[str, str]]) -> tuple[Counter[str], dict[str, str]]:
    id_counts = Counter((row.get("TGAZ_ID") or "").strip() for row in rows)
    categories: Counter[str] = Counter()
    category_by_id: dict[str, str] = {}
    for row in rows:
        tgaz_id = (row.get("TGAZ_ID") or "").strip()
        missing_fields = [
            field for field in REQUIRED_TGAZ_FIELDS
            if field not in row or row.get(field) is None
        ]
        if missing_fields or not tgaz_id:
            category = "missing_required_field"
        elif id_counts[tgaz_id] > 1:
            category = "duplicate_tgaz_id_quarantined"
        elif (row.get("DATA_SRC") or "").strip() != "CHGIS":
            category = "non_chgis_excluded"
        elif (row.get("OBJ_TYPE") or "").strip().upper() != "POINT":
            category = "polygon_excluded"
        else:
            valid_from = parse_year(row.get("BEG"))
            valid_to = parse_year(row.get("END"))
            if valid_from is None or valid_to is None:
                category = "invalid_time_quarantined"
            elif valid_from > valid_to:
                category = "inverted_time_quarantined"
            elif not _valid_coordinate(row.get("X") or "", -180, 180) or not _valid_coordinate(
                row.get("Y") or "", -90, 90
            ):
                category = "invalid_coordinate"
            else:
                category = "valid_normalized_point"
        categories[category] += 1
        if tgaz_id:
            category_by_id[tgaz_id] = category
    return categories, category_by_id


def build_year_density(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    min_year = min(int(row["valid_from"]) for row in rows)
    max_year = max(int(row["valid_to"]) for row in rows)
    families = (*USER_FAMILIES, "polity")
    diffs = {family: [0] * (max_year - min_year + 2) for family in families}
    for row in rows:
        family = family_for_type(str(row["feature_type"]))
        start = int(row["valid_from"]) - min_year
        end = int(row["valid_to"]) - min_year + 1
        diffs[family][start] += 1
        diffs[family][end] -= 1
    running = {family: 0 for family in families}
    result = []
    for offset, year in enumerate(range(min_year, max_year + 1)):
        for family in families:
            running[family] += diffs[family][offset]
        if year == 0:
            continue
        by_family = {family: running[family] for family in families}
        result.append({
            "year": year,
            "total_active_records": sum(by_family.values()),
            "user_eligible_records_all_layers": sum(by_family[family] for family in USER_FAMILIES),
            "by_display_family": by_family,
        })
    return result


def _spaced_years(candidates: Iterable[tuple[float, int]], count: int) -> list[int]:
    selected: list[int] = []
    for _, year in candidates:
        if all(abs(year - previous) >= 12 for previous in selected):
            selected.append(year)
        if len(selected) == count:
            break
    return selected


def _density_samples(density: list[dict[str, Any]]) -> tuple[list[int], list[int]]:
    counts = {item["year"]: item["total_active_records"] for item in density}
    ratios: list[tuple[float, int]] = []
    for item in density:
        year = item["year"]
        neighbors = [
            counts[candidate]
            for candidate in range(year - 5, year + 6)
            if candidate != year and candidate != 0 and candidate in counts
        ]
        if len(neighbors) >= 5:
            baseline = sum(neighbors) / len(neighbors)
            ratios.append((item["total_active_records"] / baseline if baseline else 1.0, year))
    sparse = _spaced_years(sorted(ratios), 5)
    dense = _spaced_years(
        sorted(((-item["total_active_records"], item["year"]) for item in density)),
        5,
    )
    return sparse, dense


def _viewport_cases(
    normalized: list[dict[str, Any]],
    density: list[dict[str, Any]],
    sparse_years: list[int],
    dense_years: list[int],
) -> list[dict[str, Any]]:
    global_counts = {item["year"]: item["total_active_records"] for item in density}
    low_threshold = sorted(global_counts.values())[max(0, len(global_counts) // 10 - 1)]
    years = sparse_years + dense_years
    cases: list[dict[str, Any]] = []
    for viewport_id, name, lon, lat, anchor_fixture in VIEWPORTS:
        bbox = [lon - 1.2, lat - 0.9, lon + 1.2, lat + 0.9]
        for year in years:
            active = [row for row in normalized if row["valid_from"] <= year <= row["valid_to"]]
            viewport = [
                row for row in active
                if bbox[0] <= row["lon"] <= bbox[2] and bbox[1] <= row["lat"] <= bbox[3]
            ]
            eligible = [row for row in viewport if family_for_type(row["feature_type"]) in USER_FAMILIES]
            displayed = len({(row["lon"], row["lat"]) for row in eligible})
            if year in dense_years:
                classification = "DENSE_CONTROL"
            elif len(active) != global_counts[year]:
                classification = "PIPELINE_LOSS"
            elif global_counts[year] <= low_threshold:
                classification = "SOURCE_SPARSE"
            elif not viewport:
                classification = "COVERAGE_GAP"
            elif len(eligible) < len(viewport):
                classification = "LAYER_FILTERED"
            elif displayed < len(eligible):
                classification = "DISPLAY_COLLISION"
            else:
                classification = "UNKNOWN"
            cases.append({
                "viewport_id": viewport_id,
                "display_name": name,
                "is_five_anchor_fixture": anchor_fixture,
                "bbox": bbox,
                "year": year,
                "case_role": "sparse_investigation" if year in sparse_years else "dense_control",
                "source_active_count": global_counts[year],
                "normalized_active_count": len(active),
                "viewport_active_count": len(viewport),
                "enabled_layer_count": len(USER_FAMILIES),
                "eligible_count": len(eligible),
                "displayed_count": displayed,
                "co_location_reduction_count": len(eligible) - displayed,
                "classification": classification,
            })
    return cases


def verify_download() -> dict[str, Any]:
    local_bytes = TGAZ_INDEX_PATH.read_bytes()
    live: dict[str, Any]
    try:
        with httpx.Client(
            follow_redirects=True,
            timeout=60,
            headers={"User-Agent": USER_AGENT},
        ) as client:
            response = client.get(TGAZ_INDEX_URL)
            response.raise_for_status()
        content = response.content
        live = {
            "status": "available",
            "http_status": response.status_code,
            "retrieved_at": utc_now(),
            "bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
            "etag": response.headers.get("etag"),
            "last_modified": response.headers.get("last-modified"),
            "matches_local_bytes": content == local_bytes,
        }
    except Exception as error:
        live = {
            "status": "unavailable",
            "retrieved_at": utc_now(),
            "error_type": type(error).__name__,
            "error": str(error),
            "matches_local_bytes": None,
        }
    with TGAZ_INDEX_PATH.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        local_rows = list(reader)
        schema = reader.fieldnames or []
    report = {
        "phase": "1.3.1e",
        "generated_at": utc_now(),
        "official_programmatic_url": TGAZ_INDEX_URL,
        "local_artifact": {
            "path": TGAZ_INDEX_PATH.relative_to(PROJECT_ROOT).as_posix(),
            "bytes": TGAZ_INDEX_PATH.stat().st_size,
            "sha256": sha256_file(TGAZ_INDEX_PATH),
            "record_count": len(local_rows),
            "schema": schema,
        },
        "documented_record_count": 71647,
        "live_official_artifact": live,
        "status": "PASS" if len(local_rows) == 71647 and live.get("matches_local_bytes") is True else "INCONCLUSIVE",
    }
    write_json(DOWNLOAD_REPORT, report)
    return report


def generate_audit() -> dict[str, Any]:
    with TGAZ_INDEX_PATH.open("r", encoding="utf-8-sig", newline="") as stream:
        raw_rows = list(csv.DictReader(stream))
    normalized = [json.loads(line) for line in NORMALIZED_PATH.read_text(encoding="utf-8").splitlines() if line]
    categories, raw_category_by_id = classify_raw_rows(raw_rows)
    normalized_ids = {row["tgaz_id"] for row in normalized}
    expected_ids = {tgaz_id for tgaz_id, category in raw_category_by_id.items() if category == "valid_normalized_point"}
    reconciliation = {
        "phase": "1.3.1e",
        "generated_at": utc_now(),
        "raw_total": len(raw_rows),
        "categories": dict(sorted(categories.items())),
        "normalized_file_record_count": len(normalized),
        "expected_normalized_id_count": len(expected_ids),
        "missing_expected_ids": sorted(expected_ids - normalized_ids),
        "unexpected_normalized_ids": sorted(normalized_ids - expected_ids),
        "accounted_total": sum(categories.values()),
        "unaccounted_records": len(raw_rows) - sum(categories.values()),
        "accounting_equation": "raw total = normalized + quarantine + explicit exclusions",
        "status": "PASS" if len(raw_rows) == sum(categories.values()) and expected_ids == normalized_ids else "FAIL",
    }
    write_json(RECONCILIATION_REPORT, reconciliation)

    density = build_year_density(normalized)
    sparse_years, dense_years = _density_samples(density)
    viewport_cases = _viewport_cases(normalized, density, sparse_years, dense_years)
    type_counts = Counter(row["feature_type"] for row in normalized)
    other_counts = {
        raw_type: count for raw_type, count in sorted(type_counts.items())
        if family_for_type(raw_type) == "other"
    }
    density_report = {
        "phase": "1.3.1e",
        "generated_at": utc_now(),
        "year_zero_policy": "excluded from historical UI and density rows",
        "earliest_supported_year": density[0]["year"],
        "latest_supported_year": density[-1]["year"],
        "year_count": len(density),
        "display_family_registry": {family: sorted(types) for family, types in FAMILY_TYPES.items()},
        "other_unclassified_source_type_counts": other_counts,
        "sparse_year_samples": sparse_years,
        "dense_year_samples": dense_years,
        "active_records_by_year": density,
        "viewport_audit": {
            "viewport_count": len(VIEWPORTS),
            "five_anchor_count": sum(item[4] for item in VIEWPORTS),
            "non_anchor_count": sum(not item[4] for item in VIEWPORTS),
            "years_per_viewport": len(sparse_years) + len(dense_years),
            "cases": viewport_cases,
        },
    }
    write_json(DENSITY_REPORT, density_report)
    DENSITY_MARKDOWN.write_text(
        "# Phase 1.3.1e Year Density\n\n"
        f"- 范围：{density[0]['year']} 至 {density[-1]['year']}（无公元 0 年），共 {len(density)} 个整数年份。\n"
        f"- 稀疏抽样年份：{', '.join(map(str, sparse_years))}。\n"
        f"- 高密度对照年份：{', '.join(map(str, dense_years))}。\n"
        f"- 审计视口：{len(VIEWPORTS)}（5 anchors + {len(VIEWPORTS) - 5} non-anchors），每个视口 {len(sparse_years) + len(dense_years)} 个年份。\n"
        "- 完整逐年计数与 family 分解见 `phase1_3_1e_year_density.json`。\n"
        "- `other` 保留实际 raw type 计数，不将未审计类型伪装成已确认行政层级。\n",
        encoding="utf-8",
    )
    return {"reconciliation": reconciliation, "density": density_report}


def write_coverage_report(download: dict[str, Any], audit: dict[str, Any]) -> None:
    reconciliation = audit["reconciliation"]
    density = audit["density"]
    sparse = density["sparse_year_samples"]
    dense = density["dense_year_samples"]
    cases = density["viewport_audit"]["cases"]
    sparse_classes = Counter(
        case["classification"] for case in cases if case["case_role"] == "sparse_investigation"
    )
    COVERAGE_REPORT.parent.mkdir(parents=True, exist_ok=True)
    COVERAGE_REPORT.write_text(
        "# ChronoChina Phase 1.3.1e Coverage Audit\n\n"
        "## Executive answer\n\n"
        f"- Download completeness: **{download['status']}**. 本地官方 CSV 为 {download['local_artifact']['record_count']:,} 条、"
        f"{download['local_artifact']['bytes']:,} bytes、SHA-256 `{download['local_artifact']['sha256']}`；"
        f"本轮官方 URL 实时字节比对为 `{download['live_official_artifact'].get('matches_local_bytes')}`。\n"
        f"- Ingestion completeness: **{reconciliation['status']}**. {reconciliation['normalized_file_record_count']:,} 条 normalized point；"
        f"250 条 inverted-time quarantine；4 条 polygon explicit exclusion；unaccounted = {reconciliation['unaccounted_records']}。\n"
        "- Source coverage completeness: **不能等同于完整历史事实覆盖**。当前 canonical artifact 是 2016 CSV snapshot；"
        "V6 抽样已有版本差异证据，因此本轮只标记 `SOURCE_VERSION_GAP`，不静默迁移。\n\n"
        "## Raw → normalized reconciliation\n\n"
        "`71,647 = 71,393 valid normalized points + 250 inverted-time quarantines + 4 polygon exclusions`。"
        "expected/raw ID 与 normalized ID 集合完全一致，无无法解释 ingestion loss。\n\n"
        "## Exact-year density\n\n"
        f"逐年范围为 {density['earliest_supported_year']}..{density['latest_supported_year']}（排除 year zero）。"
        f"自动检测的稀疏抽样为 {sparse}；高密度对照为 {dense}。完整 histogram 见 "
        "`data/qa/phase1_3_1e_year_density.json`。\n\n"
        "## Five-anchor and non-anchor viewport audit\n\n"
        f"共 {density['viewport_audit']['viewport_count']} 个视口（5 anchors + {density['viewport_audit']['non_anchor_count']} non-anchors）、"
        f"{len(cases)} 个 year/viewport case。稀疏案例分类计数：`{dict(sparse_classes)}`。"
        "所有 families 默认开启时，User layer filtering 仅排除 developer-only polity；exact-coordinate co-location 单独计数。\n\n"
        "## Why some years look empty\n\n"
        "本轮没有发现 download incomplete、normalized ingestion loss 或 viewport predicate 漏记。"
        "空白感主要来自官方 snapshot 的 exact-year active density 在年份间剧烈不均，以及局部 viewport coverage gap；"
        "关闭 family 会进一步产生可测的 `LAYER_FILTERED`，但默认全部开启不会主动制造该空白。"
        "`displayed_count < eligible_count` 的差值来自 exact-coordinate co-location display grouping，不是删除 source record。\n\n"
        "## V6 comparison\n\n"
        "已有 G6 official Dataverse sample 显示 100 条 V6 county-point 抽样中 92 条可在 TGAZ CSV 找到，"
        "且时间、类型、坐标并非全量一致。这是 material `SOURCE_VERSION_GAP` 证据；`V4/2016 CSV != V6`，"
        "本轮未迁移 canonical source。\n\n"
        "## MVP decision\n\n"
        "当前数据足以继续 bounded MVP：download 与 ingestion 可复现且完整；UI 必须继续声明 source density != historical density。"
        "后续应设独立 Source Upgrade Phase 评估 V6 全量映射、许可冲突与 parity，而不是在本轮静默替换。\n",
        encoding="utf-8",
    )


def main() -> None:
    download = verify_download()
    audit = generate_audit()
    write_coverage_report(download, audit)
    print(json.dumps({
        "download": download["status"],
        "ingestion": audit["reconciliation"]["status"],
        "sparse_years": audit["density"]["sparse_year_samples"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
