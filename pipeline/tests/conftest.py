from __future__ import annotations

import shutil
from pathlib import Path
from uuid import uuid4


_MANAGED_TEMP: Path | None = None


def pytest_configure(config) -> None:
    """Avoid reusing Windows temp folders created by a different sandbox identity."""
    global _MANAGED_TEMP
    if config.option.basetemp is not None:
        return
    project_root = Path(__file__).resolve().parents[2]
    _MANAGED_TEMP = project_root / f".pytest_tmp_{uuid4().hex}"
    config.option.basetemp = str(_MANAGED_TEMP)


def pytest_sessionfinish() -> None:
    if _MANAGED_TEMP is not None and _MANAGED_TEMP.exists():
        shutil.rmtree(_MANAGED_TEMP, ignore_errors=True)
