import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import App, { confidenceLabel, formatYear, sourceNotePresentation } from "./App";
import { yearToOrdinal } from "./temporal/timelineScale";

const TYPES = {
  province: "\u7701",
  regional: "\u90e1",
};

function manifest(anchorId = "beijing") {
  return {
    anchor_id: anchorId,
    display_name: anchorId === "beijing" ? "\u5317\u4eac" : "\u897f\u5b89",
    modern_location: {
      lon: anchorId === "beijing" ? 116.4 : 108.94,
      lat: anchorId === "beijing" ? 39.9 : 34.3,
    },
    source: {
      provider: "GeoNames",
      record_id: anchorId === "beijing" ? "1816670" : "1790630",
      record_url: "https://www.geonames.org/test",
      retrieved_at: "2026-08-09T00:00:00Z",
      license_notice: "CC BY 4.0",
    },
    available_periods: [1911],
    default_period: 1911,
    periods: [{
      year: 1911,
      reason: "frozen regression fixture",
      active_feature_count: 0,
      added_since_previous: 0,
      removed_since_previous: 0,
      change_since_previous: 0,
      snapshot_signature_sha256: "fixture",
      rendered_feature_count: 0,
      slice_path: `anchors/${anchorId}/slices/1911.geojson`,
    }],
    default_radius_km: 75,
    coverage: { through_1911: "available" },
    history_source: {
      dataset: "TGAZ CHGIS CSV snapshot",
      snapshot_date: "2016-07-06",
      source_url: "https://example.test/index.csv",
      sha256: "abc",
      retrieved_at: "2026-08-09T00:00:00Z",
    },
    slices: { "1911": `anchors/${anchorId}/slices/1911.geojson` },
    semantic_notice: "Spatial neighborhood only",
  };
}

function temporalManifest(anchorId = "beijing") {
  return {
    schema_version: "1.0",
    generated_at: "2026-08-09T00:00:00Z",
    anchor_id: anchorId,
    display_name: anchorId === "beijing" ? "\u5317\u4eac" : "\u897f\u5b89",
    supported_snapshot_count: 1,
    earliest_supported_year: 1911,
    latest_supported_year: 1911,
    timeline_scale_scope: "per_anchor",
    timeline_display_algorithm: "frozen_fixture",
    semantic_notice: "supported snapshots only",
    snapshots: [{
      snapshot_id: `${anchorId}:1911`,
      anchor_id: anchorId,
      snapshot_year: 1911,
      display_year: formatYear(1911),
      broad_era_label: "\u6e05\u672b",
      shortcut_label: "\u6e05",
      regional_context_label: null,
      context_confidence: "high",
      source_status: "supported",
      source_ids: ["test_source"],
      notes: "fixture",
      whether_context_is_manual_reviewed: true,
      whether_context_is_safe_for_user_display: true,
      unresolved_conflicts: [],
      sequence_index: 0,
      sequence_count: 1,
      previous_snapshot_year: null,
      changes_from_previous: { added_records: 0, removed_records: 0, mechanical_only: true },
      timeline: {
        year: 1911,
        linear_normalized_position: 1,
        display_normalized_position: 1,
        position_adjusted: false,
        scale_scope: "per_anchor",
        display_algorithm: "frozen_fixture",
      },
    }],
  };
}

const compactIndex = {
  schema_version: "1.0",
  generated_at: "2026-08-10T00:00:00Z",
  fields: [
    "tgaz_id", "name", "name_pinyin", "valid_from", "valid_to", "lon", "lat",
    "feature_type", "parent_source_id", "parent_name", "location_confidence",
  ],
  source: {
    dataset: "TGAZ / CHGIS CSV spatial index",
    normalized_path: "data/intermediate/tgaz_points.jsonl",
    normalized_sha256: "abc",
    record_count: 5,
    canonical_uri_template: "http://maps.cga.harvard.edu/tgaz/placename/{TGAZ_ID}",
    license: null,
  },
  records: [
    ["province_1911", "\u7701\u7ea7\u8bb0\u5f55", null, 1911, 1911, 116.4, 39.9, TYPES.province, null, null, "source_point"],
    ["regional_1911", "\u533a\u57df\u8bb0\u5f55", null, 1911, 1911, 116.4, 39.9, TYPES.regional, null, null, "source_point"],
    ["bce_record", "\u5148\u79e6\u8bb0\u5f55", null, -201, -201, 116.4, 39.9, TYPES.regional, null, null, "source_point"],
    ["arbitrary_record", "\u4efb\u610f\u5e74\u8bb0\u5f55", null, 100, 200, 116.4, 39.9, TYPES.regional, null, null, "source_point"],
    ["hvd_88266", "\u5ba3\u5316\u5e9c", "Xuanhua Fu", 0, 1911, 116.4, 39.9, "\u5e9c", null, null, "source_point"],
  ],
};

