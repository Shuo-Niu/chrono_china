import { expect, test } from "vitest";

import type { HistoricalFeature } from "../types";
import {
  prioritizeHistoricalLabelsAgainstAnchor,
  resolveLabelCollisions,
} from "./labelPriority";


function feature(id: string, lon: number, lat: number): HistoricalFeature {
  return {
    type: "Feature",
    id,
    geometry: { type: "Point", coordinates: [lon, lat] },
    properties: {
      tgaz_id: id,
      name: id,
      name_pinyin: null,
      feature_type: "县",
      valid_from: 1,
      valid_to: 2,
      parent_name: null,
      distance_to_anchor_km: 1,
      relation_to_anchor: "spatial_nearby",
      lineage_claim: null,
      location_confidence: "source_point",
      location_assertion_status: "resolved",
      source_id: "test",
      source_record_id: id,
      source_url: "https://example.invalid",
      license: null,
      detail_path: null,
    },
  };
}

test("collision order is modern anchor, historical label, ordinary modern label", () => {
  const rectangle: [number, number, number, number] = [10, 10, 30, 30];
  expect(
    resolveLabelCollisions([
      { id: "modern", role: "ordinary_modern_reference", rectangle },
      { id: "history", role: "historical_label", rectangle },
      { id: "anchor", role: "modern_anchor", rectangle },
    ]),
  ).toEqual(new Set(["anchor"]));
  expect(
    resolveLabelCollisions([
      { id: "modern", role: "ordinary_modern_reference", rectangle },
      { id: "history", role: "historical_label", rectangle },
    ]),
  ).toEqual(new Set(["history"]));
});

test("anchor collision hides only the historical label, never its point", () => {
  const atAnchor = feature("at-anchor", 116.4, 39.9);
  const west = feature("west", 115.9, 39.9);
  const result = prioritizeHistoricalLabelsAgainstAnchor(
    [atAnchor, west],
    new Set([atAnchor.id, west.id]),
    { lon: 116.4, lat: 39.9 },
    75,
    "北京（现代）",
  );
  expect(result.visibleLabelIds).toEqual(new Set(["west"]));
  expect(result.hiddenLabelIds).toEqual(new Set(["at-anchor"]));
  expect([atAnchor.id, west.id]).toHaveLength(2);
});
