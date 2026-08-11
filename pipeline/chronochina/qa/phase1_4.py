from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import urlsplit, urlunsplit

import httpx
import shapefile

from chronochina.io import write_json
from chronochina.qa.phase1_3_1f import display_family


REPO_ROOT = Path(__file__).resolve().parents[3]
QA_ROOT = REPO_ROOT / "data/qa/source_upgrade"
RAW_ROOT = REPO_ROOT / "data/raw/source_upgrade"
INTERMEDIATE_ROOT = REPO_ROOT / "data/intermediate/source_upgrade"
YEAR_MIN = -222
YEAR_MAX = 1911
ERA_SAMPLES = (
    ("Han", 100),
    ("Three Kingdoms", 250),
    ("Jin", 350),
    ("Northern and Southern Dynasties", 500),
    ("Sui", 600),
    ("Tang", 750),
    ("Song-Liao-Jin", 1100),
    ("Yuan", 1300),
    ("Ming", 1500),
    ("Qing 1820", 1820),
    ("Qing 1911", 1911),
)

V6_PATHS = {
    "time_county": REPO_ROOT / "data/raw/chgis_v6/v6_time_cnty_pts_utf_wgs84.zip",
    "time_prefecture": RAW_ROOT / "chgis_v6/v6_time_pref_pts_utf_wgs84.zip",
    "town_1820": RAW_ROOT / "chgis_v6/v6_1820_twn_pts_utf.zip",
    "town_1911": RAW_ROOT / "chgis_v6/v6_1911_twn_pts_utf.zip",
    "province_1820": RAW_ROOT / "chgis_v6/v6_1820_prov_pts_utf.zip",
    "province_1911": RAW_ROOT / "chgis_v6/v6_1911_prov_pts_utf.zip",
    "ming_stations": RAW_ROOT / "chgis_v6/ming_stations_2016.zip",
}

V4_PATHS = {
    "time_province": INTERMEDIATE_ROOT / "v4_time_province/Province_Point.DAT",
    "time_prefecture": INTERMEDIATE_ROOT / "v4_time_prefecture/Prefecture_Point.DAT",
    "time_county": INTERMEDIATE_ROOT / "v4_time_county/County_Point.DAT",
    "town_1820": INTERMEDIATE_ROOT / "v4_1820_town/PII_Point_1820_Town.DAT",
    "town_1911": INTERMEDIATE_ROOT / "v4_1911_town/Town_1911_Point.DAT",
}

ANCHORS = {
    "beijing": ("北京", 116.39723, 39.9075),
    "xian": ("西安", 108.92861, 34.25833),
    "chengdu": ("成都", 104.06667, 30.66667),
    "qingdao": ("青岛", 120.37194, 36.09861),
    "qufu": ("曲阜", 116.9914, 35.59667),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact(path: Path) -> dict[str, Any]:
    return {
        "path": path.relative_to(REPO_ROOT).as_posix(),
        "size_bytes": path.stat().st_size,
        "sha256": sha256(path),
    }


def _load_canonical() -> list[dict[str, Any]]:
    path = REPO_ROOT / "data/intermediate/tgaz_points.jsonl"
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle]


def _shapefile_records(path: Path, layer: str) -> list[dict[str, Any]]:
    reader = shapefile.Reader(str(path), encoding="utf-8")
    fields = [field[0] for field in reader.fields[1:]]
    result: list[dict[str, Any]] = []
    for raw in reader.iterRecords():
        row = dict(zip(fields, raw))
        if layer == "ming_stations":
            result.append({
                "candidate_id": f"ming_station_{row['YZ_ID']}",
                "chgis_id": f"hvd_{row['CHGIS_ID']}" if str(row.get("CHGIS_ID", "")).strip() else None,
                "name": row.get("YZNM_CH"),
                "feature_type": "驿站",
                "valid_from": None,
                "valid_to": None,
                "lon": row.get("YZ_LAT"),
                "lat": row.get("YZ_LONG"),
                "parent_name": row.get("10CNTY_CH"),
                "source_layer": layer,
            })
            continue
        x_key = "X_COOR" if "X_COOR" in row else "X_COORD"
        y_key = "Y_COOR" if "Y_COOR" in row else "Y_COORD"
        parent = row.get("CNTY_CH") or row.get("COUNT_CH") or row.get("LEV2_CH")
        lon = row.get(x_key)
        lat = row.get(y_key)
        result.append({
            "candidate_id": f"hvd_{str(row['SYS_ID']).strip()}",
            "name": str(row.get("NAME_CH") or "").strip(),
            "feature_type": str(row.get("TYPE_CH") or "").strip(),
            "valid_from": int(row["BEG_YR"]),
            "valid_to": int(row["END_YR"]),
            "lon": float(lon) if lon is not None else None,
            "lat": float(lat) if lat is not None else None,
            "parent_name": str(parent).strip() if parent else None,
            "source_layer": layer,
        })
    return result


