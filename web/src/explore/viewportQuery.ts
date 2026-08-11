import type { HistoricalFeature, HistoricalFeatureCollection } from "../types";

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

export type ViewportCoverageStatus =
  | "covered_with_active_records"
  | "covered_no_active_records"
  | "outside_source_scope"
  | "insufficient_source_coverage"
  | "unsupported_year"
  | "query_failed";

export interface ViewportQueryResult {
  collection: HistoricalFeatureCollection;
  coverageStatus: ViewportCoverageStatus;
  coverageReason: string;
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

const CONSERVATIVE_GAP_INTERIORS = [
  { id: "xinjiang", bbox: [78, 38, 91, 46] },
  { id: "tibet_lhasa", bbox: [89.5, 28, 92.5, 31.5] },
  { id: "qinghai_xining", bbox: [99.5, 34.5, 103, 38] },
  { id: "inner_mongolia_hohhot", bbox: [109.5, 39, 114, 43] },
] as const;

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

function viewportCenterGap(bbox: [number, number, number, number]): string | null {
  const [west, south, east, north] = bbox;
  const centerLon = (west + east) / 2;
  const centerLat = (south + north) / 2;
  const match = CONSERVATIVE_GAP_INTERIORS.find(({ bbox: gap }) =>
    centerLon >= gap[0] && centerLat >= gap[1] && centerLon <= gap[2] && centerLat <= gap[3],
  );
  return match?.id ?? null;
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
  const globalYears = compactIndexYearRange(index);
  const knownGap = viewportCenterGap(bbox);
  let coverageStatus: ViewportCoverageStatus;
  let coverageReason: string;
  if (knownGap) {
    coverageStatus = "outside_source_scope";
    coverageReason = `当前视口中心位于 ${knownGap} 保守负控框内；CHGIS Time Series 基础覆盖不包含该区域。框内即使有索引记录，也不能视为完整覆盖。`;
  } else if (year < globalYears[0] || year > globalYears[1]) {
    coverageStatus = "unsupported_year";
    coverageReason = `所选年份超出索引记录的有效年代包络 ${globalYears[0]}..${globalYears[1]}。`;
  } else if (active.length > 0) {
    coverageStatus = "covered_with_active_records";
    coverageReason = "当前精确年份与视口查询取得有效来源记录。";
  } else if (spatial.length > 0) {
    coverageStatus = "covered_no_active_records";
    coverageReason = "当前视口存在其他年代的来源记录，但没有记录在所选精确年份有效。";
  } else {
    coverageStatus = "insufficient_source_coverage";
    coverageReason = "当前视口未观察到来源记录足迹；这不能作为历史上没有地点的证据。";
  }
  const queryLatencyMs = now() - started;
  return {
    collection: {
      type: "FeatureCollection",
      metadata: {
        anchor_id: "viewport",
        anchor_display_name: "当前视口",
        year,
        radius_km: 0,
        coverage_status: coverageStatus,
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
    coverageStatus,
    coverageReason,
    activeRecordCount: active.length,
    spatialRecordCount: spatial.length,
    queryLatencyMs,
  };
}

export function coverageStatusLabel(status: ViewportCoverageStatus): string {
  return {
    covered_with_active_records: "当前视口有该年有效记录",
    covered_no_active_records: "本区有来源记录，但所选年份无有效记录",
    outside_source_scope: "当前视口位于已知来源覆盖范围外",
    insufficient_source_coverage: "当前视口来源覆盖不足，不能解释为历史上没有地点",
    unsupported_year: "所选年份超出当前索引年代范围",
    query_failed: "视口查询失败",
  }[status];
}
