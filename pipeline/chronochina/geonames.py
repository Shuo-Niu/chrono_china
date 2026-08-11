from __future__ import annotations

import io
import json
import unicodedata
import zipfile
from pathlib import Path
from typing import Any, Iterable

from .config import (
    ANCHOR_SPECS,
    COUNTY_CANDIDATE_SPECS,
    DEFAULT_RADIUS_KM,
    GEONAMES_ADMIN1_PATH,
    GEONAMES_ADMIN1_URL,
    GEONAMES_CN_URL,
    GEONAMES_MANIFEST_PATH,
    GEONAMES_README_PATH,
    GEONAMES_README_URL,
    GEONAMES_ZIP_PATH,
    INTERMEDIATE_DIR,
    NEGATIVE_CONTROL_SPEC,
    QA_DIR,
    RAW_DIR,
)
from .io import download_file, utc_now, write_json


GEONAMES_FIELDS = (
    "geonameid",
    "name",
    "asciiname",
    "alternatenames",
    "latitude",
    "longitude",
    "feature_class",
    "feature_code",
    "country_code",
    "cc2",
    "admin1_code",
    "admin2_code",
    "admin3_code",
    "admin4_code",
    "population",
    "elevation",
    "dem",
    "timezone",
    "modification_date",
)

FEATURE_CODE_PRIORITY = {
    "PPLC": 9,
    "PPLA": 8,
    "PPLA2": 7,
    "PPLA3": 6,
    "PPLA4": 5,
    "PPL": 4,
    "PPLX": 3,
}

ANCHORS_PATH = INTERMEDIATE_DIR / "anchors_candidates.json"
RESOLUTION_REPORT_PATH = QA_DIR / "geonames_resolution_report.json"
RESOLUTION_RAW_DIR = RAW_DIR / "geonames" / "resolution"


class ResolutionError(RuntimeError):
    pass


def fetch_geonames() -> dict[str, Any]:
    try:
        dataset = download_file(GEONAMES_CN_URL, GEONAMES_ZIP_PATH, timeout_seconds=300)
        notice = download_file(GEONAMES_README_URL, GEONAMES_README_PATH)
        admin1_codes = download_file(GEONAMES_ADMIN1_URL, GEONAMES_ADMIN1_PATH)
    except Exception as error:
        write_json(
            QA_DIR / "geonames_fetch_error.json",
            {
                "observed_at": utc_now(),
                "source_url": GEONAMES_CN_URL,
                "error_type": type(error).__name__,
                "error": str(error),
            },
        )
        raise

    license_line = next(
        (
            line.strip()
            for line in GEONAMES_README_PATH.read_text(encoding="utf-8", errors="replace").splitlines()
            if "licensed under" in line.lower()
        ),
        None,
    )
    manifest = {
        "dataset": "GeoNames China country dump",
        "artifact": dataset,
        "source_notice": notice,
        "admin1_codes": admin1_codes,
        "license_notice_from_source": license_line,
        "manifest_generated_at": utc_now(),
    }
    write_json(GEONAMES_MANIFEST_PATH, manifest)
    return manifest


