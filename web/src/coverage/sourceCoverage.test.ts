import { describe, expect, test } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import type { HistoricalFeature } from "../types";
import type { CompactHistoricalIndex } from "../explore/viewportQuery";
import {
  assessSourceCoverage,
  parseCoverageMetadata,
  resolveViewportResult,
  userCoverageMessages,
} from "./sourceCoverage";

const INDEX_SHA = "7c9ccaedfd58445595e5ab68fd1fb9e106e33c37b8bb98002a7e8e6bad5b5baf";

function index(): CompactHistoricalIndex {
  return {
    schema_version: "1.0",
    generated_at: "2026-08-12T00:00:00Z",
    fields: [
      "tgaz_id", "name", "name_pinyin", "valid_from", "valid_to", "lon", "lat",
      "feature_type", "parent_source_id", "parent_name", "location_confidence",
    ],
    source: {
      dataset: "test",
      normalized_path: "test",
      normalized_sha256: "normalized",
      record_count: 4,
      canonical_uri_template: "https://example.test/{TGAZ_ID}",
      license: null,
    },
    records: [
      ["early", "早期亭", null, 14, 22, 108, 34, "亭", null, null, "source_point"],
      ["pavilion", "杜邮亭", null, 623, 959, 108, 34, "亭", null, null, "source_point"],
      ["town-1820", "村镇", null, 1820, 1820, 108, 34, "村镇", null, null, "source_point"],
      ["town-1911", "村镇", null, 1911, 1911, 108, 34, "村镇", null, null, "source_point"],
    ],
  };
}

function metadata(): unknown {
  const timeSeries = (id: string, rawTypes: string[], periods: number[][]) => ({
    id,
    raw_types: rawTypes,
    temporal_model: "TIME_SERIES",
    support: "UNKNOWN",
    observed_periods: periods,
    provenance: { basis: "fixture" },
    source_evidence: "fixture",
    evidence_strength: "FROZEN_INDEX_OBSERVATION",
  });
  return {
    schema_version: "1.0",
    canonical_index: {
      path: "data/processed/explore/tgaz_compact.json",
      bytes: 1,
      record_count: 4,
      sha256: INDEX_SHA,
      observed_envelope: { min_year: 14, max_year: 1911 },
    },
    provenance: {},
    families: {
      settlement: {
        default_support: "UNSUPPORTED",
        components: [
          {
            id: "raw_town_snapshots",
            raw_types: ["村镇"],
            temporal_model: "TIME_SLICE",
            support: "SUPPORTED",
            snapshot_years: [1820, 1911],
            provenance: { basis: "fixture" },
            source_evidence: "fixture",
            evidence_strength: "APPROVED_SOURCE_EVIDENCE",
          },
          {
            id: "raw_pavilion_intervals",
            raw_types: ["亭"],
            temporal_model: "TIME_SERIES",
            support: "UNKNOWN",
            supported_periods: [[14, 22], [623, 959]],
            provenance: { basis: "fixture" },
            source_evidence: "fixture",
            evidence_strength: "APPROVED_SOURCE_EVIDENCE",
          },
        ],
        developer_mode_explanation: "fixture",
        user_mode_copy: {
          snapshot_template: "{year} 村镇快照",
          unsupported: "当前来源无该时期资料",
          unknown: "来源覆盖未明",
        },
      },
      high_admin: {
        default_support: "LIMITED",
        components: [timeSeries("province", ["省"], [[1220, 1911]])],
        developer_mode_explanation: "fixture",
        user_mode_copy: { limited: "高层级资料有限" },
      },
      regional_admin: {
        default_support: "SUPPORTED",
        components: [timeSeries("prefecture", ["府"], [[14, 1911]])],
        developer_mode_explanation: "fixture",
        user_mode_copy: {},
      },
      county: {
        default_support: "SUPPORTED",
        components: [timeSeries("county", ["县"], [[14, 1911]])],
        developer_mode_explanation: "fixture",
        user_mode_copy: {},
      },
      other: {
        default_support: "UNKNOWN",
        components: [],
        developer_mode_explanation: "fixture",
        user_mode_copy: { unknown: "来源覆盖未明" },
      },
      polity: {
        default_support: "UNKNOWN",
        components: [],
        developer_mode_explanation: "fixture",
      },
    },
  };
}

