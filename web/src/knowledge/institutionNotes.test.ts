import { describe, expect, it } from "vitest";
import { parseInstitutionNotes, selectInstitutionNote } from "./institutionNotes";

function fixture() {
  return {
    schema_version: "0.1",
    publication_status: "PUBLISHED",
    ui_enabled: true,
    notes: [
      {
        note_id: "overview",
        note_kind: "ERA_OVERVIEW",
        title_zh: "清末总览",
        body_zh: "总览正文",
        matching: {
          raw_types: ["府", "州"],
          year_from: 1901,
          year_to: 1911,
          auto_match_enabled: true,
        },
        source_ids: ["source_a"],
        status: "PUBLISHED",
      },
      {
        note_id: "fu",
        note_kind: "UNIT_TYPE",
        title_zh: "清末的府",
        body_zh: "府的制度说明",
        matching: {
          raw_types: ["府"],
          year_from: 1901,
          year_to: 1911,
          auto_match_enabled: true,
        },
        source_ids: ["source_a"],
        status: "PUBLISHED",
      },
    ],
  };
}

describe("institution notes", () => {
  it("selects only the exact unit-type note and suppresses the overview", () => {
    const publication = parseInstitutionNotes(fixture());
    expect(selectInstitutionNote(publication, "府", 1911)?.noteId).toBe("fu");
  });

  it("does not infer from similar types or extend the audited years", () => {
    const publication = parseInstitutionNotes(fixture());
    expect(selectInstitutionNote(publication, "直隶府", 1911)).toBeNull();
    expect(selectInstitutionNote(publication, "府", 1900)).toBeNull();
    expect(selectInstitutionNote(publication, "府", 1912)).toBeNull();
  });

  it("fails closed when two exact unit notes conflict", () => {
    const payload = fixture();
    payload.notes.push({
      ...payload.notes[1],
      note_id: "fu_duplicate",
    });
    const publication = parseInstitutionNotes(payload);
    expect(selectInstitutionNote(publication, "府", 1911)).toBeNull();
  });

  it("rejects malformed or non-published metadata", () => {
    expect(() => parseInstitutionNotes({})).toThrow("unsupported institution-note schema");
    expect(() => parseInstitutionNotes({ ...fixture(), ui_enabled: false })).toThrow(
      "not enabled for UI",
    );
    const malformed = fixture();
    malformed.notes[1].matching.auto_match_enabled = false;
    expect(() => parseInstitutionNotes(malformed)).toThrow("not approved for matching");
  });
});
