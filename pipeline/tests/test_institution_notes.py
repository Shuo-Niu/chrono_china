from __future__ import annotations

import json

from chronochina.config import PROJECT_ROOT
from chronochina.institution_notes import (
    build_publication_candidate,
    matching_notes,
    validate_institution_notes,
    validate_source_review,
)


DRAFT_PATH = (
    PROJECT_ROOT
    / "data"
    / "knowledge"
    / "drafts"
    / "qing_late_institution_notes_v0.1.json"
)
SOURCE_REVIEW_PATH = (
    PROJECT_ROOT
    / "data"
    / "knowledge"
    / "reviews"
    / "qing_late_institution_notes_source_review_v0.1.json"
)


def load_draft() -> dict:
    return json.loads(DRAFT_PATH.read_text(encoding="utf-8"))


def load_source_review() -> dict:
    return json.loads(SOURCE_REVIEW_PATH.read_text(encoding="utf-8"))


def test_qing_late_draft_passes_editorial_schema() -> None:
    payload = load_draft()
    assert validate_institution_notes(payload) == []
    assert len(payload["notes"]) == 8


def test_draft_cannot_publish_or_auto_match_before_review() -> None:
    payload = load_draft()
    assert payload["publication_status"] == "DRAFT_ONLY"
    for note in payload["notes"]:
        assert note["status"] == "DRAFT"
        assert note["publication_eligible"] is False
        assert note["matching"]["auto_match_enabled"] is False
        assert note["review"]["decision"] in {
            None, "APPROVE", "REQUEST_CHANGES", "HOLD"
        }
    assert {note["review"]["decision"] for note in payload["notes"]} == {"APPROVE"}
    assert all(note["publication_eligible"] is False for note in payload["notes"])


def test_ambiguous_qing_types_are_not_collapsed_to_one_level() -> None:
    payload = load_draft()
    notes = {note["note_id"]: note for note in payload["notes"]}
    assert "不是单一层级" in notes["qing_late_zhou"]["body_zh"]
    assert "不是单一层级" in notes["qing_late_ting"]["body_zh"]
    assert "派出或办事机构" in notes["qing_late_dao"]["body_zh"]


def test_first_batch_matches_only_explicit_raw_types_and_years() -> None:
    payload = load_draft()
    for note in payload["notes"]:
        matching = note["matching"]
        assert matching["raw_types"]
        assert matching["year_from"] == 1901
        assert matching["year_to"] == 1911
        assert "name" not in matching
        assert "coordinate" not in matching
        assert "distance" not in matching


def test_source_review_covers_every_approved_note() -> None:
    draft = load_draft()
    review = load_source_review()
    note_ids = {note["note_id"] for note in draft["notes"]}
    assert validate_source_review(review, note_ids) == []
    assert {item["verdict"] for item in review["note_reviews"]} == {"VERIFIED"}


def test_candidate_requires_content_approval_and_source_verification() -> None:
    candidate = build_publication_candidate(load_draft(), load_source_review())
    assert candidate["publication_status"] == "PUBLISHED"
    assert candidate["ui_enabled"] is True
    assert len(candidate["notes"]) == 8
    for note in candidate["notes"]:
        assert note["status"] == "PUBLISHED"
        assert note["publication_eligible"] is True
        assert note["source_review_verdict"] == "VERIFIED"
        assert note["matching"]["auto_match_enabled"] is True


def test_matching_is_exact_raw_type_and_inclusive_year_only() -> None:
    candidate = build_publication_candidate(load_draft(), load_source_review())
    assert {note["note_id"] for note in matching_notes(candidate, raw_type="州", year=1911)} == {
        "qing_late_system_overview",
        "qing_late_zhou",
    }
    assert {note["note_id"] for note in matching_notes(candidate, raw_type="直隶州", year=1911)} == {
        "qing_late_system_overview",
        "qing_late_direct_prefecture",
    }
    assert matching_notes(candidate, raw_type="直隶厅", year=1911) == []
    assert matching_notes(candidate, raw_type="州", year=1900) == []
    assert matching_notes(candidate, raw_type="州", year=1912) == []


def test_ting_verification_does_not_claim_unread_scan_as_evidence() -> None:
    review = load_source_review()
    ting = next(item for item in review["note_reviews"] if item["note_id"] == "qing_late_ting")
    assert ting["verdict"] == "VERIFIED"
    assert "ruc_qing_ting_research" in ting["verified_source_ids"]
    assert "pku_qing_ting" not in ting["verified_source_ids"]