function emptyCollection(anchorId = "beijing") {
  return {
    type: "FeatureCollection",
    metadata: {
      anchor_id: anchorId,
      anchor_display_name: anchorId,
      year: 1911,
      radius_km: 75,
      coverage_status: "available_through_1911",
      underlying_active_record_count: 0,
      active_feature_count: 0,
      period_selection: {},
      relation_semantics: "spatial_nearby only",
    },
    features: [],
  };
}

function jsonResponse(value: unknown) {
  return { ok: true, status: 200, json: async () => value } as Response;
}

function installFetchMock() {
  const responses: Record<string, unknown> = {
    "/explore/tgaz_compact.json": compactIndex,
    "/anchors/beijing/manifest.json": manifest("beijing"),
    "/anchors/xian/manifest.json": manifest("xian"),
    "/temporal_context/beijing.json": temporalManifest("beijing"),
    "/phase1_1/anchors/beijing/slices/1911.geojson": emptyCollection("beijing"),
  };
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const value = responses[String(input)];
    return value
      ? jsonResponse(value)
      : ({ ok: false, status: 404, json: async () => ({}) } as Response);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

async function renderReadyApp() {
  render(<App />);
  const map = screen.getByTestId("map");
  await waitFor(() => expect(map).toHaveAttribute("data-explore-index-status", "ready"));
  await waitFor(() => expect(map).toHaveAttribute("data-snapshot-year", "1911"));
  await waitFor(() => expect(map).toHaveAttribute("data-historical-point-count", "1"));
  return map;
}

test("formatters preserve BCE, confidence, and complete source-note semantics", () => {
  expect(formatYear(-221)).toBe("\u516c\u5143\u524d 221 \u5e74");
  expect(() => formatYear(0)).toThrow("\u4e0d\u5b58\u5728 0 \u5e74");
  expect(confidenceLabel("source_point")).toBe("\u6765\u6e90\u5750\u6807");
  expect(confidenceLabel("unresolved_conflict")).toBe("\u5750\u6807\u5b58\u5728\u672a\u89e3\u51b2\u7a81");
  const raw = "<p>complete note</p>\nsecond line";
  expect(sourceNotePresentation(raw)).toEqual({
    text: "complete note second line",
    raw,
    rawDiffers: true,
  });
});

test("User Mode exposes manual single-line layers, a concise timeline, and no modern-place selector", async () => {
  installFetchMock();
  const map = await renderReadyApp();
  expect(map).toHaveAttribute("data-view-mode", "unified_viewport");
  expect(screen.getByTestId("continuous-timeline")).toBeVisible();
  expect(screen.queryByLabelText("\u4ee3\u8868\u65f6\u671f")).not.toBeInTheDocument();
  expect(screen.queryByLabelText("\u81ea\u7531\u63a2\u7d22\u65f6\u95f4\u4e0e\u8303\u56f4")).not.toBeInTheDocument();
  expect(document.querySelector(".maplibregl-ctrl-scale")).toHaveTextContent("100 km");
  expect(document.querySelectorAll("[data-legend-family]")).toHaveLength(5);
  expect(screen.getByLabelText("\u5730\u56fe\u56fe\u4f8b")).toHaveTextContent("\u90e1\u3001\u5e9c\u3001\u5dde");
  expect(screen.queryByLabelText("\u73b0\u4ee3\u5730\u70b9")).not.toBeInTheDocument();
  expect(screen.getByLabelText("\u5730\u56fe\u56fe\u4f8b")).not.toHaveTextContent("\u7701\u7ea7 / \u738b\u757f");
  expect(screen.getByTestId("continuous-timeline")).not.toHaveTextContent("\u7cbe\u786e\u5e74\u4efd");
  expect(screen.getByTestId("continuous-timeline")).not.toHaveTextContent("\u62d6\u52a8\u67e5\u770b\u4efb\u610f\u6574\u6570\u5e74\u4efd");
  expect(screen.getByTestId("continuous-timeline")).not.toHaveTextContent("\u516c\u5143\u7eaa\u5e74\u65e0 0 \u5e74");
  expect(screen.getByLabelText("历史点显示模式")).toBeVisible();
  expect(screen.getByLabelText("背景地图模式")).toBeVisible();
});

test("point-only mode removes persistent labels without changing layers or interaction", async () => {
  installFetchMock();
  const map = await renderReadyApp();
  const regionalToggle = screen.getByRole("button", { name: /郡、府、州/ });
  await userEvent.click(regionalToggle);
  const enabledBefore = map.dataset.enabledDisplayFamilies;
  await userEvent.click(screen.getByRole("button", { name: "仅点" }));
  expect(map).toHaveAttribute("data-historical-display-mode", "point_only");
  expect(map).toHaveAttribute("data-historical-label-count", "0");
  expect(document.querySelector(".history-marker__label--persistent")).not.toBeInTheDocument();
  expect(document.querySelector(".history-marker__label--hover")).toBeInTheDocument();
  expect(document.querySelector(".history-marker")).toHaveAttribute("title");
  expect(map.dataset.enabledDisplayFamilies).toBe(enabledBefore);
  expect(regionalToggle).toHaveAttribute("aria-pressed", "false");
  await userEvent.click(document.querySelector<HTMLElement>(".history-marker")!);
  expect(screen.getByLabelText("历史地点详情")).toBeVisible();
});

test("basemap switching preserves historical state", async () => {
  installFetchMock();
  const map = await renderReadyApp();
  const before = {
    year: map.dataset.snapshotYear,
    ids: map.dataset.historicalPointIds,
    families: map.dataset.enabledDisplayFamilies,
    bbox: map.dataset.viewportBbox,
  };
  await userEvent.click(screen.getByRole("button", { name: "彩色地理" }));
  await waitFor(() => expect(map).toHaveAttribute("data-reference-effective-mode", "r4_color_geography"));
  expect({
    year: map.dataset.snapshotYear,
    ids: map.dataset.historicalPointIds,
    families: map.dataset.enabledDisplayFamilies,
    bbox: map.dataset.viewportBbox,
  }).toEqual(before);

});

test("colored basemap initialization failure falls back to minimal without clearing history", async () => {
  (globalThis as { __CHRONO_TEST_COLOR_BASEMAP_FAILURE__?: boolean })
    .__CHRONO_TEST_COLOR_BASEMAP_FAILURE__ = true;
  installFetchMock();
  const map = await renderReadyApp();
  const ids = map.dataset.historicalPointIds;
  await userEvent.click(screen.getByRole("button", { name: "彩色地理" }));
  await waitFor(() => expect(map).toHaveAttribute("data-reference-effective-mode", "r2_minimal_modern"));
  expect(map).toHaveAttribute("data-reference-mode", "r2_minimal_modern");
  expect(map).toHaveAttribute("data-historical-point-ids", ids);
});

test("exact-year updates retain keyed marker instances and never clear the layer while pending", async () => {
  installFetchMock();
  const map = await renderReadyApp();
  const timeline = screen.getByTestId("timeline-range");
  fireEvent.change(timeline, { target: { value: yearToOrdinal(150) } });
  await waitFor(() => expect(map).toHaveAttribute("data-query-result-year", "150"));
  const retained = document.querySelector<HTMLElement>(".history-marker")!;
  retained.dataset.instanceProbe = "stable";
  fireEvent.change(timeline, { target: { value: yearToOrdinal(151) } });
  expect(document.querySelector<HTMLElement>(".history-marker")?.dataset.instanceProbe).toBe("stable");
  await waitFor(() => expect(map).toHaveAttribute("data-query-result-year", "151"));
  expect(document.querySelector<HTMLElement>(".history-marker")?.dataset.instanceProbe).toBe("stable");
  expect(map).toHaveAttribute("data-retained-marker-recreation-count", "0");
  expect(map).toHaveAttribute("data-full-historical-layer-clear-count", "0");
  expect(map).toHaveAttribute("data-stale-commit-count", "0");
});

test("manual layer toggle updates point and co-location counts and persists across year changes", async () => {
  installFetchMock();
  const map = await renderReadyApp();
  const regionalToggle = screen.getByRole("button", { name: /\u90e1\u3001\u5e9c\u3001\u5dde/ });
  expect(regionalToggle).toHaveAttribute("aria-pressed", "true");
  expect(map).toHaveAttribute("data-co-located-group-count", "1");
  await userEvent.click(regionalToggle);
  await waitFor(() => expect(map).toHaveAttribute("data-eligible-record-count", "1"));
  expect(map).toHaveAttribute("data-historical-point-ids", "province_1911");
  expect(map).toHaveAttribute("data-co-located-group-count", "0");
  fireEvent.change(screen.getByTestId("timeline-range"), {
    target: { value: yearToOrdinal(-201) },
  });
  await waitFor(() => expect(map).toHaveAttribute("data-snapshot-year", "-201"));
  expect(regionalToggle).toHaveAttribute("aria-pressed", "false");
});

test("the timeline supports arbitrary CE, BCE, and rapid exact-year changes without year zero", async () => {
  installFetchMock();
  const map = await renderReadyApp();
  const timeline = screen.getByTestId("timeline-range");
  expect(timeline).toHaveAttribute("min", String(yearToOrdinal(-201)));
  expect(timeline).toHaveAttribute("max", String(yearToOrdinal(1911)));

  fireEvent.change(timeline, { target: { value: yearToOrdinal(-201) } });
  await waitFor(() => expect(map).toHaveAttribute("data-snapshot-year", "-201"));
  await waitFor(() => expect(map).toHaveAttribute("data-historical-point-ids", "bce_record"));
  expect(screen.getByTestId("timeline-current-year")).toHaveTextContent("\u516c\u5143\u524d 201 \u5e74");

  fireEvent.change(timeline, { target: { value: yearToOrdinal(150) } });
  fireEvent.change(timeline, { target: { value: yearToOrdinal(151) } });
  fireEvent.change(timeline, { target: { value: yearToOrdinal(123) } });
  await waitFor(() => expect(map).toHaveAttribute("data-snapshot-year", "123"));
  await waitFor(() => expect(map).toHaveAttribute(
    "data-historical-point-ids",
    "arbitrary_record,hvd_88266",
  ));
  expect(Number(map.dataset.timelineInputToMapLatencyMs)).toBeLessThan(100);
  expect(Number(map.dataset.exploreCancelledQueryCount)).toBeGreaterThan(0);
  expect(screen.getByTestId("timeline-current-year")).toHaveTextContent("\u516c\u5143 123 \u5e74");
});

test("co-located groups contain only members active in the selected exact year", async () => {
  installFetchMock();
  const map = await renderReadyApp();
  await waitFor(() => expect(map).toHaveAttribute("data-co-located-group-count", "1"));
  const initialGroup = document.querySelector<HTMLElement>(".history-marker--colocated")!;
  expect(initialGroup.dataset.memberIds).toBe("province_1911,hvd_88266,regional_1911");
  fireEvent.change(screen.getByTestId("timeline-range"), {
    target: { value: yearToOrdinal(-201) },
  });
  await waitFor(() => expect(map).toHaveAttribute("data-snapshot-year", "-201"));
  await waitFor(() => expect(map).toHaveAttribute("data-co-located-group-count", "0"));
  await waitFor(() => expect(map).toHaveAttribute("data-historical-point-ids", "bce_record"));
  expect(document.querySelector<HTMLElement>(".history-marker")?.dataset.memberIds).toBe("bce_record");
});

test("1911 宣化府 co-location and detail click cannot crash on a year-zero source sentinel", async () => {
  installFetchMock();
  const map = await renderReadyApp();
  await userEvent.click(document.querySelector<HTMLElement>(".history-marker--colocated")!);
  expect(screen.getByLabelText("同址历史记录")).toBeVisible();
  await userEvent.click(document.querySelector<HTMLElement>("[data-colocated-member-id='hvd_88266']")!);
  expect(screen.getByLabelText("历史地点详情")).toBeVisible();
  expect(screen.getByLabelText("历史地点详情")).toHaveTextContent("宣化府");
  expect(screen.getByLabelText("历史地点详情")).toHaveTextContent("来源未注明");
  expect(map).toHaveAttribute("data-snapshot-year", "1911");
  expect(screen.getByTestId("continuous-timeline")).toBeVisible();
});

test("modern-place fly-to is available only after entering Developer Mode", async () => {
  const fetchMock = installFetchMock();
  const map = await renderReadyApp();
  expect(screen.queryByLabelText("\u73b0\u4ee3\u5730\u70b9")).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "\u5f00\u53d1\u8005\u6a21\u5f0f" }));
  await userEvent.selectOptions(screen.getByLabelText("\u73b0\u4ee3\u5730\u70b9"), "xian");
  await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/anchors/xian/manifest.json"));
  expect(map).toHaveAttribute("data-view-mode", "unified_viewport");
  expect(map).toHaveAttribute("data-snapshot-year", "1911");
});

test("reference failure falls back without disabling the unified historical layer", async () => {
  (globalThis as { __CHRONO_TEST_REFERENCE_FAILURE__?: boolean })
    .__CHRONO_TEST_REFERENCE_FAILURE__ = true;
  installFetchMock();
  const map = await renderReadyApp();
  await waitFor(() => expect(map).toHaveAttribute("data-reference-effective-mode", "r0_grid"));
  expect(map).toHaveAttribute("data-reference-fallback-active", "true");
  expect(map).toHaveAttribute("data-historical-point-count", "1");
  expect(screen.getByTestId("continuous-timeline")).toBeVisible();
});
