from __future__ import annotations

import json
import random
import unicodedata
import zipfile
from pathlib import Path
from typing import Any

import httpx
import shapefile

from .config import INTERMEDIATE_DIR, QA_DIR, RAW_DIR
from .io import USER_AGENT, download_file, utc_now, write_json
from .spatial import haversine
from .tgaz_index import load_normalized_points


DATAVERSE_BASE = "https://dataverse.harvard.edu"
ROOT_CONTENTS_URL = f"{DATAVERSE_BASE}/api/dataverses/chgis_v6/contents"
TARGET_DATASET_TITLE = "V6 Time Series County Points"
TARGET_FILENAME = "v6_time_cnty_pts_utf_wgs84.zip"
TARGET_README = "CHGIS_V6_README.txt"
V6_RAW_DIR = RAW_DIR / "chgis_v6"
V6_METADATA_DIR = V6_RAW_DIR / "metadata"
V6_EXTRACT_DIR = INTERMEDIATE_DIR / "chgis_v6" / "county_points"
V6_MANIFEST_PATH = V6_RAW_DIR / "manifest.json"
G6_REPORT_PATH = QA_DIR / "g6_v6_parity.json"
PARITY_RANDOM_SEED = 20260808


def _api_json(client: httpx.Client, url: str, **params: Any) -> dict[str, Any]:
    response = client.get(url, params=params or None)
    response.raise_for_status()
    payload = response.json()
    if payload.get("status") != "OK":
        raise RuntimeError(f"Dataverse API status is {payload.get('status')!r} for {url}")
    return payload


def _dataset_title(latest_version: dict[str, Any]) -> str | None:
    for block in latest_version.get("metadataBlocks", {}).values():
        for field in block.get("fields", []):
            if field.get("typeName") == "title":
                return field.get("value")
    return None


def _safe_extract(archive_path: Path, destination: Path) -> list[str]:
    destination.mkdir(parents=True, exist_ok=True)
    extracted = []
    root = destination.resolve()
    with zipfile.ZipFile(archive_path) as archive:
        for member in archive.infolist():
            target = (destination / member.filename).resolve()
            if root not in target.parents and target != root:
                raise RuntimeError(f"unsafe ZIP member path: {member.filename}")
            archive.extract(member, destination)
            extracted.append(member.filename)
    return extracted


def _record_value(record: dict[str, Any], candidates: tuple[str, ...]) -> Any:
    normalized = {key.casefold(): value for key, value in record.items()}
    for candidate in candidates:
        if candidate.casefold() in normalized:
            return normalized[candidate.casefold()]
    return None


def _text(value: object) -> str:
    return unicodedata.normalize("NFKC", str(value or "")).strip()


def _integer(value: object) -> int | None:
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _tgaz_id_hypothesis(chgis_id: object) -> str | None:
    value = _text(chgis_id)
    if not value:
        return None
    return value if value.startswith("hvd_") else f"hvd_{value}"


