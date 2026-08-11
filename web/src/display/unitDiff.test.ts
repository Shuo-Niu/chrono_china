import { describe, expect, test } from "vitest";
import type { HistoricalFeature } from "../types";
import type { DisplayUnit } from "./semanticZoom";
import { diffDisplayUnits } from "./unitDiff";

function feature(id: string): HistoricalFeature {
  return {
    type: "Feature",
    id,
    geometry: { type: "Point", coordinates: [116, 40] },
    properties: {
      tgaz_id: id,
      name: id,
      name_pinyin: null,
      feature_type: "县",
      valid_from: 1,
      valid_to: 1911,
      parent_name: null,
      distance_to_anchor_km: 0,
      relation_to_anchor: "viewport_member",
      lineage_claim: null,
      location_confidence: "source_point",
      location_assertion_status: "resolved",
      source_id: "test",
      source_record_id: id,
      source_url: `https://example.test/${id}`,
      license: null,
      detail_path: null,
    },
  };
}

function unit(id: string, memberIds: string[], coordinate: [number, number] = [116, 40]): DisplayUnit {
  const members = memberIds.map(feature);
  return {
    id,
    kind: members.length > 1 ? "colocated_group" : "feature",
    members,
    representative: members[0],
    coordinate,
    family: "county",
    label: memberIds.join("、"),
  };
}

describe("display-unit keyed diff", () => {
  test("separates retained, entering, and leaving units", () => {
    expect(diffDisplayUnits(
      [unit("a", ["a"]), unit("b", ["b"], [117, 40])],
      [unit("b", ["b"], [117, 40]), unit("c", ["c"], [118, 40])],
    )).toMatchObject({
      retainedIds: ["b"],
      enteringIds: ["c"],
      leavingIds: ["a"],
      changedGroupCoordinateKeys: [],
    });
  });

  test("reports only the co-location coordinate whose membership changed", () => {
    expect(diffDisplayUnits(
      [unit("group:a,b", ["a", "b"])],
      [unit("group:a,c", ["a", "c"])],
    ).changedGroupCoordinateKeys).toEqual(["116:40"]);
  });
});