def _normalized(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip().casefold()


def load_admin1_codes() -> dict[str, dict[str, str]]:
    codes = {}
    for line in GEONAMES_ADMIN1_PATH.read_text(encoding="utf-8").splitlines():
        values = line.split("\t")
        if len(values) == 4:
            code, name, ascii_name, geonameid = values
            codes[code] = {
                "code": code,
                "name": name,
                "ascii_name": ascii_name,
                "geonameid": geonameid,
            }
    return codes


def iter_geonames(path: Path = GEONAMES_ZIP_PATH) -> Iterable[dict[str, str]]:
    with zipfile.ZipFile(path) as archive:
        member = next((name for name in archive.namelist() if name.endswith("CN.txt")), None)
        if member is None:
            raise ResolutionError("GeoNames CN.zip does not contain CN.txt")
        with archive.open(member) as binary:
            with io.TextIOWrapper(binary, encoding="utf-8") as text:
                for line in text:
                    values = line.rstrip("\n").split("\t")
                    if len(values) != len(GEONAMES_FIELDS):
                        continue
                    yield dict(zip(GEONAMES_FIELDS, values, strict=True))


def find_exact_candidates(records: Iterable[dict[str, str]], query: str) -> list[dict[str, str]]:
    target = _normalized(query)
    matches = []
    for record in records:
        aliases = [record["name"], record["asciiname"]]
        aliases.extend(record["alternatenames"].split(","))
        if target in {_normalized(alias) for alias in aliases if alias}:
            matches.append(record)
    return matches


def _candidate_sort_key(record: dict[str, str]) -> tuple[int, int, int, int]:
    try:
        population = int(record["population"] or 0)
    except ValueError:
        population = 0
    try:
        geonameid = int(record["geonameid"])
    except ValueError:
        geonameid = 0
    return (
        1 if record["feature_class"] == "P" else 0,
        FEATURE_CODE_PRIORITY.get(record["feature_code"], 0),
        population,
        -geonameid,
    )


def select_candidate(candidates: list[dict[str, str]]) -> dict[str, str]:
    if not candidates:
        raise ResolutionError("GeoNames query returned no exact name/alias candidate")
    return max(candidates, key=_candidate_sort_key)


def resolve_anchor(spec: dict[str, str], manifest: dict[str, Any]) -> dict[str, Any]:
    candidates = find_exact_candidates(iter_geonames(), spec["query"])
    selected = select_candidate(candidates)
    selected_at = utc_now()
    admin1 = load_admin1_codes().get(f"CN.{selected['admin1_code']}")
    raw_resolution = {
        "query": spec["query"],
        "selection_rule": "exact normalized name/alias; populated-place class; feature-code priority; population",
        "candidate_count": len(candidates),
        "selected": selected,
        "candidates": sorted(candidates, key=_candidate_sort_key, reverse=True)[:50],
        "resolved_at": selected_at,
        "dataset_sha256": manifest["artifact"]["sha256"],
    }
    write_json(RESOLUTION_RAW_DIR / f"{spec['anchor_id']}.json", raw_resolution)
    return {
        "anchor_id": spec["anchor_id"],
        "display_name": spec["display_name"],
        "query": spec["query"],
        "modern_location": {
            "lon": float(selected["longitude"]),
            "lat": float(selected["latitude"]),
        },
        "source": {
            "provider": "GeoNames",
            "record_id": selected["geonameid"],
            "record_url": f"https://www.geonames.org/{selected['geonameid']}",
            "dataset_url": GEONAMES_CN_URL,
            "dataset_sha256": manifest["artifact"]["sha256"],
            "retrieved_at": manifest["artifact"]["retrieved_at"],
            "license_notice": manifest["license_notice_from_source"],
        },
        "resolution": {
            "candidate_count": len(candidates),
            "selected_feature_class": selected["feature_class"],
            "selected_feature_code": selected["feature_code"],
            "selected_population": int(selected["population"] or 0),
            "selected_admin1": admin1,
            "resolved_at": selected_at,
        },
        "override_reason": None,
        "default_radius_km": DEFAULT_RADIUS_KM,
        "coverage": {
            "pre_1912": "not_yet_queried",
            "1912_1949": "not_yet_integrated",
            "post_1949": "not_yet_integrated",
        },
    }


def resolve_all_anchor_candidates() -> list[dict[str, Any]]:
    manifest = fetch_geonames()
    specs = (*ANCHOR_SPECS, *COUNTY_CANDIDATE_SPECS, NEGATIVE_CONTROL_SPEC)
    resolved: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    for spec in specs:
        try:
            anchor = resolve_anchor(spec, manifest)
            if spec.get("expected_coverage"):
                anchor["coverage"]["pre_1912"] = spec["expected_coverage"]
            resolved.append(anchor)
        except Exception as error:
            failures.append(
                {
                    "anchor_id": spec["anchor_id"],
                    "query": spec["query"],
                    "error_type": type(error).__name__,
                    "error": str(error),
                }
            )
    write_json(ANCHORS_PATH, resolved)
    report = {
        "resolved_at": utc_now(),
        "requested_count": len(specs),
        "resolved_count": len(resolved),
        "failures": failures,
        "anchors": [
            {
                "anchor_id": anchor["anchor_id"],
                "query": anchor["query"],
                "record_id": anchor["source"]["record_id"],
                "lat": anchor["modern_location"]["lat"],
                "lon": anchor["modern_location"]["lon"],
                "candidate_count": anchor["resolution"]["candidate_count"],
                "override_reason": anchor["override_reason"],
            }
            for anchor in resolved
        ],
        "status": "PASS" if len(resolved) == len(specs) else "FAIL",
    }
    write_json(RESOLUTION_REPORT_PATH, report)
    if failures:
        raise ResolutionError(f"GeoNames failed to resolve {len(failures)} anchors")
    return resolved


def load_anchors(path: Path = ANCHORS_PATH) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))
