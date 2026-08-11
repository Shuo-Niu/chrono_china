from __future__ import annotations

import json
import os
import random
import time
from collections import Counter
from pathlib import Path
from typing import Any

import httpx

from .config import INTERMEDIATE_DIR, QA_DIR, TGAZ_DETAIL_DIR, TGAZ_DETAIL_URL
from .geonames import load_anchors
from .io import USER_AGENT, read_json, sha256_bytes, utc_now, write_json
from .spatial import query_nearby
from .temporal import parse_year
from .tgaz_index import load_normalized_points


DETAIL_MANIFEST_PATH = TGAZ_DETAIL_DIR / "manifest.json"
PARSED_DETAIL_DIR = INTERMEDIATE_DIR / "tgaz_detail"
G2_REPORT_PATH = QA_DIR / "g2_detail_enrichment.json"
G2_ERROR_LOG_PATH = QA_DIR / "tgaz_api_failures.json"
G2_RANDOM_SEED = 20260808


class DetailParseError(RuntimeError):
    pass


def decode_tgaz_json(content: bytes) -> tuple[dict[str, Any], str, str | None]:
    text = content.decode("utf-8-sig")
    try:
        return json.loads(text), "strict", None
    except json.JSONDecodeError as error:
        if "Invalid control character" not in str(error):
            raise
        return json.loads(text, strict=False), "non_strict_control_characters", str(error)


def _first_spelling(payload: dict[str, Any], *, script: str | None = None, transcription: str | None = None) -> str | None:
    for spelling in payload.get("spellings", []):
        if script and spelling.get("script") == script:
            return spelling.get("written form") or None
        if transcription and spelling.get("transcribed in") == transcription:
            return spelling.get("written form") or None
    return None


def _coordinate(value: object, lower: float, upper: float) -> float | None:
    try:
        number = float(str(value))
    except (TypeError, ValueError):
        return None
    return number if lower <= number <= upper else None


def parse_tgaz_detail(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict) or not payload.get("sys_id"):
        raise DetailParseError("TGAZ detail response is missing sys_id")
    feature_type = payload.get("feature_type") or {}
    temporal = payload.get("temporal") or {}
    spatial = payload.get("spatial") or {}
    context = payload.get("historical_context") or {}
    parsed = {
        "tgaz_id": payload["sys_id"],
        "canonical_uri": payload.get("uri"),
        "alternate_id": payload.get("sys_id of alternate") or None,
        "names": {
            "simplified_chinese": _first_spelling(payload, script="simplified Chinese"),
            "traditional_chinese": _first_spelling(payload, script="traditional Chinese"),
            "pinyin": _first_spelling(payload, transcription="Pinyin"),
            "all_spellings": payload.get("spellings", []),
        },
        "feature_type": {
            "name": feature_type.get("name"),
            "alternate_name": feature_type.get("alternate name"),
            "transcription": feature_type.get("transcription"),
            "english": feature_type.get("English"),
        },
        "location": {
            "object_type": spatial.get("object_type"),
            "xy_type": spatial.get("xy_type"),
            "lat": _coordinate(spatial.get("latitude"), -90, 90),
            "lon": _coordinate(spatial.get("longitude"), -180, 180),
            "source": spatial.get("source") or None,
            "present_location": spatial.get("present_location", []),
        },
        "temporal": {
            "valid_from": parse_year(temporal.get("begin")),
            "valid_to": parse_year(temporal.get("end")),
            "begin_rule": temporal.get("begin rule"),
            "end_rule": temporal.get("end rule"),
        },
        "relationships": {
            "part_of": context.get("part of", []),
            "subordinate_units": context.get("subordinate units", []),
            "preceded_by": context.get("preceded by", []),
        },
        "source": {
            "system": payload.get("system"),
            "data_source": payload.get("data source"),
            "source_note": payload.get("source note"),
            "source_uri": payload.get("source uri"),
            "license": payload.get("license"),
        },
    }
    return parsed


