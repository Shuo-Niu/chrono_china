import { describe, expect, test } from "vitest";

import type { HistoricalFeature } from "../types";
import {
  DISPLAY_FAMILY_REGISTRY,
  displayFamily,
  isVisibleForMode,
} from "./hierarchy";
import { selectZoomAwareDisplayLabels, zoomLabelLimit } from "./ranking";

function feature(id: string, type: string, lon: number): HistoricalFeature {
  return {
    type: "Feature",
    id,
    geometry: { type: "Point", coordinates: [lon, 0] },
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

describe("historical display hierarchy", () => {
  test("preserves raw type while mapping audited display families", () => {
    const polity = feature("qing", "政权", 0);
    expect(displayFamily(polity)).toBe("polity");
    expect(polity.properties.feature_type).toBe("政权");
    expect(displayFamily(feature("county", "县", 0))).toBe("county");
    expect(displayFamily(feature("jianling", "侨县", 0))).toBe("county");
    expect(displayFamily(feature("huaishuo", "军镇", 0))).toBe("regional_admin");
    expect(displayFamily(feature("yuan", "行省", 0))).toBe("high_admin");
    expect(displayFamily(feature("settlement", "村镇", 0))).toBe("settlement");
  });

  test("polity is display-filtered only in User Mode", () => {
    const polity = feature("qing", "政权", 0);
    expect(isVisibleForMode(polity, false)).toBe(false);
    expect(isVisibleForMode(polity, true)).toBe(true);
  });

  test("one registry covers every audited raw type and every user-visible legend family", () => {
    const auditedTypes = [
      "村镇", "县", "郡", "州", "府", "直隶州", "省", "政权",
      "侯国", "国", "路", "亭", "厅", "军", "王畿", "防镇",
      "行省", "省级", "侨郡", "军镇", "道", "监", "侨县",
    ];
    for (const rawType of auditedTypes) {
      expect(displayFamily(feature(rawType, rawType, 0))).not.toBe("other");
    }
    expect(
      DISPLAY_FAMILY_REGISTRY.filter((config) => config.userVisible).every(
        (config) => config.legend,
      ),
    ).toBe(true);
    expect(new Set(DISPLAY_FAMILY_REGISTRY.map((config) => config.shape)).size).toBeGreaterThan(3);
  });

  test("zoom label budget grows deterministically", () => {
    expect([zoomLabelLimit(6), zoomLabelLimit(7.4), zoomLabelLimit(9)]).toEqual([
      6,
      12,
      24,
    ]);
    const points = Array.from({ length: 30 }, (_, index) =>
      feature(`p-${index}`, index % 3 === 0 ? "郡" : "村镇", -0.6 + index * 0.04),
    );
    const counts = [6, 7.4, 9].map(
      (zoom) => selectZoomAwareDisplayLabels(points, { lon: 0, lat: 0 }, 75, zoom).labels.length,
    );
    expect(counts[0]).toBeLessThanOrEqual(counts[1]);
    expect(counts[1]).toBeLessThanOrEqual(counts[2]);
    expect(
      selectZoomAwareDisplayLabels(points, { lon: 0, lat: 0 }, 75, 9).labels.map(
        (item) => item.id,
      ),
    ).toEqual(
      selectZoomAwareDisplayLabels(points, { lon: 0, lat: 0 }, 75, 9).labels.map(
        (item) => item.id,
      ),
    );
  });
});