def _mapinfo_records(path: Path) -> list[dict[str, Any]]:
    """Read legacy MapInfo DAT/DBF fields without stripping binary integer bytes."""
    payload = path.read_bytes()
    record_count = int.from_bytes(payload[4:8], "little")
    header_length = int.from_bytes(payload[8:10], "little")
    record_length = int.from_bytes(payload[10:12], "little")
    fields: list[tuple[str, str, int, int]] = []
    offset = 32
    field_offset = 1
    while payload[offset] != 0x0D:
        descriptor = payload[offset:offset + 32]
        name = descriptor[:11].split(b"\0", 1)[0].decode("ascii")
        fields.append((name, chr(descriptor[11]), descriptor[16], field_offset))
        field_offset += descriptor[16]
        offset += 32

    binary_int_fields = {"BEG_YR", "END_YR", "NOTE_ID", "SYS_ID", "SYS_ID_1", "LOC_ID", "GEO_ID"}
    records: list[dict[str, Any]] = []
    for index in range(record_count):
        start = header_length + index * record_length
        record = payload[start:start + record_length]
        if not record or record[0] == 0x2A:
            continue
        row: dict[str, Any] = {}
        for name, field_type, length, field_start in fields:
            value = record[field_start:field_start + length]
            if name in binary_int_fields:
                row[name] = int.from_bytes(value, "little", signed=True)
            elif field_type in {"N", "F"}:
                text = value.decode("ascii", errors="ignore").strip()
                row[name] = float(text) if text and "." in text else int(text) if text else None
            else:
                row[name] = value.rstrip(b"\0 ").decode("gbk", errors="replace")
        records.append(row)
    return records


def _v4_summary() -> dict[str, Any]:
    result: dict[str, Any] = {}
    for layer, path in V4_PATHS.items():
        rows = _mapinfo_records(path)
        periods = Counter()
        if layer == "town_1820":
            periods[(1820, 1820)] = len(rows)
        elif layer == "town_1911":
            periods[(1911, 1911)] = len(rows)
        else:
            periods.update((row["BEG_YR"], row["END_YR"]) for row in rows)
        result[layer] = {
            "artifact": artifact(path),
            "record_count": len(rows),
            "valid_interval_count": sum(count for (begin, end), count in periods.items() if begin <= end),
            "min_begin": min(begin for begin, _ in periods),
            "max_end": max(end for _, end in periods),
        }
    return result


def _active(records: Iterable[Mapping[str, Any]], year: int) -> int:
    return sum(
        1 for record in records
        if record.get("valid_from") is not None
        and int(record["valid_from"]) <= year <= int(record["valid_to"])
    )


def _v4_active(rows: Iterable[Mapping[str, Any]], year: int) -> int:
    return sum(1 for row in rows if int(row["BEG_YR"]) <= year <= int(row["END_YR"]))


def _hartwell_summary() -> dict[str, Any]:
    root = INTERMEDIATE_ROOT / "hartwell_v5/v5_Hartwell"
    raw_counts: Counter[tuple[int, str]] = Counter()
    unique_codes: defaultdict[tuple[int, str], set[str]] = defaultdict(set)
    for path in sorted(root.glob("*.shp")):
        parts = path.stem.split("_")
        year = int(parts[1])
        suffix = parts[-1]
        unit = suffix if suffix in {"c", "p", "d", "l", "s"} else "special_or_reference"
        reader = shapefile.Reader(str(path), encoding="latin1")
        fields = [field[0] for field in reader.fields[1:]]
        for index, raw in enumerate(reader.iterRecords()):
            row = dict(zip(fields, raw))
            key = str(row.get("CODE") or row.get("GB_CODE_EN") or f"{path.stem}:{index}")
            raw_counts[(year, unit)] += 1
            unique_codes[(year, unit)].add(key)
    return {
        "coverage_kind": "static_polygon_time_slices",
        "projection": "Gauss Kruger, Xian 1980, Zone 19",
        "counts": [
            {
                "year": year,
                "unit_code": unit,
                "raw_layer_rows": raw_counts[(year, unit)],
                "unique_hierarchical_or_reference_codes": len(unique_codes[(year, unit)]),
            }
            for year, unit in sorted(raw_counts)
        ],
        "counting_note": "Repeated regional/all-China layers are de-duplicated only by Hartwell CODE/GB_CODE_EN, never by name or proximity.",
    }


