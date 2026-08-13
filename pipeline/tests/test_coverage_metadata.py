from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from chronochina.io import sha256_file
from chronochina.qa.coverage_metadata import (
    build_coverage_metadata,
    derive_canonical_identity,
    generate,
    load_compact_index,
    validate_coverage_metadata,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
COMPACT_PATH = REPO_ROOT / "data/processed/explore/tgaz_compact.json"


def write_compact(path: Path, records: list[list[object]]) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "fields": [
                    "tgaz_id",
                    "name",
                    "name_pinyin",
                    "valid_from",
                    "valid_to",
                    "lon",
                    "lat",
                    "feature_type",
                ],
                "records": records,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_real_frozen_index_derives_identity_without_documentation_clipping() -> None:
    metadata = build_coverage_metadata(COMPACT_PATH)

    assert metadata["canonical_index"] == {
        "path": "data/processed/explore/tgaz_compact.json",
        "bytes": COMPACT_PATH.stat().st_size,
        "record_count": 71_393,
        "sha256": "7c9ccaedfd58445595e5ab68fd1fb9e106e33c37b8bb98002a7e8e6bad5b5baf",
        "observed_envelope": {"min_year": -763, "max_year": 1912},
    }
    assert metadata["provenance"]["tgaz_documentation_envelope"] == {
        "min_year": -222,
        "max_year": 1911,
        "role": "provenance_note_only",
    }


def test_settlement_components_preserve_snapshot_and_interval_models() -> None:
    metadata = build_coverage_metadata(COMPACT_PATH)
    components = {
        item["id"]: item for item in metadata["families"]["settlement"]["components"]
    }

    assert {
        key: components["raw_town_snapshots"][key]
        for key in (
            "id",
            "raw_types",
            "temporal_model",
            "support",
            "snapshot_years",
            "snapshot_record_counts",
        )
    } == {
        "id": "raw_town_snapshots",
        "raw_types": ["村镇"],
        "temporal_model": "TIME_SLICE",
        "support": "SUPPORTED",
        "snapshot_years": [1820, 1911],
        "snapshot_record_counts": {"1820": 8659, "1911": 40031},
    }
    assert {
        key: components["raw_pavilion_intervals"][key]
        for key in (
            "id",
            "raw_types",
            "temporal_model",
            "support",
            "supported_periods",
            "period_record_counts",
        )
    } == {
        "id": "raw_pavilion_intervals",
        "raw_types": ["亭"],
        "temporal_model": "TIME_SERIES",
        "support": "UNKNOWN",
        "supported_periods": [[14, 22], [623, 959]],
        "period_record_counts": {"14..22": 17, "623..959": 1},
    }


def test_high_admin_preserves_all_raw_types_without_sparse_period_claims() -> None:
    metadata = build_coverage_metadata(COMPACT_PATH)
    high_admin = metadata["families"]["high_admin"]

    assert high_admin["default_support"] == "LIMITED"
    assert {item["raw_types"][0] for item in high_admin["components"]} == {
        "王畿",
        "省",
        "行省",
        "省级",
    }
    assert all(item["temporal_model"] == "TIME_SERIES" for item in high_admin["components"])
    assert "sparse_periods" not in high_admin
    assert all("supported_periods" not in item for item in high_admin["components"])
    assert all("observed_periods" in item for item in high_admin["components"])


def test_metadata_includes_conservative_component_evidence_and_mode_copy() -> None:
    metadata = build_coverage_metadata(COMPACT_PATH)
    pavilion = metadata["families"]["settlement"]["components"][1]

    assert pavilion["supported_periods"] == [[14, 22], [623, 959]]
    assert pavilion["evidence_strength"] == "APPROVED_SOURCE_EVIDENCE"
    assert pavilion["provenance"]["basis"] == "approved_phase_1_4_1_source_audit"
    assert "source_evidence" in pavilion
    for family_id, family in metadata["families"].items():
        if family_id != "polity":
            assert family["user_mode_copy"]
        assert "developer_mode_explanation" in family
        for component in family["components"]:
            assert {"provenance", "source_evidence", "evidence_strength"} <= component.keys()
            if component["id"] != "raw_pavilion_intervals":
                assert "supported_periods" not in component
            if (
                component["temporal_model"] == "TIME_SERIES"
                and component["id"] != "raw_pavilion_intervals"
            ):
                assert "observed_periods" in component


def test_polity_is_developer_mode_only_and_has_no_user_mode_copy() -> None:
    polity = build_coverage_metadata(COMPACT_PATH)["families"]["polity"]

    assert "user_mode_copy" not in polity
    assert polity["developer_mode_explanation"]


def test_generate_rejects_a_compact_index_outside_the_approved_freeze(tmp_path: Path) -> None:
    compact = tmp_path / "data/processed/explore/tgaz_compact.json"
    compact.parent.mkdir(parents=True)
    payload = json.loads(COMPACT_PATH.read_text(encoding="utf-8"))
    payload["records"][0][1] = "changed only to prove explicit refreeze is required"
    compact.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="approved frozen SHA-256"):
        generate(tmp_path)


def test_metadata_generation_does_not_modify_frozen_index(tmp_path: Path) -> None:
    compact = tmp_path / "tgaz_compact.json"
    compact.write_bytes(COMPACT_PATH.read_bytes())
    before = sha256_file(compact)

    build_coverage_metadata(compact)

    assert sha256_file(compact) == before


def test_load_compact_index_rejects_malformed_tuple_schema(tmp_path: Path) -> None:
    compact = tmp_path / "malformed.json"
    write_compact(compact, [["hvd_1", "name", "pinyin", 1, 2, 1.0, 2.0]])

    with pytest.raises(ValueError, match="does not match declared fields"):
        load_compact_index(compact)


@pytest.mark.parametrize("year", [1.5, "1820", True])
def test_identity_rejects_non_integer_validity_years(tmp_path: Path, year: object) -> None:
    compact = tmp_path / "malformed-year.json"
    write_compact(
        compact,
        [["hvd_1", "name", "pinyin", year, 2, 1.0, 2.0, "村镇"]],
    )

    with pytest.raises(ValueError, match="must be integers"):
        derive_canonical_identity(compact, load_compact_index(compact))


def test_build_rejects_unaccounted_settlement_raw_type(tmp_path: Path) -> None:
    compact = tmp_path / "unexpected-settlement.json"
    write_compact(
        compact,
        [["hvd_1", "name", "pinyin", 1, 2, 1.0, 2.0, "村镇"]],
    )

    with pytest.raises(ValueError, match="Settlement source types do not match"):
        build_coverage_metadata(compact)


def test_validator_rejects_metadata_identity_mismatches() -> None:
    metadata = build_coverage_metadata(COMPACT_PATH)
    wrong_sha = deepcopy(metadata)
    wrong_sha["canonical_index"]["sha256"] = "0" * 64
    wrong_envelope = deepcopy(metadata)
    wrong_envelope["canonical_index"]["observed_envelope"] = {
        "min_year": -222,
        "max_year": 1911,
    }

    with pytest.raises(ValueError, match="SHA-256"):
        validate_coverage_metadata(wrong_sha, COMPACT_PATH)
    with pytest.raises(ValueError, match="envelope"):
        validate_coverage_metadata(wrong_envelope, COMPACT_PATH)
