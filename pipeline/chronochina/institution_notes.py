from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REVIEW_STATUSES = {"DRAFT", "REVIEWED", "PUBLISHED"}
REVIEW_DECISIONS = {None, "APPROVE", "REQUEST_CHANGES", "HOLD"}
NOTE_KINDS = {"ERA_OVERVIEW", "UNIT_TYPE"}
SOURCE_REVIEW_VERDICTS = {"VERIFIED", "NOT_VERIFIED"}


def validate_institution_notes(payload: dict[str, Any]) -> list[str]:
    """Return human-readable validation errors for an editorial note set."""

    errors: list[str] = []
    if payload.get("schema_version") != "0.1":
        errors.append("schema_version must be 0.1")

    sources = payload.get("sources")
    if not isinstance(sources, list) or not sources:
        errors.append("sources must be a non-empty list")
        sources = []
    source_ids = [source.get("source_id") for source in sources if isinstance(source, dict)]
    if len(source_ids) != len(set(source_ids)):
        errors.append("source_id values must be unique")
    known_source_ids = {source_id for source_id in source_ids if isinstance(source_id, str)}

    notes = payload.get("notes")
    if not isinstance(notes, list) or not notes:
        errors.append("notes must be a non-empty list")
        return errors

    note_ids: set[str] = set()
    for index, note in enumerate(notes):
        prefix = f"notes[{index}]"
        if not isinstance(note, dict):
            errors.append(f"{prefix} must be an object")
            continue

        note_id = note.get("note_id")
        if not isinstance(note_id, str) or not note_id:
            errors.append(f"{prefix}.note_id must be a non-empty string")
        elif note_id in note_ids:
            errors.append(f"{prefix}.note_id is duplicated: {note_id}")
        else:
            note_ids.add(note_id)

        if note.get("note_kind") not in NOTE_KINDS:
            errors.append(f"{prefix}.note_kind is invalid")
        if note.get("status") not in REVIEW_STATUSES:
            errors.append(f"{prefix}.status is invalid")

        title = note.get("title_zh")
        body = note.get("body_zh")
        if not isinstance(title, str) or not title.strip():
            errors.append(f"{prefix}.title_zh must be a non-empty string")
        if not isinstance(body, str) or not 50 <= len(body.strip()) <= 180:
            errors.append(f"{prefix}.body_zh must contain 50-180 characters")

        matching = note.get("matching")
        if not isinstance(matching, dict):
            errors.append(f"{prefix}.matching must be an object")
        else:
            raw_types = matching.get("raw_types")
            if not isinstance(raw_types, list) or not raw_types or not all(
                isinstance(item, str) and item for item in raw_types
            ):
                errors.append(f"{prefix}.matching.raw_types must be non-empty strings")
            start = matching.get("year_from")
            end = matching.get("year_to")
            if not isinstance(start, int) or not isinstance(end, int) or start > end:
                errors.append(f"{prefix}.matching year range is invalid")
            elif start == 0 or end == 0 or start < 0 < end:
                errors.append(f"{prefix}.matching year range must not cross year zero")

        note_source_ids = note.get("source_ids")
        if not isinstance(note_source_ids, list) or len(note_source_ids) < 2:
            errors.append(f"{prefix}.source_ids must cite at least two sources")
        elif unknown := set(note_source_ids) - known_source_ids:
            errors.append(f"{prefix}.source_ids contains unknown IDs: {sorted(unknown)}")

        review = note.get("review")
        if not isinstance(review, dict):
            errors.append(f"{prefix}.review must be an object")
        elif review.get("decision") not in REVIEW_DECISIONS:
            errors.append(f"{prefix}.review.decision is invalid")

        if note.get("status") == "DRAFT" and note.get("publication_eligible") is not False:
            errors.append(f"{prefix} draft must not be publication eligible")

    return errors


