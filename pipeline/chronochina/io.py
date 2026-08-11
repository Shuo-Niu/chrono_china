from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx


USER_AGENT = "ChronoChina-Phase0/0.1 (private non-commercial data POC)"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def download_file(
    url: str,
    destination: Path,
    *,
    timeout_seconds: float = 120.0,
) -> dict[str, Any]:
    """Download once without overwriting an existing raw artifact."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        created_at = datetime.fromtimestamp(
            destination.stat().st_ctime, timezone.utc
        ).isoformat(timespec="seconds").replace("+00:00", "Z")
        return {
            "source_url": url,
            "path": str(destination),
            "retrieved_at": created_at,
            "retrieval_time_basis": "existing_raw_filesystem_creation_time",
            "sha256": sha256_file(destination),
            "bytes": destination.stat().st_size,
            "cache_status": "existing_raw",
        }

    temporary = destination.with_name(f"{destination.name}.part")
    try:
        with httpx.Client(
            follow_redirects=True,
            timeout=timeout_seconds,
            headers={"User-Agent": USER_AGENT},
        ) as client:
            with client.stream("GET", url) as response:
                response.raise_for_status()
                with temporary.open("wb") as stream:
                    for chunk in response.iter_bytes(1024 * 1024):
                        stream.write(chunk)
        os.replace(temporary, destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise

    return {
        "source_url": url,
        "path": str(destination),
        "retrieved_at": utc_now(),
        "retrieval_time_basis": "http_download_completion_time",
        "sha256": sha256_file(destination),
        "bytes": destination.stat().st_size,
        "cache_status": "downloaded",
    }