def _interval_series(
    records: Iterable[Mapping[str, Any]],
    *,
    begin_key: str = "valid_from",
    end_key: str = "valid_to",
    predicate: Any = None,
) -> dict[int, int]:
    difference = [0] * (YEAR_MAX - YEAR_MIN + 2)
    for record in records:
        if predicate is not None and not predicate(record):
            continue
        begin = max(YEAR_MIN, int(record[begin_key]))
        end = min(YEAR_MAX, int(record[end_key]))
        if begin > end:
            continue
        difference[begin - YEAR_MIN] += 1
        difference[end - YEAR_MIN + 1] -= 1
    current = 0
    result: dict[int, int] = {}
    for offset, year in enumerate(range(YEAR_MIN, YEAR_MAX + 1)):
        current += difference[offset]
        if year != 0:
            result[year] = current
    return result


def _series(records: Iterable[Mapping[str, Any]], family: str) -> dict[int, int]:
    return _interval_series(
        records,
        predicate=lambda record: display_family(str(record["feature_type"])) == family,
    )


def _era_values(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_year = {row["year"]: row for row in rows}
    return [{"era": era, **by_year[year]} for era, year in ERA_SAMPLES]


def generate_coverage() -> tuple[dict[str, Any], dict[str, Any]]:
    canonical = _load_canonical()
    v6 = {layer: _shapefile_records(path, layer) for layer, path in V6_PATHS.items()}
    v4_rows = {layer: _mapinfo_records(path) for layer, path in V4_PATHS.items()}
    canonical_settlement = _series(canonical, "settlement")
    canonical_high = _series(canonical, "high_admin")
    canonical_regional = _series(canonical, "regional_admin")
    canonical_county = _series(canonical, "county")
    canonical_village_town = _interval_series(
        canonical, predicate=lambda record: record["feature_type"] == "村镇"
    )
    v6_prefecture = _interval_series(v6["time_prefecture"])
    v6_county = _interval_series(v6["time_county"])
    canonical_ids = {record["tgaz_id"] for record in canonical}
    v6_prefecture_id_increment = _interval_series(
        record for record in v6["time_prefecture"]
        if record["candidate_id"] not in canonical_ids and record["lon"] is not None and record["lat"] is not None
    )
    v6_county_id_increment = _interval_series(
        record for record in v6["time_county"]
        if record["candidate_id"] not in canonical_ids and record["lon"] is not None and record["lat"] is not None
    )

    settlement_rows: list[dict[str, Any]] = []
    for year in range(YEAR_MIN, YEAR_MAX + 1):
        if year == 0:
            continue
        settlement_rows.append({
            "year": year,
            "canonical_settlement_family": canonical_settlement[year],
            "canonical_raw_village_town": canonical_village_town[year],
            "chgis_v6_static_town_points": (
                len(v6["town_1820"]) if year == 1820
                else len(v6["town_1911"]) if year == 1911
                else 0
            ),
            "fudan_v4_static_town_points": (
                len(v4_rows["town_1820"]) if year == 1820
                else len(v4_rows["town_1911"]) if year == 1911
                else 0
            ),
        })

    high_rows: list[dict[str, Any]] = []
    v4_province = v4_rows["time_province"]
    v4_province_series = _interval_series(v4_province, begin_key="BEG_YR", end_key="END_YR")
    for year in range(YEAR_MIN, YEAR_MAX + 1):
        if year == 0:
            continue
        high_rows.append({
            "year": year,
            "canonical_high_admin": canonical_high[year],
            "canonical_regional_admin": canonical_regional[year],
            "canonical_county": canonical_county[year],
            "chgis_v6_static_province_points": (
                len(v6["province_1820"]) if year == 1820
                else len(v6["province_1911"]) if year == 1911
                else 0
            ),
            "chgis_v6_time_prefecture_points": v6_prefecture[year],
            "chgis_v6_time_county_points": v6_county[year],
            "chgis_v6_prefecture_candidate_id_increment": v6_prefecture_id_increment[year],
            "chgis_v6_county_candidate_id_increment": v6_county_id_increment[year],
            "canonical_plus_v6_prefecture_id_union": canonical_regional[year] + v6_prefecture_id_increment[year],
            "canonical_plus_v6_county_id_union": canonical_county[year] + v6_county_id_increment[year],
            "fudan_v4_time_province_points": v4_province_series[year],
        })

    settlement = {
        "phase": "1.4",
        "generated_at_utc": utc_now(),
        "method": "Closed intervals for time series; static layers count only at their named snapshot year; year zero omitted.",
        "canonical_record_count": len(canonical),
        "candidate_layers": {
            "chgis_v6_towns": {
                "coverage_kind": "time_slice",
                "1820_records": len(v6["town_1820"]),
                "1911_records": len(v6["town_1911"]),
                "official_readme_status": "unchanged from V5; no other settlement years published",
            },
            "fudan_v4_towns": {
                "coverage_kind": "time_slice",
                "1820_records": len(v4_rows["town_1820"]),
                "1911_records": len(v4_rows["town_1911"]),
            },
            "ming_stations": {
                "coverage_kind": "static_thematic_corpus",
                "records": len(v6["ming_stations"]),
                "records_with_chgis_id": sum(1 for row in v6["ming_stations"] if row["chgis_id"]),
                "exact_year_usable": False,
                "reason": "No per-record BEG/END; courier stations are not a generic settlement layer.",
            },
            "hartwell": {"coverage_kind": "administrative_polygon_time_slices", "settlement_layer": "not_provided"},
        },
        "era_samples": _era_values(settlement_rows),
        "by_year": settlement_rows,
    }
    high = {
        "phase": "1.4",
        "generated_at_utc": utc_now(),
        "method": "Closed intervals for time series; static province layers count only at 1820/1911; Hartwell is separately reported as polygon snapshots.",
        "candidate_layers": {
            "chgis_v6_time_county": {"records": len(v6["time_county"]), "coverage_kind": "time_series"},
            "chgis_v6_time_prefecture": {"records": len(v6["time_prefecture"]), "coverage_kind": "time_series"},
            "chgis_v6_province": {
                "coverage_kind": "time_slice",
                "1820_records": len(v6["province_1820"]),
                "1911_records": len(v6["province_1911"]),
                "official_readme_status": "unchanged from V5; V6 publishes no updated province time-series core layer",
            },
            "fudan_v4": _v4_summary(),
            "hartwell": _hartwell_summary(),
        },
        "era_samples": _era_values(high_rows),
        "by_year": high_rows,
    }
    return settlement, high


def haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    radius = 6371.0088
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    value = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return radius * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))