def _fetch_one(client: httpx.Client, tgaz_id: str, max_attempts: int = 3) -> tuple[dict[str, Any], dict[str, Any]]:
    raw_path = TGAZ_DETAIL_DIR / f"{tgaz_id}.json"
    metadata_path = TGAZ_DETAIL_DIR / f"{tgaz_id}.meta.json"
    if raw_path.exists() and metadata_path.exists():
        payload, parse_mode, parse_warning = decode_tgaz_json(raw_path.read_bytes())
        stored_metadata = read_json(metadata_path)
        metadata_changed = "json_parse_mode" not in stored_metadata
        stored_metadata.setdefault("json_parse_mode", parse_mode)
        if parse_warning:
            metadata_changed = "json_parse_warning" not in stored_metadata or metadata_changed
            stored_metadata.setdefault("json_parse_warning", parse_warning)
        if metadata_changed:
            write_json(metadata_path, stored_metadata)
        metadata = {**stored_metadata, "cache_status": "existing_raw"}
        return payload, metadata

    url = TGAZ_DETAIL_URL.format(tgaz_id=tgaz_id)
    attempts: list[dict[str, Any]] = []
    for attempt in range(1, max_attempts + 1):
        try:
            response = client.get(url)
            attempts.append(
                {"attempt": attempt, "observed_at": utc_now(), "http_status": response.status_code}
            )
            response.raise_for_status()
            content = response.content
            payload, parse_mode, parse_warning = decode_tgaz_json(content)
            if payload.get("sys_id") != tgaz_id:
                raise DetailParseError(
                    f"requested {tgaz_id}, response sys_id is {payload.get('sys_id')!r}"
                )
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = raw_path.with_name(f"{raw_path.name}.part")
            temporary.write_bytes(content)
            os.replace(temporary, raw_path)
            metadata = {
                "tgaz_id": tgaz_id,
                "source_url": url,
                "canonical_uri": payload.get("uri"),
                "fetched_at": utc_now(),
                "http_status": response.status_code,
                "content_type": response.headers.get("content-type"),
                "content_hash": sha256_bytes(content),
                "bytes": len(content),
                "attempts": attempts,
                "license_from_response": payload.get("license"),
                "data_source_from_response": payload.get("data source"),
                "cache_status": "downloaded",
                "json_parse_mode": parse_mode,
                "json_parse_warning": parse_warning,
            }
            write_json(metadata_path, metadata)
            return payload, metadata
        except Exception as error:
            if not attempts or attempts[-1].get("attempt") != attempt:
                attempts.append({"attempt": attempt, "observed_at": utc_now()})
            attempts[-1].update({"error_type": type(error).__name__, "error": str(error)})
            if attempt < max_attempts:
                time.sleep(0.5 * attempt)
    raise RuntimeError(json.dumps({"tgaz_id": tgaz_id, "attempts": attempts}, ensure_ascii=False))


def _sample_beijing_ids(sample_size: int = 10) -> tuple[list[str], int, float]:
    anchors = load_anchors()
    beijing = next(anchor for anchor in anchors if anchor["anchor_id"] == "beijing")
    points = load_normalized_points()
    year = max(beijing["available_periods"])
    matches = query_nearby(
        points,
        anchor_lat=beijing["modern_location"]["lat"],
        anchor_lon=beijing["modern_location"]["lon"],
        year=year,
        radius_km=beijing["default_radius_km"],
    )
    unique_ids = sorted({row["tgaz_id"] for row in matches})
    if len(unique_ids) < sample_size:
        raise RuntimeError(f"only {len(unique_ids)} unique Beijing candidates; need {sample_size}")
    return random.Random(G2_RANDOM_SEED).sample(unique_ids, sample_size), year, beijing["default_radius_km"]


