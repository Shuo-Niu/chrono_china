import type { DetailCard, HistoricalFeature } from "../types";
import { formatHistoricalYear } from "../temporal/temporal";

function objectValue(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === "object" ? value as Record<string, unknown> : {};
}

function stringValue(value: unknown, fallback: string): string {
  return typeof value === "string" && value.trim() ? value : fallback;
}

function optionalString(value: unknown, fallback: string | null = null): string | null {
  return typeof value === "string" ? value : fallback;
}

function finiteNumber(value: unknown, fallback: number): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

export function detailFromActiveFeature(
  feature: HistoricalFeature,
  snapshotYear: number,
): DetailCard {
  const properties = feature.properties;
  return {
    ...properties,
    snapshot_year: snapshotYear,
    names: {
      simplified_chinese: properties.name,
      traditional_chinese: null,
      pinyin: properties.name_pinyin,
    },
    parent_units: [],
    subordinate_units: [],
    source: {
      system: "TGAZ / CHGIS CSV snapshot",
      data_source: properties.source_data_source ?? "CHGIS",
      source_note: (
        "Phase 1.1 使用冻结 CSV active record；该记录未在本实验中重新请求 canonical API enrichment。"
      ),
      source_uri: properties.source_url,
      license: properties.license,
    },
    canonical_uri: properties.source_url,
    semantic_notice: "Spatial neighborhood only; no historical-lineage claim is made.",
  };
}

export function normalizeDetailPayload(
  payload: unknown,
  feature: HistoricalFeature,
  snapshotYear: number,
): DetailCard {
  const fallback = detailFromActiveFeature(feature, snapshotYear);
  const value = objectValue(payload);
  const source = objectValue(value.source);
  const names = objectValue(value.names);
  return {
    ...fallback,
    name: stringValue(value.name, fallback.name),
    name_pinyin: optionalString(value.name_pinyin, fallback.name_pinyin),
    feature_type: stringValue(value.feature_type, fallback.feature_type),
    valid_from: finiteNumber(value.valid_from, fallback.valid_from),
    valid_to: finiteNumber(value.valid_to, fallback.valid_to),
    parent_name: optionalString(value.parent_name, fallback.parent_name),
    distance_to_anchor_km: finiteNumber(
      value.distance_to_anchor_km,
      fallback.distance_to_anchor_km,
    ),
    location_confidence: value.location_confidence === "unresolved_conflict"
      ? "unresolved_conflict"
      : fallback.location_confidence,
    source_record_id: stringValue(value.source_record_id, fallback.source_record_id),
    snapshot_year: finiteNumber(value.snapshot_year, snapshotYear),
    names: {
      simplified_chinese: optionalString(names.simplified_chinese, fallback.names.simplified_chinese),
      traditional_chinese: optionalString(names.traditional_chinese),
      pinyin: optionalString(names.pinyin, fallback.names.pinyin),
    },
    parent_units: Array.isArray(value.parent_units) ? value.parent_units as Array<Record<string, string>> : [],
    subordinate_units: Array.isArray(value.subordinate_units)
      ? value.subordinate_units as Array<Record<string, string>>
      : [],
    source: {
      system: optionalString(source.system, fallback.source.system),
      data_source: optionalString(source.data_source, fallback.source.data_source),
      source_note: optionalString(source.source_note),
      source_uri: optionalString(source.source_uri, fallback.source.source_uri),
      license: optionalString(source.license, fallback.source.license),
    },
    canonical_uri: stringValue(value.canonical_uri, fallback.canonical_uri),
    semantic_notice: stringValue(value.semantic_notice, fallback.semantic_notice),
  };
}

export function formatDetailYear(value: unknown): string {
  if (value === 0) return "来源未注明";
  if (typeof value !== "number" || !Number.isInteger(value)) return "暂不可用";
  try {
    return formatHistoricalYear(value);
  } catch (error) {
    console.error("[ChronoChina detail] invalid historical year", value, error);
    return "暂不可用";
  }
}

export function formatDetailDistance(value: unknown): string {
  return typeof value === "number" && Number.isFinite(value)
    ? `约 ${value.toFixed(1)} km`
    : "暂不可用";
}

export function sourceNotePresentation(sourceNote: unknown): {
  text: string;
  raw: string | null;
  rawDiffers: boolean;
} {
  const raw = typeof sourceNote === "string" ? sourceNote : null;
  const text = (raw ?? "")
    .replace(/<[^>]*>/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  return { text, raw, rawDiffers: Boolean(raw && raw !== text) };
}