def _compare(candidate: Mapping[str, Any], canonical: Mapping[str, Any] | None) -> dict[str, Any]:
    if canonical is None:
        return {
            "candidate_id": candidate["candidate_id"],
            "classification": ["uncertain_match"],
            "reason": "Candidate SYS_ID is absent from the canonical index; no name+nearest inference was attempted.",
        }
    distance_m = haversine_km(
        float(candidate["lon"]), float(candidate["lat"]),
        float(canonical["lon"]), float(canonical["lat"]),
    ) * 1000
    classes: list[str] = []
    if distance_m > 1:
        classes.append("same_entity_revised_coordinate")
    if (candidate["valid_from"], candidate["valid_to"]) != (canonical["valid_from"], canonical["valid_to"]):
        classes.append("same_entity_revised_time_interval")
    if candidate["feature_type"] != canonical["feature_type"]:
        classes.append("same_entity_revised_type")
    if candidate["name"] != canonical["name_zh_hans"]:
        classes.append("same_entity_revised_name")
    if not classes:
        classes.append("exact_id_unchanged")
    return {
        "candidate_id": candidate["candidate_id"],
        "canonical_id": canonical["tgaz_id"],
        "classification": classes,
        "coordinate_difference_m": round(distance_m, 3),
    }


def generate_entity_parity() -> dict[str, Any]:
    canonical_records = _load_canonical()
    canonical = {record["tgaz_id"]: record for record in canonical_records}
    candidate_layers = {
        layer: _shapefile_records(V6_PATHS[layer], layer)
        for layer in ("time_county", "time_prefecture", "town_1820", "town_1911", "province_1820", "province_1911")
    }
    all_candidates = [record for records in candidate_layers.values() for record in records]
    candidates = [record for record in all_candidates if record["lon"] is not None and record["lat"] is not None]
    id_counts = Counter(record["candidate_id"] for record in candidates)
    comparisons = [(record, _compare(record, canonical.get(record["candidate_id"]))) for record in candidates]
    class_counts = Counter(
        classification
        for _, comparison in comparisons
        for classification in comparison["classification"]
    )
    exact_distances = sorted(
        float(comparison["coordinate_difference_m"])
        for _, comparison in comparisons
        if comparison.get("canonical_id")
    )
    per_layer: dict[str, Any] = {}
    for layer, records in candidate_layers.items():
        valid = [record for record in records if record["lon"] is not None and record["lat"] is not None]
        layer_comparisons = [_compare(record, canonical.get(record["candidate_id"])) for record in valid]
        layer_classes = Counter(
            classification
            for comparison in layer_comparisons
            for classification in comparison["classification"]
        )
        per_layer[layer] = {
            "rows": len(records),
            "valid_coordinate_rows": len(valid),
            "unique_ids": len({record["candidate_id"] for record in records}),
            "exact_id_matches": sum(1 for comparison in layer_comparisons if comparison.get("canonical_id")),
            "candidate_ids_absent_from_canonical": layer_classes["uncertain_match"],
            "classification_counts": dict(sorted(layer_classes.items())),
        }

    def percentile(values: list[float], fraction: float) -> float | None:
        if not values:
            return None
        return round(values[min(len(values) - 1, int((len(values) - 1) * fraction))], 3)

    anchor_samples: dict[str, Any] = {}
    for anchor_id, (name, lon, lat) in ANCHORS.items():
        nearby = sorted(
            ((haversine_km(lon, lat, row["lon"], row["lat"]), row) for row in candidates),
            key=lambda item: (item[0], item[1]["candidate_id"]),
        )[:5]
        anchor_samples[anchor_id] = {
            "display_name": name,
            "coordinate": [lon, lat],
            "records": [
                {
                    "distance_km": round(distance, 3),
                    "candidate": row,
                    "canonical": canonical.get(row["candidate_id"]),
                    "parity": _compare(row, canonical.get(row["candidate_id"])),
                }
                for distance, row in nearby
            ],
        }

    far_candidates = [
        row for row in candidates
        if min(haversine_km(lon, lat, row["lon"], row["lat"]) for _, lon, lat in ANCHORS.values()) > 150
    ]
    random_samples = random.Random(1401).sample(far_candidates, 10)
    return {
        "phase": "1.4",
        "generated_at_utc": utc_now(),
        "identity_policy": (
            "Exact shared CHGIS SYS_ID is the only automatic entity link. Names and coordinates are compared only after ID equality; "
            "candidate-only IDs remain uncertain and are not promoted to lineage or same-entity matches."
        ),
        "v6_layer_counts": {layer: len(records) for layer, records in candidate_layers.items()},
        "per_layer": per_layer,
        "summary": {
            "candidate_rows": len(candidates),
            "candidate_rows_with_invalid_coordinate": len(all_candidates) - len(candidates),
            "candidate_unique_ids": len(id_counts),
            "possible_duplicate_candidate_ids": sum(1 for count in id_counts.values() if count > 1),
            "exact_id_matches": sum(1 for _, comparison in comparisons if comparison.get("canonical_id")),
            "candidate_ids_absent_from_canonical": class_counts["uncertain_match"],
            "genuinely_new_record_confirmed": 0,
            "id_changed_confirmed": 0,
            "classification_counts": dict(sorted(class_counts.items())),
            "coordinate_difference_m": {
                "median": percentile(exact_distances, 0.5),
                "p90": percentile(exact_distances, 0.9),
                "p99": percentile(exact_distances, 0.99),
                "max": round(exact_distances[-1], 3) if exact_distances else None,
            },
        },
        "duplicate_candidate_ids": [
            {
                "candidate_id": candidate_id,
                "rows": [record for record in all_candidates if record["candidate_id"] == candidate_id],
                "classification": "possible_duplicate",
            }
            for candidate_id, count in sorted(id_counts.items())
            if count > 1
        ],
        "candidate_only_id_sample": [
            record for record in candidates
            if record["candidate_id"] not in canonical
        ][:50],
        "five_anchor_samples": anchor_samples,
        "random_non_anchor_samples": [
            {
                "candidate": row,
                "canonical": canonical.get(row["candidate_id"]),
                "parity": _compare(row, canonical.get(row["candidate_id"])),
            }
            for row in random_samples
        ],
        "hartwell_parity": {
            "status": "schema_level_only",
            "classification": "uncertain_match",
            "reason": (
                "Hartwell uses hierarchical IDs and projected polygon approximations rather than CHGIS TGAZ IDs/point assertions. "
                "No name+nearest or polygon-centroid same-entity inference was performed."
            ),
            "schema": {
                "id": "CODE hierarchical dynasty/admin code",
                "geometry": "polygon; Gauss Kruger Xian 1980 Zone 19",
                "time": "static snapshot encoded in layer filename",
                "parent": "hierarchical code fields",
            },
        },
    }


