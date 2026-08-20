from __future__ import annotations

from pathlib import Path, PurePosixPath
import argparse

from chronochina.io import sha256_file, utc_now, write_json


RUNTIME_ASSET_ALLOWLIST = (
    "coverage/historical_layer_coverage.json",
    "explore/tgaz_compact.json",
)

FORBIDDEN_SEGMENTS = {
    ".git",
    ".codex-remote-attachments",
    "credentials.json",
    "docs",
    "intermediate",
    "qa",
    "raw",
    "screenshots",
    "source_upgrade",
    "test-results",
}


def _entry(path: Path, root: Path, purpose: str) -> dict[str, object]:
    return {
        "path": path.relative_to(root).as_posix(),
        "size": path.stat().st_size,
        "sha256": sha256_file(path),
        "purpose": purpose,
    }


def _has_forbidden_segment(relative: PurePosixPath) -> bool:
    lowered = {part.lower() for part in relative.parts}
    return bool(lowered & FORBIDDEN_SEGMENTS) or relative.suffix.lower() in {
        ".rar",
        ".shp",
        ".sqlite",
        ".zip",
    }


def build_package_manifest(release_root: Path, staging_root: Path) -> dict[str, object]:
    runtime_assets: list[dict[str, object]] = []
    for path in sorted(item for item in staging_root.rglob("*") if item.is_file()):
        relative = PurePosixPath(path.relative_to(staging_root).as_posix())
        if _has_forbidden_segment(relative):
            raise ValueError(f"forbidden packaged path: {relative}")
        if relative.parts[0] not in {"assets"} and relative.as_posix() not in {
            "index.html",
            *RUNTIME_ASSET_ALLOWLIST,
        }:
            raise ValueError(f"runtime asset is not allowlisted: {relative}")
        purpose = (
            "historical runtime data"
            if relative.as_posix() in RUNTIME_ASSET_ALLOWLIST
            else "compiled application asset"
        )
        runtime_assets.append(_entry(path, staging_root, purpose))

    packaged_files: list[dict[str, object]] = []
    for path in sorted(item for item in release_root.rglob("*") if item.is_file()):
        relative = PurePosixPath(path.relative_to(release_root).as_posix())
        if _has_forbidden_segment(relative):
            raise ValueError(f"forbidden packaged path: {relative}")
        purpose = "packaged runtime dependency"
        if path.name == "README_FIRST.txt":
            purpose = "participant startup instructions"
        elif path.suffix.lower() == ".exe":
            purpose = "Windows executable or distribution artifact"
        elif path.name == "app.asar":
            purpose = "Electron application payload"
        packaged_files.append(_entry(path, release_root, purpose))

    if not runtime_assets:
        raise ValueError("no runtime assets found")
    return {
        "schema_version": "1.0",
        "generated_at": utc_now(),
        "status": "PASS",
        "runtime_data_allowlist": list(RUNTIME_ASSET_ALLOWLIST),
        "runtime_assets": runtime_assets,
        "packaged_files": packaged_files,
    }


def generate_manifest(release_root: Path, staging_root: Path, output: Path) -> dict[str, object]:
    manifest = build_package_manifest(release_root, staging_root)
    write_json(output, manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the Phase 1.5 Windows package")
    parser.add_argument("release_root", type=Path)
    parser.add_argument("staging_root", type=Path)
    parser.add_argument("output", type=Path)
    arguments = parser.parse_args()
    manifest = generate_manifest(
        arguments.release_root,
        arguments.staging_root,
        arguments.output,
    )
    print(
        f"validated {len(manifest['packaged_files'])} packaged files and "
        f"{len(manifest['runtime_assets'])} runtime assets"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
