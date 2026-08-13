import type { HistoricalFeature, HistoricalFeatureCollection } from "../types";
import type { ViewportResult } from "../coverage/sourceCoverage";

export type CompactRecord = [
  tgazId: string,
  name: string,
  namePinyin: string | null,
  validFrom: number,
  validTo: number,
  lon: number,
  lat: number,
  featureType: string,
  parentSourceId: string | null,
  parentName: string | null,
  locationConfidence: "source_point" | "unresolved_conflict",
];

export interface CompactHistoricalIndex {
  schema_version: "1.0";
  generated_at: string;
  fields: string[];
  source: {
    dataset: string;
    normalized_path: string;
    normalized_sha256: string;
    record_count: number;
    canonical_uri_template: string;
    license: string | null;
  };
  records: CompactRecord[];
}

export interface ViewportQueryResult {
  collection: HistoricalFeatureCollection;
  viewportResult: ViewportResult;
  activeRecordCount: number;
  spatialRecordCount: number;
  queryLatencyMs: number;
}

export function compactIndexYearRange(index: CompactHistoricalIndex): [number, number] {
  return index.records.reduce(
    (range, record) => [Math.min(range[0], record[3]), Math.max(range[1], record[4])],
    [Infinity, -Infinity],
  );
}

const EXPECTED_FIELDS = [
  "tgaz_id", "name", "name_pinyin", "valid_from", "valid_to", "lon", "lat",
  "feature_type", "parent_source_id", "parent_name", "location_confidence",
];

export function parseCompactIndex(value: unknown): CompactHistoricalIndex {
  const index = value as CompactHistoricalIndex;
  if (
    index?.schema_version !== "1.0" ||
    !Array.isArray(index.records) ||
    index.source?.record_count !== index.records.length ||
    JSON.stringify(index.fields) !== JSON.stringify(EXPECTED_FIELDS)
  ) {
    throw new Error("invalid compact historical index schema");
  }
  return index;
}

function longitudeInside(lon: number, west: number, east: number): boolean {
  return west <= east ? west <= lon && lon <= east : lon >= west || lon <= east;
}

function recordInside(record: CompactRecord, bbox: [number, number, number, number]): boolean {
  const [west, south, east, north] = bbox;
  return longitudeInside(record[5], west, east) && south <= record[6] && record[6] <= north;
}

function haversineKm(
  lon: number,
  lat: number,
  centerLon: number,
  centerLat: number,
): number {
  const radians = (value: number) => value * Math.PI / 180;
  const deltaLat = radians(lat - centerLat);
  const deltaLon = radians(lon - centerLon);
  const firstLat = radians(centerLat);
  const secondLat = radians(lat);
  const a = Math.sin(deltaLat / 2) ** 2 +
    Math.cos(firstLat) * Math.cos(secondLat) * Math.sin(deltaLon / 2) ** 2;
  return 6371.0088 * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

function toFeature(
  record: CompactRecord,
  center: [number, number],
): HistoricalFeature {
  const id = record[0];
  return {
    type: "Feature",
    id,
    geometry: { type: "Point", coordinates: [record[5], record[6]] },
    properties: {
      tgaz_id: id,
      name: record[1],
      name_pinyin: record[2],
      feature_type: record[7],
      valid_from: record[3],
      valid_to: record[4],
      parent_name: record[9],
      distance_to_anchor_km: haversineKm(record[5], record[6], center[0], center[1]),
      relation_to_anchor: "viewport_member",
      lineage_claim: null,
      location_confidence: record[10],
      location_assertion_status: record[10] === "unresolved_conflict" ? "unresolved_conflict" : "resolved",
      source_id: "tgaz_chgis_2016_07_06",
      source_record_id: id,
      source_url: `http://maps.cga.harvard.edu/tgaz/placename/${id}`,
      source_data_source: "CHGIS",
      source_detail_level: "csv_snapshot",
      license: null,
      detail_path: null,
    },
  };
}

export function queryCompactIndex(
  index: CompactHistoricalIndex,
  bbox: [number, number, number, number],
  year: number,
  now: () => number = () => performance.now(),
): ViewportQueryResult {
  if (!Number.isInteger(year) || year === 0) {
    throw new Error("exact historical year must be a non-zero integer");
  }
  const started = now();
  const spatial = index.records.filter((record) => recordInside(record, bbox));
  const active = spatial.filter((record) => record[3] <= year && year <= record[4]);
  const center: [number, number] = [(bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2];
  const features = active.map((record) => toFeature(record, center));
  const viewportResult: ViewportResult = active.length > 0 ? "HAS_RECORDS" : "NO_RECORDS";
  const queryLatencyMs = now() - started;
  return {
    collection: {
      type: "FeatureCollection",
      metadata: {
        anchor_id: "viewport",
        anchor_display_name: "当前视口",
        year,
        radius_km: 0,
        coverage_status: viewportResult,
        underlying_active_record_count: active.length,
        active_feature_count: active.length,
        rendered_feature_count: features.length,
        relation_semantics: "viewport membership only; no identity or lineage claim",
        query_latency_ms: queryLatencyMs,
        viewport_bbox: bbox,
        spatial_record_count: spatial.length,
      },
      features,
    },
    viewportResult,
    activeRecordCount: active.length,
    spatialRecordCount: spatial.length,
    queryLatencyMs,
  };
}
