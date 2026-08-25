export type InstitutionNoteKind = "ERA_OVERVIEW" | "UNIT_TYPE";

export interface InstitutionNote {
  noteId: string;
  noteKind: InstitutionNoteKind;
  titleZh: string;
  bodyZh: string;
  rawTypes: string[];
  yearFrom: number;
  yearTo: number;
  sourceIds: string[];
  autoMatchEnabled: boolean;
}

export interface InstitutionNotePublication {
  publicationStatus: "PUBLISHED";
  uiEnabled: boolean;
  notes: InstitutionNote[];
}

function record(value: unknown, label: string): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${label} must be an object`);
  }
  return value as Record<string, unknown>;
}

function nonEmptyString(value: unknown, label: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${label} must be a non-empty string`);
  }
  return value;
}

function stringArray(value: unknown, label: string): string[] {
  if (!Array.isArray(value) || value.length === 0) {
    throw new Error(`${label} must be a non-empty array`);
  }
  return value.map((item, index) => nonEmptyString(item, `${label}[${index}]`));
}

export function parseInstitutionNotes(value: unknown): InstitutionNotePublication {
  const root = record(value, "institution notes");
  if (root.schema_version !== "0.1") throw new Error("unsupported institution-note schema");
  if (root.publication_status !== "PUBLISHED") throw new Error("institution notes are not published");
  if (root.ui_enabled !== true) throw new Error("institution notes are not enabled for UI");
  if (!Array.isArray(root.notes)) throw new Error("institution notes must contain notes");

  const noteIds = new Set<string>();
  const notes = root.notes.map((value, index) => {
    const note = record(value, `notes[${index}]`);
    const matching = record(note.matching, `notes[${index}].matching`);
    const noteId = nonEmptyString(note.note_id, `notes[${index}].note_id`);
    if (noteIds.has(noteId)) throw new Error(`duplicate institution note: ${noteId}`);
    noteIds.add(noteId);
    if (note.status !== "PUBLISHED") throw new Error(`${noteId} is not published`);
    if (note.note_kind !== "ERA_OVERVIEW" && note.note_kind !== "UNIT_TYPE") {
      throw new Error(`${noteId} has an invalid note kind`);
    }
    if (!Number.isInteger(matching.year_from) || !Number.isInteger(matching.year_to)) {
      throw new Error(`${noteId} has an invalid year range`);
    }
    if ((matching.year_from as number) > (matching.year_to as number)) {
      throw new Error(`${noteId} has an inverted year range`);
    }
    if (matching.auto_match_enabled !== true) {
      throw new Error(`${noteId} is not approved for matching`);
    }
    return {
      noteId,
      noteKind: note.note_kind,
      titleZh: nonEmptyString(note.title_zh, `${noteId}.title_zh`),
      bodyZh: nonEmptyString(note.body_zh, `${noteId}.body_zh`),
      rawTypes: stringArray(matching.raw_types, `${noteId}.raw_types`),
      yearFrom: matching.year_from as number,
      yearTo: matching.year_to as number,
      sourceIds: stringArray(note.source_ids, `${noteId}.source_ids`),
      autoMatchEnabled: true,
    } satisfies InstitutionNote;
  });

  return { publicationStatus: "PUBLISHED", uiEnabled: true, notes };
}

export function selectInstitutionNote(
  publication: InstitutionNotePublication | null,
  rawType: string,
  year: number,
): InstitutionNote | null {
  if (!publication?.uiEnabled) return null;
  const matches = publication.notes.filter((note) =>
    note.noteKind === "UNIT_TYPE" &&
    note.autoMatchEnabled &&
    note.rawTypes.includes(rawType) &&
    note.yearFrom <= year && year <= note.yearTo
  );
  return matches.length === 1 ? matches[0] : null;
}