def _request(client: httpx.Client, url: str, *, method: str = "GET", params: Mapping[str, Any] | None = None) -> tuple[httpx.Response, dict[str, Any]]:
    response = client.request(method, url, params=params)
    final = urlsplit(str(response.url))
    return response, {
        "requested_url": url,
        "final_url": urlunsplit((final.scheme, final.netloc, final.path, "", "")),
        "status_code": response.status_code,
        "content_type": response.headers.get("content-type"),
        "content_length_bytes": len(response.content) if method != "HEAD" else int(response.headers.get("content-length", 0) or 0),
    }


def probe_access() -> dict[str, Any]:
    with httpx.Client(timeout=60, follow_redirects=True, headers={"User-Agent": "ChronoChina-Phase1.4/1.0"}) as client:
        cbdb_manifest_response, cbdb_manifest_probe = _request(
            client, "https://raw.githubusercontent.com/cbdb-project/cbdb_sqlite/master/latest.json"
        )
        cbdb_manifest = cbdb_manifest_response.json()
        _, cbdb_archive_probe = _request(client, cbdb_manifest["huggingface_url"], method="HEAD")
        whg_response, whg_probe = _request(client, "https://whgazetteer.org/api/datasets/")
        whg_catalog = whg_response.json()
        whg_china = [
            item for item in whg_catalog.get("features", [])
            if any(term in json.dumps(item, ensure_ascii=False).lower() for term in ("china", "chinese", "qing", "ming", "tang"))
        ]
        _, whg_detail_probe = _request(client, "https://whgazetteer.org/entity/dataset:1209/api")
        _, ccts_probe = _request(client, "https://ccts.sinica.edu.tw/")
        ccts_agreement, ccts_agreement_probe = _request(client, "https://ccts.sinica.edu.tw/download/CCTS_user_agreement.pdf")
        tgaz_chgis_response, tgaz_chgis_probe = _request(
            client,
            "https://tgaz.fudan.edu.cn/tgaz/placename",
            params={"fmt": "json", "src": "CHGIS", "n": "北京"},
        )
        tgaz_ras_response, tgaz_ras_probe = _request(
            client,
            "https://tgaz.fudan.edu.cn/tgaz/placename",
            params={"fmt": "json", "src": "RAS", "n": "Вятское"},
        )
        tgaz_hgr_response, tgaz_hgr_probe = _request(
            client,
            "https://tgaz.fudan.edu.cn/tgaz/placename",
            params={"fmt": "json", "src": "HGR", "n": "Вятское"},
        )
        tgaz_chgis = tgaz_chgis_response.json()
        tgaz_ras = tgaz_ras_response.json()
        tgaz_hgr = tgaz_hgr_response.json()

    local_artifacts = [artifact(path) for path in V6_PATHS.values()]
    v6_counts = {layer: len(_shapefile_records(path, layer)) for layer, path in V6_PATHS.items()}
    v4 = _v4_summary()
    hartwell_zip = RAW_ROOT / "hartwell_v5.zip"
    payload = {
        "phase": "1.4",
        "probed_at_utc": utc_now(),
        "decision_rule": "Actual HTTP/API access or a local downloaded artifact is required; conflicting licenses use the stricter interpretation.",
        "sources": [
            {
                "name": "CHGIS V6",
                "institution": "Harvard Fairbank Center and Fudan Center for Historical Geography",
                "official_entry": "https://dataverse.harvard.edu/dataverse/chgis_v6",
                "access_method": "Harvard Dataverse official API; anonymous metadata and file download",
                "programmatic": True,
                "account_or_token": False,
                "formats": ["zipped ESRI Shapefile", "README/EULA text"],
                "time_and_feature_scope": {
                    "time_series": ["county points", "prefecture points/polygons"],
                    "time_slices": ["1820 towns/provinces", "1911 towns/provinces"],
                    "supplement": ["Ming courier stations; no per-record BEG/END"],
                },
                "record_counts": v6_counts,
                "license": "Package README/EULA: non-commercial academic/educational use; no resale or redistribution; commercial license required.",
                "license_conflict": "Dataverse metadata exposes CC0 while distributed README/EULA is stricter; this audit applies the package terms.",
                "private_research_demo": "available_with_conditions",
                "public_free_app": "permission_required",
                "commercial_app": "separate_commercial_license_required",
                "redistribution": "prohibited_without_permission",
                "attribution": "CHGIS Version 6 citation required",
                "access_result": "success",
                "artifacts": local_artifacts,
            },
            {
                "name": "Fudan CHGIS V4 direct downloads",
                "institution": "Fudan Center for Historical Geography",
                "official_entry": "https://yugong.fudan.edu.cn/CHGIS/sjxz.htm",
                "access_method": "Official direct .rar links; anonymous",
                "programmatic": True,
                "account_or_token": False,
                "formats": ["MapInfo TAB/DAT/MAP/ID"],
                "time_and_feature_scope": {
                    "time_series": ["province", "prefecture", "county"],
                    "time_slices": ["1820 towns", "1911 towns"],
                },
                "record_counts": {key: value["record_count"] for key, value in v4.items()},
                "license": "Non-commercial academic/educational use; PRC users need Fudan permission; full electronic redistribution requires written permission.",
                "private_research_demo": "available_with_conditions",
                "public_free_app": "permission_required",
                "commercial_app": "separate_commercial_agreement_required",
                "redistribution": "prohibited_without_written_permission",
                "access_result": "success",
                "artifacts": [value["artifact"] for value in v4.values()],
            },
            {
                "name": "TGAZ current API collections",
                "institution": "Fudan/Harvard CHGIS",
                "official_entry": "https://tgaz.fudan.edu.cn/tgaz/indexAPI.html",
                "access_method": "Read-only faceted/canonical REST API",
                "programmatic": True,
                "account_or_token": False,
                "formats": ["JSON", "XML", "RDF", "HTML"],
                "time_range": [-222, 1911],
                "collections": ["CHGIS", "HGR"],
                "observed_doc_mismatch": "Documentation names RAS; actual src=RAS returned 0 for its own example while src=HGR returned the record.",
                "probe_results": {
                    "chgis": {**tgaz_chgis_probe, "total_results": int(tgaz_chgis["count of total results"])},
                    "ras": {**tgaz_ras_probe, "total_results": int(tgaz_ras["count of total results"])},
                    "hgr": {**tgaz_hgr_probe, "total_results": int(tgaz_hgr["count of total results"])},
                },
                "coverage_assessment": "CHGIS is the canonical lineage already in use; HGR covers historical Russia, not missing Chinese settlements.",
                "license": "Per-record detail exposes source-specific license; HGR sample reports CC BY-NC 4.0.",
                "redistribution": "source-specific and not established for bulk",
                "access_result": "success_but_not_an_independent_china_coverage_source",
            },
            {
                "name": "Hartwell China Historical GIS",
                "institution": "Harvard Fairbank Center / CHGIS",
                "official_entry": "https://doi.org/10.7910/DVN/29302",
                "access_method": "Harvard Dataverse official API and anonymous zip download",
                "programmatic": True,
                "account_or_token": False,
                "formats": ["ESRI Shapefile polygons", "one 1990 reference point layer"],
                "time_scope": [741, 1080, 1200, 1290, 1391],
                "record_count_note": "See high_admin_coverage_by_year.json; regional/all-China layers overlap and are reported with CODE de-duplication.",
                "license": "Archive README: CC BY-NC-SA 3 / non-commercial academic use and CHGIS EULA.",
                "license_conflict": "Dataverse metadata says CC0; archive README is stricter and controls this assessment.",
                "private_research_demo": "available_with_conditions",
                "public_free_app": "permission_required",
                "commercial_app": "not_permitted_by_archive_terms",
                "redistribution": "share-alike/non-commercial terms and CHGIS EULA apply",
                "access_result": "success",
                "artifact": artifact(hartwell_zip),
            },
            {
                "name": "China Biographical Database (CBDB)",
                "institution": "CBDB academic consortium",
                "official_entry": "https://cbdb.hsites.harvard.edu/download-cbdb-standalone-database",
                "access_method": "Public GitHub manifest plus anonymous Hugging Face SQLite archive",
                "programmatic": True,
                "account_or_token": False,
                "formats": ["SQLite3 zip", "Microsoft Access"],
                "record_scope": "Biographical database; address codes derive substantially from CHGIS and are not a complete settlement gazetteer.",
                "license": "CC BY-NC-SA 4.0 academic branch; separate/exclusive commercial terms apply.",
                "private_research_demo": "available_with_conditions",
                "public_free_app": "non-commercial_share-alike_only",
                "commercial_app": "not_usable_without_commercial_license",
                "redistribution": "share-alike and attribution required",
                "access_result": "manifest_get_and_archive_head_success",
                "manifest": cbdb_manifest,
                "probes": {"manifest": cbdb_manifest_probe, "archive": cbdb_archive_probe},
            },
            {
                "name": "World Historical Gazetteer (WHG)",
                "institution": "World History Center, University of Pittsburgh",
                "official_entry": "https://whgazetteer.org/public_data/",
                "access_method": "Public dataset catalog API; entity detail API requires token",
                "programmatic": True,
                "account_or_token": "catalog_no; entity/download_yes",
                "formats": ["Linked Places JSON/GeoJSON", "dataset catalog JSON"],
                "catalog_count": int(whg_catalog.get("count", 0)),
                "china_related_catalog_entries": whg_china,
                "coverage_assessment": "Mainland China administrative entries are CHGIS 1911 derivatives; no cross-era settlement source found.",
                "license": "WHG public datasets are advertised as CC BY 4.0; underlying source provenance still requires review.",
                "private_research_demo": "available_with_conditions",
                "public_free_app": "dataset_specific",
                "commercial_app": "dataset_specific",
                "redistribution": "dataset_specific_attribution",
                "access_result": "catalog_success_entity_detail_auth_required",
                "probes": {"catalog": whg_probe, "entity_detail": whg_detail_probe},
            },
            {
                "name": "Chinese Civilization in Time and Space (CCTS)",
                "institution": "Academia Sinica",
                "official_entry": "https://ccts.sinica.edu.tw/",
                "access_method": "Legacy WebGIS/WMTS; full system requires account/application",
                "programmatic": "No public bulk API or anonymous record-level download verified",
                "account_or_token": True,
                "formats": ["GIS data under application", "WebGIS/WMTS", "documentation PDF"],
                "time_scope": "Ancient through Qing; system literature reports inhabited-locality content.",
                "license": "Non-transferable limited use; no redistribution/disclosure without prior consent; non-profit raster outputs only.",
                "private_research_demo": "application_required",
                "public_free_app": "not_permitted_without_separate_permission",
                "commercial_app": "not_permitted_by_published_terms",
                "redistribution": "prohibited_without_prior_consent",
                "access_result": "landing_and_license_success_data_access_blocked_by_account_and_terms",
                "probes": {
                    "landing": ccts_probe,
                    "agreement": {**ccts_agreement_probe, "sha256": hashlib.sha256(ccts_agreement.content).hexdigest()},
                },
            },
        ],
    }
    write_json(QA_ROOT / "source_access_catalog.json", payload)
    return payload


def generate() -> None:
    QA_ROOT.mkdir(parents=True, exist_ok=True)
    settlement, high = generate_coverage()
    parity = generate_entity_parity()
    write_json(QA_ROOT / "settlement_coverage_by_year.json", settlement)
    write_json(QA_ROOT / "high_admin_coverage_by_year.json", high)
    write_json(QA_ROOT / "entity_parity.json", parity)
    print(json.dumps({
        "settlement_years": len(settlement["by_year"]),
        "high_admin_years": len(high["by_year"]),
        "v6_candidate_rows": parity["summary"]["candidate_rows"],
        "v6_exact_id_matches": parity["summary"]["exact_id_matches"],
    }))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("probe", "generate", "all"))
    args = parser.parse_args()
    if args.action in {"probe", "all"}:
        probe_access()
    if args.action in {"generate", "all"}:
        generate()


if __name__ == "__main__":
    main()
