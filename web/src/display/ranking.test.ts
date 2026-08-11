import { describe, expect, test } from "vitest";

import type { HistoricalFeature } from "../types";
import {
  rankNearest,
  rankTypeDiverse,
  rankTypeSpatial,
  selectDisplay,
  spatialCoverageGridCells,
} from "./ranking";

const anchor = { lon: 0, lat: 0 };

function feature(
  id: string,
  distance: number,
  featureType: string,
  lon = 0,
  lat = 0,
): HistoricalFeature {
  return {
    type: "Feature",
    id,
    geometry: { type: "Point", coordinates: [lon, lat] },
    properties: {
      tgaz_id: id,
      name: id,
      name_pinyin: null,
      feature_type: featureType,
      valid_from: 1,
      valid_to: 2,
      parent_name: null,
      distance_to_anchor_km: distance,
      relation_to_anchor: "spatial_nearby",
      lineage_claim: null,
      location_confidence: "source_point",
      location_assertion_status: "not_re_enriched",
      source_id: "tgaz_chgis",
      source_record_id: id,
      source_url: `https://example.test/${id}`,
      license: null,
      detail_path: null,
    },
  };
}

describe("display ranking", () => {
  test("nearest is stable and returns all available records", () => {
    const input = [feature("b", 2, "县"), feature("c", 1, "州"), feature("a", 1, "府")];
    expect(rankNearest(input).map((item) => item.id)).toEqual(["a", "c", "b"]);
    expect(rankNearest(input)).toHaveLength(3);
  });

  test("type round-robin retains minority types", () => {
    const input = Array.from({ length: 8 }, (_, index) =>
      feature(`county-${index}`, index + 1, "县"),
    );
    input.push(feature("prefecture", 2.5, "府"), feature("department", 3.5, "州"));
    expect(new Set(rankTypeDiverse(input).slice(0, 3).map((item) => item.properties.feature_type))).toEqual(
      new Set(["县", "府", "州"]),
    );
  });

  test("spatial ranking increases coverage when alternatives exist", () => {
    const input = [
      feature("near-1", 1, "县", 0.001, 0.001),
      feature("near-2", 2, "县", 0.002, 0.002),
      feature("near-3", 3, "县", 0.003, 0.003),
      feature("near-4", 4, "县", 0.004, 0.004),
      feature("east", 55, "县", 0.5, 0),
      feature("west", 56, "县", -0.5, 0),
      feature("north", 57, "县", 0, 0.5),
    ];
    const typeOnly = rankTypeDiverse(input).slice(0, 4);
    const spatial = rankTypeSpatial(input, 4);
    expect(spatialCoverageGridCells(spatial, anchor, 75)).toBeGreaterThan(
      spatialCoverageGridCells(typeOnly, anchor, 75),
    );
  });

  test("selection is deterministic, empty-safe, and preserves identity", () => {
    const input = [
      feature("one", 1, "县", 0.01),
      feature("two", 2, "府", -0.02),
      feature("three", 3, "县", 0, 0.03),
    ];
    const serialized = JSON.stringify(input);
    const first = rankTypeSpatial(input, 3).map((item) => item.id);
    const second = rankTypeSpatial(input, 3).map((item) => item.id);
    expect(first).toEqual(second);
    expect(new Set(first)).toEqual(new Set(input.map((item) => item.id)));
    expect(input.every((item) => item.properties.lineage_claim === null)).toBe(true);
    expect(JSON.stringify(input)).toBe(serialized);
    expect(rankTypeSpatial([], 30)).toEqual([]);
  });

  test("points and persistent labels are independent subsets", () => {
    const input = Array.from({ length: 40 }, (_, index) =>
      feature(
        `row-${index}`,
        index + 1,
        index % 2 ? "县" : "州",
        (index - 20) * 0.02,
        ((index % 7) - 3) * 0.04,
      ),
    );
    const selection = selectDisplay(input, "type_diverse_distance", anchor, 75);
    expect(selection.points).toHaveLength(30);
    expect(selection.labels.length).toBeLessThanOrEqual(12);
    expect(selection.points.length).toBeGreaterThan(selection.labels.length);
    expect(selection.labels.every((item) => selection.points.includes(item))).toBe(true);
    expect(selection.collisionMetricKind).toBe("estimated");
  });
});
