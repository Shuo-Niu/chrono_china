from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from .build import G4_REPORT_PATH
from .config import PROJECT_ROOT, QA_DIR
from .io import read_json, utc_now, write_json


G4_WEB_REPORT_PATH = QA_DIR / "g4_web_verification.json"


def _latest_mtime(paths: list[Path]) -> float:
    return max(path.stat().st_mtime for path in paths if path.exists())


def finalize_g4() -> dict[str, Any]:
    web_dir = PROJECT_ROOT / "web"
    vitest_path = PROJECT_ROOT / "artifacts" / "vitest-results.xml"
    playwright_path = PROJECT_ROOT / "artifacts" / "playwright-results.json"
    build_path = web_dir / "dist" / "index.html"
    required = (vitest_path, playwright_path, build_path, G4_REPORT_PATH)
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise RuntimeError(f"G4 verification artifacts missing: {missing}")

    vitest = ET.parse(vitest_path).getroot()
    vitest_summary = {
        "tests": int(vitest.attrib.get("tests", 0)),
        "failures": int(vitest.attrib.get("failures", 0)),
        "errors": int(vitest.attrib.get("errors", 0)),
    }
    playwright = read_json(playwright_path)
    playwright_summary = {
        key: playwright["stats"].get(key, 0)
        for key in ("expected", "unexpected", "flaky", "skipped", "duration")
    }
    source_paths = list((web_dir / "src").rglob("*")) + list((web_dir / "tests").rglob("*"))
    source_paths.extend(
        [
            web_dir / "package.json",
            web_dir / "package-lock.json",
            web_dir / "vite.config.ts",
            web_dir / "playwright.config.ts",
            PROJECT_ROOT / "data" / "processed" / "anchors" / "beijing" / "manifest.json",
        ]
    )
    source_paths = [path for path in source_paths if path.is_file()]
    latest_source_mtime = _latest_mtime(source_paths)
    freshness = {
        "production_build": build_path.stat().st_mtime >= latest_source_mtime,
        "vitest": vitest_path.stat().st_mtime >= latest_source_mtime,
        "playwright": playwright_path.stat().st_mtime >= latest_source_mtime,
    }
    g4_data = read_json(G4_REPORT_PATH)
    checks = {
        "data_ready": g4_data["status"] in ("DATA_READY", "PASS") and g4_data["feature_count"] > 0,
        "all_details_present": g4_data["feature_count"] == g4_data["detail_count"],
        "all_sources_traceable": g4_data["source_traceable_count"] == g4_data["feature_count"],
        "identity_safe": not g4_data["identity_violations"],
        "vitest_passed": vitest_summary["tests"] > 0
        and vitest_summary["failures"] == 0
        and vitest_summary["errors"] == 0,
        "playwright_passed": playwright_summary["expected"] > 0
        and playwright_summary["unexpected"] == 0
        and playwright_summary["flaky"] == 0,
        "evidence_fresh": all(freshness.values()),
    }
    status = "PASS" if all(checks.values()) else "FAIL"
    report = {
        "gate": "G4",
        "status": status,
        "verified_at": utc_now(),
        "checks": checks,
        "freshness": freshness,
        "vitest": vitest_summary,
        "playwright": playwright_summary,
        "production_build": str(build_path),
        "e2e_flow": "open app -> search Beijing -> select 1911 -> real point -> detail card with source/license",
    }
    write_json(G4_WEB_REPORT_PATH, report)
    if status == "PASS":
        g4_data["status"] = "PASS"
        g4_data["remaining_for_pass"] = None
        g4_data["web_verification_path"] = str(G4_WEB_REPORT_PATH)
        write_json(G4_REPORT_PATH, g4_data)
    else:
        raise RuntimeError(f"G4 web verification failed: {checks}")
    return report
