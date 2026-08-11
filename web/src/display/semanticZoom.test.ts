import { describe, expect, test } from "vitest";

import type { HistoricalFeature } from "../types";
import {
  groupCoLocatedFeatures,
  selectSemanticZoomUnits,
  stableLabelPlacement,
} from "./semanticZoom";

function feature(id: string, type: string, lon: number, lat = 0): HistoricalFeature {
  return {
    type: "Feature",
    id,
    geometry: { type: "Point", coordinates: [lon, lat] },
    properties: {
      tgaz_id: id,
      name: id,
      name_pinyin: null,
      feature_type: type,
      valid_from: 1,
      valid_to: 2,
      parent_name: null,
      distance_to_anchor_km: Math.abs(lon) * 111,
      relation_to_anchor: "spatial_nearby",
      lineage_claim: null,
      location_confidence: "source_point",
      location_assertion_status: "resolved",
      source_id: "tgaz_chgis",
      source_record_id: id,
      source_url: `https://example.test/${id}`,
      license: null,
      detail_path: null,
    },
  };
}

describe("manual historical layer display units", () => {
  test("zoom never mutates family eligibility and explicit toggles are the only family filter", () => {
    const features = [
      feature("province", "\u7701", -0.5),
      feature("prefecture", "\u90e1", 0),
      feature("county", "\u53bf", 0.5),
      feature("village", "\u6751\u9547", 1),
    ];
    const enabled = new Set(["high_admin", "county"] as const);
    const low = selectSemanticZoomUnits(features, { lon: 0, lat: 0 }, 200, 6.2, enabled);
    const maximum = selectSemanticZoomUnits(features, { lon: 0, lat: 0 }, 200, 11, enabled);
    expect(low.eligibleFamilies).toEqual(["high_admin", "county"]);
    expect(low.units.map((unit) => unit.id)).toEqual(["province", "county"]);
    expect(maximum.units.map((unit) => unit.id)).toEqual(low.units.map((unit) => unit.id));
    expect(maximum.semanticHiddenFeatureCount).toBe(2);
  });

  test("co-location membership is recalculated after a family is turned off", () => {
    const features = [
      feature("province", "省", 1, 1),
      feature("prefecture", "郡", 1, 1),
    ];
    const all = selectSemanticZoomUnits(
      features, { lon: 1, lat: 1 }, 75, 8, new Set(["high_admin", "regional_admin"]),
    );
    const highOnly = selectSemanticZoomUnits(
      features, { lon: 1, lat: 1 }, 75, 8, new Set(["high_admin"]),
    );
    expect(all.units[0].members).toHaveLength(2);
    expect(highOnly.units[0].members.map((item) => item.id)).toEqual(["province"]);
  });

  test("co-located records remain separate members of one exact-coordinate group", () => {
    const features = [
      feature("hvd_112122", "\u90e1", 109.06952, 34.36034),
      feature("hvd_112123", "\u90e1", 109.06952, 34.36034),
      feature("hvd_112126", "\u90e1", 109.06952, 34.36034),
    ];
    const [group] = groupCoLocatedFeatures(features);
    expect(group.kind).toBe("colocated_group");
    expect(group.members.map((item) => item.id).sort()).toEqual([
      "hvd_112122", "hvd_112123", "hvd_112126",
    ]);
    expect(group.coordinate).toEqual([109.06952, 34.36034]);
  });

  test("co-located grouping does not suppress another eligible same-family unit", () => {
    const selection = selectSemanticZoomUnits(
      [
        feature("near-singleton", "\u90e1", 0, 0),
        feature("group-a", "\u90e1", 0.00001, 0),
        feature("group-b", "\u90e1", 0.00001, 0),
      ],
      { lon: 0, lat: 0 },
      75,
      7.4,
    );
    expect(selection.units).toHaveLength(2);
    expect(selection.units.map((unit) => unit.kind)).toContain("colocated_group");
    expect(selection.collisionHiddenUnitCount).toBe(0);
  });

  test("same zoom and active records produce the same eligibility across map centers", () => {
    const features = [feature("first", "\u90e1", 0), feature("second", "\u90e1", 0.00001)];
    const first = selectSemanticZoomUnits(features, { lon: 0, lat: 0 }, 75, 7.4);
    const panned = selectSemanticZoomUnits(features, { lon: 110, lat: 40 }, 1200, 7.4);
    expect(first.units.map((unit) => unit.id)).toEqual(panned.units.map((unit) => unit.id));
    expect(first.collisionHiddenUnitCount).toBe(0);
  });

  test("label placement is stable inside a zoom bucket", () => {
    expect(stableLabelPlacement("hvd_123", 8.7)).toEqual(
      stableLabelPlacement("hvd_123", 10.4),
    );
  });
});
