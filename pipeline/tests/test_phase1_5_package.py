from __future__ import annotations

import json
from pathlib import Path

import pytest

from chronochina.qa.phase1_5_package import (
    RUNTIME_ASSET_ALLOWLIST,
    build_package_manifest,
)


def _write(path: Path, content: bytes = b"fixture") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def test_manifest_accepts_only_declared_runtime_data_and_distribution_files(
    tmp_path: Path,
) -> None:
    release = tmp_path / "release"
    unpacked = release / "win-unpacked"
    _write(unpacked / "ChronoChina.exe")
    _write(unpacked / "resources" / "app.asar")
    _write(release / "ChronoChina-0.1.0-x64-portable.exe")
    _write(release / "README_FIRST.txt", b"start")

    staging = tmp_path / "dist"
    _write(staging / "index.html")
    _write(staging / "assets" / "app.js")
    _write(staging / "explore" / "tgaz_compact.json", b"{}")
    _write(staging / "coverage" / "historical_layer_coverage.json", b"{}")
    _write(staging / "reference" / "china_z9.pmtiles", b"pmtiles")
    _write(staging / "knowledge" / "qing_late_institution_notes_v0.1.json", b"{}")
    _write(staging / "reference" / "assets" / "fonts" / "OFL.txt", b"ofl")
    _write(staging / "reference" / "assets" / "fonts" / "Noto Sans Regular" / "0-255.pbf")
    _write(staging / "reference" / "assets" / "sprites" / "v4" / "light.png")

    manifest = build_package_manifest(release, staging)

    assert manifest["runtime_data_allowlist"] == list(RUNTIME_ASSET_ALLOWLIST)
    assert manifest["status"] == "PASS"
    assert {item["path"] for item in manifest["runtime_assets"]} == {
        "assets/app.js",
        "coverage/historical_layer_coverage.json",
        "explore/tgaz_compact.json",
        "index.html",
        "knowledge/qing_late_institution_notes_v0.1.json",
        "reference/china_z9.pmtiles",
        "reference/assets/fonts/OFL.txt",
        "reference/assets/fonts/Noto Sans Regular/0-255.pbf",
        "reference/assets/sprites/v4/light.png",
    }
    assert all(len(item["sha256"]) == 64 for item in manifest["packaged_files"])


def test_manifest_rejects_installer_artifacts(tmp_path: Path) -> None:
    release = tmp_path / "release"
    staging = tmp_path / "dist"
    _write(release / "ChronoChina-0.1.0-x64-setup.exe")
    _write(staging / "index.html")
    _write(staging / "explore" / "tgaz_compact.json", b"{}")
    _write(staging / "coverage" / "historical_layer_coverage.json", b"{}")

    with pytest.raises(ValueError, match="portable executable"):
        build_package_manifest(release, staging)


@pytest.mark.parametrize(
    "forbidden",
    [
        "raw/chgis.zip",
        "qa/debug.json",
        "screenshots/map.png",
        "docs/design.md",
        ".git/config",
        "source_upgrade/archive.rar",
        "credentials.json",
    ],
)
def test_manifest_rejects_forbidden_packaged_content(
    tmp_path: Path,
    forbidden: str,
) -> None:
    release = tmp_path / "release"
    staging = tmp_path / "dist"
    _write(release / "win-unpacked" / forbidden)
    _write(staging / "index.html")
    _write(staging / "explore" / "tgaz_compact.json", b"{}")
    _write(staging / "coverage" / "historical_layer_coverage.json", b"{}")

    with pytest.raises(ValueError, match="forbidden packaged path"):
        build_package_manifest(release, staging)


def test_manifest_rejects_undeclared_runtime_data(tmp_path: Path) -> None:
    release = tmp_path / "release"
    staging = tmp_path / "dist"
    _write(staging / "index.html")
    _write(staging / "explore" / "tgaz_compact.json", b"{}")
    _write(staging / "coverage" / "historical_layer_coverage.json", b"{}")
    _write(staging / "anchors" / "index.json", b"{}")

    with pytest.raises(ValueError, match="runtime asset is not allowlisted"):
        build_package_manifest(release, staging)
@pytest.mark.parametrize(
    "undeclared_reference",
    [
        "reference/china_z10.pmtiles",
        "reference/assets/fonts/Unknown Font/0-255.pbf",
        "reference/assets/sprites/v4/dark.png",
    ],
)
def test_manifest_rejects_undeclared_reference_assets(
    tmp_path: Path,
    undeclared_reference: str,
) -> None:
    release = tmp_path / "release"
    staging = tmp_path / "dist"
    _write(staging / "index.html")
    _write(staging / "explore" / "tgaz_compact.json", b"{}")
    _write(staging / "coverage" / "historical_layer_coverage.json", b"{}")
    _write(staging / undeclared_reference)

    with pytest.raises(ValueError, match="runtime asset is not allowlisted"):
        build_package_manifest(release, staging)