function feature(id: string, rawType: string): HistoricalFeature {
  return {
    type: "Feature",
    id,
    geometry: { type: "Point", coordinates: [108, 34] },
    properties: {
      tgaz_id: id,
      name: id,
      name_pinyin: null,
      feature_type: rawType,
      valid_from: 1,
      valid_to: 2,
      parent_name: null,
      distance_to_anchor_km: 0,
      relation_to_anchor: "viewport_member",
      lineage_claim: null,
      location_confidence: "source_point",
      location_assertion_status: "resolved",
      source_id: "test",
      source_record_id: id,
      source_url: "https://example.test",
      license: null,
      detail_path: null,
    },
  };
}

describe("source coverage", () => {
  test("requires a verified compact SHA and rejects every identity mismatch", () => {
    expect(parseCoverageMetadata(metadata(), index(), INDEX_SHA).canonicalIndex.recordCount).toBe(4);
    expect(() => parseCoverageMetadata(
      metadata(),
      index(),
      undefined as unknown as string,
    )).toThrow("verified SHA");
    expect(() => parseCoverageMetadata(metadata(), index(), "0".repeat(64))).toThrow("identity");
    const mismatched = structuredClone(metadata()) as Record<string, any>;
    mismatched.canonical_index.sha256 = "0".repeat(64);
    expect(() => parseCoverageMetadata(mismatched, index(), INDEX_SHA)).toThrow("identity");
    const wrongCount = structuredClone(metadata()) as Record<string, any>;
    wrongCount.canonical_index.record_count = 5;
    expect(() => parseCoverageMetadata(wrongCount, index(), INDEX_SHA)).toThrow("identity");
    expect(() => parseCoverageMetadata({ schema_version: "0" }, index(), INDEX_SHA)).toThrow("schema");
  });

  test("parses the committed metadata against the real compact index", () => {
    const compact = JSON.parse(readFileSync(resolve("../data/processed/explore/tgaz_compact.json"), "utf8"));
    const coverage = JSON.parse(readFileSync(resolve("../data/metadata/historical_layer_coverage.json"), "utf8"));
    expect(parseCoverageMetadata(coverage, compact, INDEX_SHA).canonicalIndex).toMatchObject({
      recordCount: 71_393,
      observedEnvelope: { minYear: -763, maxYear: 1912 },
    });
  });

  test("keeps settlement snapshot and interval components independent", () => {
    const parsed = parseCoverageMetadata(metadata(), index(), INDEX_SHA);
    expect(assessSourceCoverage(parsed, "settlement", 1819).support).toBe("UNSUPPORTED");
    expect(assessSourceCoverage(parsed, "settlement", 1820).temporalModels).toEqual(["TIME_SLICE"]);
    expect(assessSourceCoverage(parsed, "settlement", 1821).support).toBe("UNSUPPORTED");
    expect(assessSourceCoverage(parsed, "settlement", 1910).support).toBe("UNSUPPORTED");
    expect(assessSourceCoverage(parsed, "settlement", 1911).temporalModels).toEqual(["TIME_SLICE"]);
    for (const year of [14, 626, 750]) {
      expect(assessSourceCoverage(parsed, "settlement", year)).toMatchObject({
        support: "UNKNOWN",
        temporalModels: ["TIME_SERIES"],
      });
    }
  });

  test("keeps limited source coverage orthogonal to viewport results", () => {
    const parsed = parseCoverageMetadata(metadata(), index(), INDEX_SHA);
    const highAdmin = assessSourceCoverage(parsed, "high_admin", 750);
    expect(highAdmin.support).toBe("LIMITED");
    expect(resolveViewportResult([feature("province", "省")], "high_admin")).toBe("HAS_RECORDS");
    expect(userCoverageMessages(highAdmin, "HAS_RECORDS", true).map((item) => item.text))
      .toEqual(["高层级资料有限"]);
  });

  test("preserves snapshot plus empty viewport and suppresses disabled-layer copy", () => {
    const parsed = parseCoverageMetadata(metadata(), index(), INDEX_SHA);
    const snapshot = assessSourceCoverage(parsed, "settlement", 1820);
    expect(userCoverageMessages(snapshot, "NO_RECORDS", true).map((item) => item.text))
      .toEqual(["1820 村镇快照", "当前范围无记录"]);
    expect(userCoverageMessages(snapshot, "NO_RECORDS", false)).toEqual([]);
  });

  test("emits no User Mode absence claim when metadata is missing", () => {
    const assessment = assessSourceCoverage(null, "settlement", 1819);
    expect(assessment).toMatchObject({ support: "UNKNOWN", temporalModels: [] });
    expect(assessment.diagnostic).not.toBeNull();
    expect(userCoverageMessages(assessment, "NO_RECORDS", true)).toEqual([]);
  });

  test("normal supported time series and polity produce no special User Mode copy", () => {
    const parsed = parseCoverageMetadata(metadata(), index(), INDEX_SHA);
    expect(userCoverageMessages(
      assessSourceCoverage(parsed, "county", 750),
      "HAS_RECORDS",
      true,
    )).toEqual([]);
    expect(userCoverageMessages(
      assessSourceCoverage(parsed, "polity", 750),
      "NO_RECORDS",
      true,
    )).toEqual([]);
  });

  test("does not mutate metadata or features", () => {
    const rawMetadata = metadata();
    const sourceIndex = index();
    const points = [feature("pavilion", "亭")];
    const before = JSON.stringify({ rawMetadata, sourceIndex, points });
    const parsed = parseCoverageMetadata(rawMetadata, sourceIndex, INDEX_SHA);
    assessSourceCoverage(parsed, "settlement", 626);
    resolveViewportResult(points, "settlement");
    expect(JSON.stringify({ rawMetadata, sourceIndex, points })).toBe(before);
  });

  test("rejects malformed temporal components and cross-family raw types", () => {
    const cases = [
      (value: Record<string, any>) => { value.families.settlement.components[0].snapshot_years = []; },
      (value: Record<string, any>) => { delete value.families.settlement.components[1].supported_periods; },
      (value: Record<string, any>) => { value.families.settlement.components[1].supported_periods = [[959, 623]]; },
      (value: Record<string, any>) => { value.families.county.components[0].raw_types = ["村镇"]; },
    ];
    for (const mutate of cases) {
      const malformed = structuredClone(metadata()) as Record<string, any>;
      mutate(malformed);
      expect(() => parseCoverageMetadata(malformed, index(), INDEX_SHA)).toThrow("schema");
    }
  });

  test("keeps active unsupported components conservative", () => {
    const raw = structuredClone(metadata()) as Record<string, any>;
    raw.families.settlement.components[1].support = "UNSUPPORTED";
    expect(assessSourceCoverage(
      parseCoverageMetadata(raw, index(), INDEX_SHA),
      "settlement",
      626,
    ).support).toBe("UNSUPPORTED");
  });

  test("preserves Developer Mode evidence and family explanation", () => {
    const parsed = parseCoverageMetadata(metadata(), index(), INDEX_SHA);
    expect(parsed.families.settlement.developerModeExplanation).toBe("fixture");
    expect(parsed.families.settlement.components[0]).toMatchObject({
      sourceEvidence: "fixture",
      evidenceStrength: "APPROVED_SOURCE_EVIDENCE",
      provenance: { basis: "fixture" },
    });
  });

  test("emits snapshot and simultaneous exceptional coverage state in stable order", () => {
    const raw = structuredClone(metadata()) as Record<string, any>;
    raw.families.settlement.components[1].supported_periods.push([1820, 1820]);
    const assessment = assessSourceCoverage(
      parseCoverageMetadata(raw, index(), INDEX_SHA),
      "settlement",
      1820,
    );
    expect(userCoverageMessages(assessment, "HAS_RECORDS", true).map((item) => item.text))
      .toEqual(["1820 村镇快照", "来源覆盖未明"]);
  });
});