def validate_source_review(
    payload: dict[str, Any], expected_note_ids: set[str]
) -> list[str]:
    """Validate that source review accounts for every editorial draft note."""

    errors: list[str] = []
    if payload.get("schema_version") != "0.1":
        errors.append("schema_version must be 0.1")

    reviews = payload.get("note_reviews")
    if not isinstance(reviews, list):
        return errors + ["note_reviews must be a list"]

    review_ids: list[str] = []
    for index, review in enumerate(reviews):
        prefix = f"note_reviews[{index}]"
        if not isinstance(review, dict):
            errors.append(f"{prefix} must be an object")
            continue
        note_id = review.get("note_id")
        if not isinstance(note_id, str) or not note_id:
            errors.append(f"{prefix}.note_id must be a non-empty string")
        else:
            review_ids.append(note_id)
        if review.get("verdict") not in SOURCE_REVIEW_VERDICTS:
            errors.append(f"{prefix}.verdict is invalid")
        source_ids = review.get("verified_source_ids")
        if not isinstance(source_ids, list) or not source_ids:
            errors.append(f"{prefix}.verified_source_ids must be non-empty")
        evidence = review.get("evidence")
        if not isinstance(evidence, str) or not evidence.strip():
            errors.append(f"{prefix}.evidence must be a non-empty string")

    if len(review_ids) != len(set(review_ids)):
        errors.append("source review note_id values must be unique")
    actual_note_ids = set(review_ids)
    if actual_note_ids != expected_note_ids:
        missing = sorted(expected_note_ids - actual_note_ids)
        extra = sorted(actual_note_ids - expected_note_ids)
        errors.append(f"source review note coverage mismatch: missing={missing}, extra={extra}")
    return errors


def build_publication_candidate(
    draft: dict[str, Any], source_review: dict[str, Any]
) -> dict[str, Any]:
    """Promote approved and source-verified notes to a UI-review candidate."""

    draft_errors = validate_institution_notes(draft)
    if draft_errors:
        raise ValueError("invalid institution-note draft: " + "; ".join(draft_errors))

    notes = draft["notes"]
    note_ids = {note["note_id"] for note in notes}
    review_errors = validate_source_review(source_review, note_ids)
    if review_errors:
        raise ValueError("invalid source review: " + "; ".join(review_errors))

    reviews = {review["note_id"]: review for review in source_review["note_reviews"]}
    candidate_notes: list[dict[str, Any]] = []
    for note in notes:
        review = reviews[note["note_id"]]
        if note["review"]["decision"] != "APPROVE" or review["verdict"] != "VERIFIED":
            continue
        matching = dict(note["matching"])
        matching["auto_match_enabled"] = True
        candidate_notes.append(
            {
                "note_id": note["note_id"],
                "note_kind": note["note_kind"],
                "title_zh": note["title_zh"],
                "body_zh": note["body_zh"],
                "matching": matching,
                "source_ids": list(review["verified_source_ids"]),
                "caveat_zh": note["caveat_zh"],
                "status": "PUBLISHED",
                "publication_eligible": True,
                "source_review_verdict": review["verdict"],
            }
        )

    return {
        "schema_version": "0.1",
        "publication_set_id": "qing_late_institution_notes_v0_1",
        "draft_set_id": draft["draft_set_id"],
        "generated_at": source_review["reviewed_at"],
        "publication_status": "PUBLISHED",
        "ui_approval": {"decision": "APPROVE", "reviewer": "Shuo Niu", "reviewed_at": "2026-08-24"},
        "ui_enabled": True,
        "matching_policy": "exact raw type and inclusive year range only",
        "sources": draft["sources"],
        "notes": candidate_notes,
    }


def matching_notes(
    candidate: dict[str, Any], *, raw_type: str, year: int
) -> list[dict[str, Any]]:
    """Return exact-type, in-range matches without inferring from names or geometry."""

    return [
        note
        for note in candidate.get("notes", [])
        if raw_type in note["matching"]["raw_types"]
        and note["matching"]["year_from"] <= year <= note["matching"]["year_to"]
    ]


def write_default_publication_candidate(project_root: Path) -> Path:
    draft_path = project_root / "data" / "knowledge" / "drafts" / "qing_late_institution_notes_v0.1.json"
    review_path = project_root / "data" / "knowledge" / "reviews" / "qing_late_institution_notes_source_review_v0.1.json"
    output_path = project_root / "data" / "processed" / "knowledge" / "qing_late_institution_notes_v0.1.json"
    draft = json.loads(draft_path.read_text(encoding="utf-8"))
    source_review = json.loads(review_path.read_text(encoding="utf-8"))
    candidate = build_publication_candidate(draft, source_review)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(candidate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return output_path


if __name__ == "__main__":
    from chronochina.config import PROJECT_ROOT

    print(write_default_publication_candidate(PROJECT_ROOT))
