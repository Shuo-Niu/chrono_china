export interface RepresentativePeriod {
  year: number;
  reason: string;
  active_feature_count: number;
  added_since_previous: number;
  removed_since_previous: number;
  change_since_previous: number;
  snapshot_signature_sha256: string;
  rendered_feature_count: number;
  slice_path: string;
}

export interface AnchorManifest {
  anchor_id: string;
  display_name: string;
  modern_location: { lon: number; lat: number };
  source: {
    provider: string;
    record_id: string;
    record_url: string;
    retrieved_at: string;
    license_notice: string;
  };
  available_periods: number[];
  default_period: number;
  periods: RepresentativePeriod[];
  default_radius_km: number;
  coverage: Record<string, string>;
  history_source: {
    dataset: string;
    snapshot_date: string;
    source_url: string;
    sha256: string;
    retrieved_at: string;
  };
  slices: Record<string, string>;
  semantic_notice: string;
}

export interface TemporalSnapshot {
  snapshot_id: string;
  anchor_id: string;
  snapshot_year: number;
  display_year: string;
  broad_era_label: string;
  shortcut_label: string;
  regional_context_label: string | null;
  context_confidence: "high" | "medium" | "low";
  source_status: "supported" | "broad-era-only" | "disputed" | "unresolved";
  source_ids: string[];
  notes: string;
  whether_context_is_manual_reviewed: boolean;
  whether_context_is_safe_for_user_display: boolean;
  unresolved_conflicts: string[];
  sequence_index: number;
  sequence_count: number;
  previous_snapshot_year: number | null;
  changes_from_previous: {
    added_records: number;
    removed_records: number;
    mechanical_only: true;
  };
  timeline: {
    year: number;
    linear_normalized_position: number;
    display_normalized_position: number;
    position_adjusted: boolean;
    scale_scope: "per_anchor";
    display_algorithm: "linear_with_minimum_gap_0_10";
  };
}

export interface TemporalContextManifest {
  schema_version: "1.0";
  generated_at: string;
  anchor_id: string;
  display_name: string;
  supported_snapshot_count: number;
  earliest_supported_year: number;
  latest_supported_year: number;
  timeline_scale_scope: "per_anchor";
  timeline_display_algorithm: "linear_with_minimum_gap_0_10";
  semantic_notice: string;
  snapshots: TemporalSnapshot[];
}

export interface HistoricalProperties {
  tgaz_id: string;
  name: string;
  name_pinyin: string | null;
  feature_type: string;
  display_type_group?: string;
  valid_from: number;
  valid_to: number;
  parent_name: string | null;
  distance_to_anchor_km: number;
  relation_to_anchor: "spatial_nearby" | "viewport_member";
  lineage_claim: null;
  location_confidence: "source_point" | "unresolved_conflict";
  location_assertion_status: "resolved" | "unresolved_conflict" | "not_re_enriched";
  source_id: string;
  source_record_id: string;
  source_url: string;
  source_data_source?: string;
  source_detail_level?: "canonical_api_cache" | "csv_snapshot";
  license: string | null;
  detail_path: string | null;
  display_rank?: number;
}

export interface HistoricalFeature {
  type: "Feature";
  id: string;
  geometry: { type: "Point"; coordinates: [number, number] };
  properties: HistoricalProperties;
}

export interface HistoricalFeatureCollection {
  type: "FeatureCollection";
  metadata: {
    anchor_id: string;
    anchor_display_name: string;
    year: number;
    radius_km: number;
    coverage_status: string;
    underlying_active_record_count: number;
    active_feature_count?: number;
    rendered_feature_count?: number;
    period_selection?: RepresentativePeriod;
    relation_semantics: string;
    query_latency_ms?: number;
    viewport_bbox?: [number, number, number, number];
    spatial_record_count?: number;
  };
  features: HistoricalFeature[];
}

export interface DetailCard extends HistoricalProperties {
  snapshot_year: number;
  names: {
    simplified_chinese: string | null;
    traditional_chinese: string | null;
    pinyin: string | null;
  };
  parent_units: Array<Record<string, string>>;
  subordinate_units: Array<Record<string, string>>;
  source: {
    system: string | null;
    data_source: string | null;
    source_note: string | null;
    source_uri: string | null;
    license: string | null;
  };
  canonical_uri: string;
  semantic_notice: string;
}