def run_g2() -> dict[str, Any]:
    sampled_ids, year, radius_km = _sample_beijing_ids()
    successes: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    manifest_records: dict[str, Any] = {}
    with httpx.Client(
        follow_redirects=True,
        timeout=httpx.Timeout(20.0),
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    ) as client:
        for index, tgaz_id in enumerate(sampled_ids):
            try:
                payload, metadata = _fetch_one(client, tgaz_id)
                parsed = parse_tgaz_detail(payload)
                write_json(PARSED_DETAIL_DIR / f"{tgaz_id}.json", parsed)
                field_presence = {
                    "name": bool(parsed["names"]["simplified_chinese"] or parsed["names"]["traditional_chinese"]),
                    "type": bool(parsed["feature_type"]["name"]),
                    "coordinates": parsed["location"]["lat"] is not None and parsed["location"]["lon"] is not None,
                    "temporal": parsed["temporal"]["valid_from"] is not None and parsed["temporal"]["valid_to"] is not None,
                    "relationships": all(key in parsed["relationships"] for key in ("part_of", "subordinate_units", "preceded_by")),
                    "source": bool(parsed["source"]["system"] or parsed["source"]["data_source"]),
                    "source_note_field": "source_note" in parsed["source"],
                    "license": bool(parsed["source"]["license"]),
                    "canonical_uri": bool(parsed["canonical_uri"]),
                }
                successes.append(
                    {"tgaz_id": tgaz_id, "metadata": metadata, "field_presence": field_presence}
                )
                manifest_records[tgaz_id] = metadata
            except Exception as error:
                failures.append(
                    {
                        "tgaz_id": tgaz_id,
                        "observed_at": utc_now(),
                        "error_type": type(error).__name__,
                        "error": str(error),
                    }
                )
            if index < len(sampled_ids) - 1:
                time.sleep(0.4)

    write_json(
        DETAIL_MANIFEST_PATH,
        {"generated_at": utc_now(), "records": manifest_records},
    )
    write_json(G2_ERROR_LOG_PATH, {"generated_at": utc_now(), "failures": failures})
    required_presence = ("name", "type", "coordinates", "temporal", "relationships", "source", "source_note_field", "license", "canonical_uri")
    complete_count = sum(
        all(success["field_presence"][field] for field in required_presence)
        for success in successes
    )
    report = {
        "gate": "G2",
        "status": "PASS" if len(successes) == 10 and complete_count == 10 else "FAIL",
        "verified_at": utc_now(),
        "selection": {
            "anchor_id": "beijing",
            "year": year,
            "radius_km": radius_km,
            "random_seed": G2_RANDOM_SEED,
            "sampled_ids": sampled_ids,
        },
        "requested_count": len(sampled_ids),
        "success_count": len(successes),
        "complete_parse_count": complete_count,
        "failure_count": len(failures),
        "success_rate": len(successes) / len(sampled_ids),
        "field_coverage": {
            field: sum(success["field_presence"][field] for success in successes)
            for field in required_presence
        },
        "license_values": dict(
            Counter(success["metadata"].get("license_from_response") for success in successes)
        ),
        "successes": successes,
        "failures": failures,
    }
    write_json(G2_REPORT_PATH, report)
    if report["status"] != "PASS":
        raise RuntimeError(
            f"G2 failed: {len(successes)}/10 fetched, {complete_count}/10 complete parses"
        )
    return report


def fetch_and_parse_details(
    tgaz_ids: list[str], *, pause_seconds: float = 0.4
) -> dict[str, Any]:
    """Fetch a deterministic low-frequency batch for processed Phase 1 display data."""
    requested_ids = sorted(set(tgaz_ids))
    existing_manifest = (
        read_json(DETAIL_MANIFEST_PATH)
        if DETAIL_MANIFEST_PATH.exists()
        else {"records": {}}
    )
    manifest_records = dict(existing_manifest.get("records", {}))
    details: dict[str, dict[str, Any]] = {}
    metadata_by_id: dict[str, dict[str, Any]] = {}
    failures: list[dict[str, Any]] = []

    with httpx.Client(
        follow_redirects=True,
        timeout=httpx.Timeout(20.0),
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    ) as client:
        for index, tgaz_id in enumerate(requested_ids):
            try:
                payload, metadata = _fetch_one(client, tgaz_id)
                parsed = parse_tgaz_detail(payload)
                write_json(PARSED_DETAIL_DIR / f"{tgaz_id}.json", parsed)
                details[tgaz_id] = parsed
                metadata_by_id[tgaz_id] = metadata
                manifest_records[tgaz_id] = metadata
            except Exception as error:
                failures.append(
                    {
                        "tgaz_id": tgaz_id,
                        "observed_at": utc_now(),
                        "error_type": type(error).__name__,
                        "error": str(error),
                    }
                )
            used_network = bool(failures and failures[-1]["tgaz_id"] == tgaz_id) or (
                metadata_by_id.get(tgaz_id, {}).get("cache_status") == "downloaded"
            )
            if pause_seconds and used_network and index < len(requested_ids) - 1:
                time.sleep(pause_seconds)

    write_json(
        DETAIL_MANIFEST_PATH,
        {"generated_at": utc_now(), "records": manifest_records},
    )
    return {
        "requested_ids": requested_ids,
        "success_count": len(details),
        "failure_count": len(failures),
        "cache_status_counts": dict(
            Counter(metadata.get("cache_status") for metadata in metadata_by_id.values())
        ),
        "details": details,
        "metadata": metadata_by_id,
        "failures": failures,
    }


def load_parsed_detail(tgaz_id: str) -> dict[str, Any] | None:
    path = PARSED_DETAIL_DIR / f"{tgaz_id}.json"
    return read_json(path) if path.exists() else None
