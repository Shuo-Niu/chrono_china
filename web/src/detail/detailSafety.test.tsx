import { render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import type { HistoricalFeature } from "../types";
import { DetailErrorBoundary } from "./DetailErrorBoundary";
import {
  formatDetailDistance,
  formatDetailYear,
  normalizeDetailPayload,
  sourceNotePresentation,
} from "./detailSafety";

const feature: HistoricalFeature = {
  type: "Feature",
  id: "hvd_88266",
  geometry: { type: "Point", coordinates: [115.05115, 40.61036] },
  properties: {
    tgaz_id: "hvd_88266",
    name: "宣化府",
    name_pinyin: "Xuanhua Fu",
    feature_type: "府",
    valid_from: 0,
    valid_to: 1911,
    parent_name: "直隶",
    distance_to_anchor_km: 1.25,
    relation_to_anchor: "viewport_member",
    lineage_claim: null,
    location_confidence: "source_point",
    location_assertion_status: "resolved",
    source_id: "tgaz_chgis_2016_07_06",
    source_record_id: "hvd_88266",
    source_url: "http://maps.cga.harvard.edu/tgaz/placename/hvd_88266",
    license: null,
    detail_path: null,
  },
};

test("宣化府 year-zero source sentinel is rendered defensively without changing it", () => {
  const detail = normalizeDetailPayload({}, feature, 1911);
  expect(detail.valid_from).toBe(0);
  expect(formatDetailYear(detail.valid_from)).toBe("来源未注明");
  expect(formatDetailYear(null)).toBe("暂不可用");
});

test("malformed optional fields, null notes, and long notes have safe presentations", () => {
  const detail = normalizeDetailPayload({
    source: null,
    parent_name: 12,
    distance_to_anchor_km: "bad",
    feature_type: ["unusual"],
  }, feature, 1911);
  expect(detail.parent_name).toBe("直隶");
  expect(detail.feature_type).toBe("府");
  expect(formatDetailDistance(detail.distance_to_anchor_km)).toBe("约 1.3 km");
  expect(sourceNotePresentation(null)).toEqual({ text: "", raw: null, rawDiffers: false });
  const long = `<p>${"long ".repeat(500)}</p>`;
  expect(sourceNotePresentation(long).text.length).toBeGreaterThan(1000);
});

test("detail error boundary contains a future record-specific render failure", () => {
  vi.spyOn(console, "error").mockImplementation(() => undefined);
  function BrokenDetail(): never {
    throw new Error("malformed optional field");
  }
  render(
    <main>
      <span>地图仍在</span>
      <DetailErrorBoundary onClose={() => undefined}>
        <BrokenDetail />
      </DetailErrorBoundary>
    </main>,
  );
  expect(screen.getByText("地图仍在")).toBeVisible();
  expect(screen.getByRole("alert")).toHaveTextContent("部分详情暂时无法显示");
});
