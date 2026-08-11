import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, test } from "vitest";

import {
  parseCompactIndex,
  queryCompactIndex,
  type CompactHistoricalIndex,
} from "./viewportQuery";

function index(records: CompactHistoricalIndex["records"]): CompactHistoricalIndex {
  return {
    schema_version: "1.0",
    generated_at: "2026-08-10T00:00:00Z",
    fields: [
      "tgaz_id", "name", "name_pinyin", "valid_from", "valid_to", "lon", "lat",
      "feature_type", "parent_source_id", "parent_name", "location_confidence",
    ],
    source: {
      dataset: "test",
      normalized_path: "test",
      normalized_sha256: "test",
      record_count: records.length,
      canonical_uri_template: "http://example/{TGAZ_ID}",
      license: null,
    },
    records,
  };
}

describe("viewport query", () => {
  test("uses inclusive exact-year filtering including BCE", () => {
    const source = index([
      ["a", "A", null, -201, 14, 116, 36, "县", null, null, "source_point"],
      ["b", "B", null, 15, 20, 116, 36, "县", null, null, "source_point"],
    ]);
    expect(queryCompactIndex(source, [115, 35, 117, 37], -201).activeRecordCount).toBe(1);
    expect(queryCompactIndex(source, [115, 35, 117, 37], 14).activeRecordCount).toBe(1);
    expect(queryCompactIndex(source, [115, 35, 117, 37], 15).activeRecordCount).toBe(1);
    expect(() => queryCompactIndex(source, [115, 35, 117, 37], 0)).toThrow("non-zero");
  });

  test("distinguishes covered empty, insufficient coverage, and known source gap", () => {
    const source = index([
      ["a", "A", null, 100, 200, 116, 36, "县", null, null, "source_point"],
    ]);
    expect(queryCompactIndex(source, [115, 35, 117, 37], 50).coverageStatus).toBe("unsupported_year");
    expect(queryCompactIndex(source, [115, 35, 117, 37], 100).coverageStatus).toBe("covered_with_active_records");
    expect(queryCompactIndex(source, [120, 30, 121, 31], 100).coverageStatus).toBe("insufficient_source_coverage");
    expect(queryCompactIndex(source, [84, 40, 86, 42], 100).coverageStatus).toBe("outside_source_scope");
    expect(queryCompactIndex(source, [89.1, 28.9, 93.1, 30.4], 100).coverageStatus).toBe("outside_source_scope");
  });

  test("real compact index parses and post-load Beijing query stays below 100 ms", () => {
    const path = resolve("../data/processed/explore/tgaz_compact.json");
    const source = parseCompactIndex(JSON.parse(readFileSync(path, "utf8")));
    const result = queryCompactIndex(source, [115.4, 39.15, 117.4, 40.65], 1911);
    expect(source.records).toHaveLength(71393);
    expect(result.activeRecordCount).toBeGreaterThan(100);
    expect(result.queryLatencyMs).toBeLessThan(100);
  });
});
