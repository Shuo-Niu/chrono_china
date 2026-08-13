import json
import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _quoted_entries(block_name: str, script: str) -> set[str]:
    match = re.search(rf"\${block_name}\s*=\s*@\((.*?)\n\)", script, re.DOTALL)
    assert match is not None
    return set(re.findall(r'"([^"]+)"', match.group(1)))


def test_release_boundary_allows_only_reviewed_aggregate_coverage_metadata() -> None:
    audit = (PROJECT_ROOT / "scripts/release_audit.ps1").read_text(encoding="utf-8-sig")
    allowed = _quoted_entries("AllowedDataFiles", audit)

    assert allowed == {
        "data/README.md",
        "data/raw/.gitkeep",
        "data/intermediate/.gitkeep",
        "data/processed/.gitkeep",
        "data/qa/.gitkeep",
        "data/metadata/historical_layer_coverage.json",
    }

    data_readme = (PROJECT_ROOT / "data/README.md").read_text(encoding="utf-8")
    policy = (PROJECT_ROOT / "docs/data_redistribution_policy.md").read_text(encoding="utf-8")
    for content in (data_readme, policy):
        assert "data/metadata/historical_layer_coverage.json" in content
        assert "record-level" in content


def test_public_tests_exclude_only_new_real_data_dependencies_from_full_suites() -> None:
    public_script = (PROJECT_ROOT / "scripts/test_public.ps1").read_text(encoding="utf-8-sig")
    ignored_python = _quoted_entries("DataDependentTests", public_script)
    assert "pipeline/tests/test_coverage_metadata.py" in ignored_python

    package = json.loads((PROJECT_ROOT / "web/package.json").read_text(encoding="utf-8"))
    public_command = package["scripts"]["test:public"]
    full_command = package["scripts"]["test"]
    assert "--exclude src/coverage/sourceCoverage.test.ts" in public_command
    assert "sourceCoverage.test.ts" not in full_command