def run_g6() -> dict[str, Any]:
    try:
        with httpx.Client(
            follow_redirects=True,
            timeout=httpx.Timeout(60.0),
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        ) as client:
            root = _api_json(client, ROOT_CONTENTS_URL)
            write_json(V6_METADATA_DIR / "root_contents.json", root)
            time_series = next(
                item
                for item in root["data"]
                if item.get("type") == "dataverse" and item.get("title") == "V6 Time Series Dataverse"
            )
            child = _api_json(
                client, f"{DATAVERSE_BASE}/api/dataverses/{time_series['id']}/contents"
            )
            write_json(V6_METADATA_DIR / "time_series_contents.json", child)
            target_metadata = None
            target_item = None
            for item in child["data"]:
                if item.get("type") != "dataset":
                    continue
                persistent_id = f"doi:{item['authority']}/{item['identifier']}"
                metadata = _api_json(
                    client,
                    f"{DATAVERSE_BASE}/api/datasets/:persistentId",
                    persistentId=persistent_id,
                )
                write_json(
                    V6_METADATA_DIR / f"dataset_{item['identifier'].split('/')[-1]}.json", metadata
                )
                if _dataset_title(metadata["data"]["latestVersion"]) == TARGET_DATASET_TITLE:
                    target_metadata = metadata
                    target_item = item
            if target_metadata is None or target_item is None:
                raise RuntimeError(f"Dataverse dataset not found: {TARGET_DATASET_TITLE}")
    except Exception as error:
        write_json(
            QA_DIR / "g6_access_error.json",
            {
                "gate": "G6",
                "status": "FAIL",
                "observed_at": utc_now(),
                "error_type": type(error).__name__,
                "error": str(error),
            },
        )
        raise

    latest = target_metadata["data"]["latestVersion"]
    files = latest.get("files", [])
    data_file = next(file for file in files if file["dataFile"]["filename"] == TARGET_FILENAME)
    readme_file = next(file for file in files if file["dataFile"]["filename"] == TARGET_README)
    zip_id = data_file["dataFile"]["id"]
    readme_id = readme_file["dataFile"]["id"]
    zip_path = V6_RAW_DIR / TARGET_FILENAME
    readme_path = V6_RAW_DIR / TARGET_README
    zip_artifact = download_file(
        f"{DATAVERSE_BASE}/api/access/datafile/{zip_id}", zip_path, timeout_seconds=180
    )
    readme_artifact = download_file(
        f"{DATAVERSE_BASE}/api/access/datafile/{readme_id}", readme_path
    )
    extracted = _safe_extract(zip_path, V6_EXTRACT_DIR)
    shapefile_path = next(V6_EXTRACT_DIR.rglob("*.shp"))
    projection_path = next(V6_EXTRACT_DIR.rglob("*.prj"), None)

    reader = shapefile.Reader(str(shapefile_path), encoding="utf-8")
    fields = [field[0] for field in reader.fields[1:]]
    records = []
    geometry_type_counts: dict[str, int] = {}
    for shape_record in reader.iterShapeRecords():
        record = shape_record.record.as_dict()
        shape = shape_record.shape
        shape_type = shapefile.SHAPETYPE_LOOKUP.get(shape.shapeType, str(shape.shapeType))
        geometry_type_counts[shape_type] = geometry_type_counts.get(shape_type, 0) + 1
        if not shape.points:
            continue
        lon, lat = shape.points[0]
        records.append({"attributes": record, "lon": lon, "lat": lat})

    id_candidates = ("CHGIS_ID", "TGAZ_ID", "SYS_ID", "ID")
    name_candidates = ("NAME_SIM", "NAME_CH", "NAME", "NAMESIM")
    begin_candidates = ("BEG", "BEG_YR", "BEG_YEAR", "BEGIN")
    end_candidates = ("END", "END_YR", "END_YEAR")
    type_candidates = ("TYPE_CH", "TYPE_SIM", "FEAT_TYPE", "TYPE", "LEV_TYPE")
    tgaz_by_id = {row["tgaz_id"]: row for row in load_normalized_points()}
    comparable = [
        record
        for record in records
        if _tgaz_id_hypothesis(_record_value(record["attributes"], id_candidates))
    ]
    sample_size = min(100, len(comparable))
    sample = random.Random(PARITY_RANDOM_SEED).sample(comparable, sample_size)
    comparisons = []
    for v6 in sample:
        attributes = v6["attributes"]
        chgis_id = _record_value(attributes, id_candidates)
        hypothesized_tgaz_id = _tgaz_id_hypothesis(chgis_id)
        tgaz = tgaz_by_id.get(hypothesized_tgaz_id or "")
        comparison = {
            "chgis_id": _text(chgis_id),
            "hypothesized_tgaz_id": hypothesized_tgaz_id,
            "tgaz_record_found": tgaz is not None,
            "v6": {
                "name": _text(_record_value(attributes, name_candidates)),
                "valid_from": _integer(_record_value(attributes, begin_candidates)),
                "valid_to": _integer(_record_value(attributes, end_candidates)),
                "feature_type": _text(_record_value(attributes, type_candidates)),
                "lon": v6["lon"],
                "lat": v6["lat"],
            },
        }
        if tgaz:
            comparison["tgaz"] = {
                "name": tgaz["name_zh_hans"],
                "valid_from": tgaz["valid_from"],
                "valid_to": tgaz["valid_to"],
                "feature_type": tgaz["feature_type"],
                "lon": tgaz["lon"],
                "lat": tgaz["lat"],
            }
            comparison["matches"] = {
                "name": comparison["v6"]["name"] == tgaz["name_zh_hans"],
                "valid_from": comparison["v6"]["valid_from"] == tgaz["valid_from"],
                "valid_to": comparison["v6"]["valid_to"] == tgaz["valid_to"],
                "feature_type": comparison["v6"]["feature_type"] == tgaz["feature_type"],
                "coordinate_within_10m": haversine(
                    v6["lat"], v6["lon"], tgaz["lat"], tgaz["lon"]
                )
                <= 0.01,
            }
            comparison["coordinate_distance_m"] = round(
                haversine(v6["lat"], v6["lon"], tgaz["lat"], tgaz["lon"]) * 1000,
                3,
            )
        comparisons.append(comparison)

    matched = [comparison for comparison in comparisons if comparison["tgaz_record_found"]]
    metric_match_counts = {
        metric: sum(comparison["matches"][metric] for comparison in matched)
        for metric in ("name", "valid_from", "valid_to", "feature_type", "coordinate_within_10m")
    }
    dataset_license = latest.get("license")
    readme_text = readme_path.read_text(encoding="utf-8", errors="replace")
    restrictive_license_tokens = ("non-commercial", "no commercial", "no resale", "no redistribution")
    license_conflict = bool(dataset_license) and any(
        token in readme_text.casefold() for token in restrictive_license_tokens
    )
    manifest = {
        "dataset_title": TARGET_DATASET_TITLE,
        "persistent_id": f"doi:{target_item['authority']}/{target_item['identifier']}",
        "dataset_id": target_item["id"],
        "publication_date": target_item.get("publicationDate"),
        "dataset_version": latest.get("versionNumber"),
        "dataset_license_metadata": dataset_license,
        "dataset_terms_of_use": latest.get("termsOfUse"),
        "file": {
            "file_id": zip_id,
            "filename": TARGET_FILENAME,
            "declared_size": data_file["dataFile"].get("filesize"),
            "restricted": data_file.get("restricted"),
            "artifact": zip_artifact,
        },
        "readme": {"file_id": readme_id, "artifact": readme_artifact},
        "license_conflict": license_conflict,
        "license_resolution": "unresolved_conflict; private non-commercial POC follows the more restrictive terms",
        "generated_at": utc_now(),
    }
    write_json(V6_MANIFEST_PATH, manifest)
    parity_equivalent = len(matched) == sample_size and all(
        count == sample_size for count in metric_match_counts.values()
    )
    report = {
        "gate": "G6",
        "status": "COMPLETE" if sample_size >= 50 else "FAIL",
        "capability": "EQUIVALENT" if parity_equivalent else "NOT_EQUIVALENT",
        "verified_at": utc_now(),
        "access": {
            "method": "Harvard Dataverse native API, anonymous",
            "dataset_found": True,
            "file_downloaded": True,
            "restricted": data_file.get("restricted"),
        },
        "dataset": manifest,
        "shapefile": {
            "path": str(shapefile_path),
            "zip_members": extracted,
            "encoding": "utf-8 (reader succeeded)",
            "crs_wkt": projection_path.read_text(encoding="utf-8", errors="replace") if projection_path else None,
            "schema": fields,
            "record_count": len(reader),
            "geometry_record_count": len(records),
            "geometry_type_counts": geometry_type_counts,
        },
        "field_mapping_candidates": {
            "id": id_candidates,
            "name": name_candidates,
            "valid_from": begin_candidates,
            "valid_to": end_candidates,
            "feature_type": type_candidates,
            "coordinate": "Shapefile point geometry",
        },
        "parity": {
            "random_seed": PARITY_RANDOM_SEED,
            "sample_size": sample_size,
            "id_mapping_hypothesis": "numeric CHGIS_ID -> hvd_{CHGIS_ID}; validated here, not assumed by Track A",
            "tgaz_record_found_count": len(matched),
            "metric_match_counts": metric_match_counts,
            "comparisons": comparisons,
            "conclusion": (
                "sampled_full_match"
                if parity_equivalent
                else "sampled_differences_observed; V4/2016 CSV must not be treated as V6-equivalent"
            ),
        },
    }
    write_json(G6_REPORT_PATH, report)
    if report["status"] != "COMPLETE":
        raise RuntimeError(f"G6 parity sample has only {sample_size} comparable records")
    return report
