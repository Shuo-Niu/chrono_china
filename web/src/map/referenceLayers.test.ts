import { expect, test } from "vitest";
import type { Map as MapLibreMap } from "maplibre-gl";

import {
  applyReferenceMode,
  isModernReferenceMapError,
  MODERN_REFERENCE_LAYER_IDS,
  MODERN_REFERENCE_SOURCE_ID,
  offlineReferenceGlyphsUrl,
  OFFLINE_REFERENCE_ARCHIVE_PATH,
  R2_REFERENCE_COMPLETENESS_CONTRACT,
} from "./referenceLayers";

class ReferenceMapStub {
  sources = new Map<string, unknown>();
  layers = new Map<string, { id: string }>();
  visibility = new Map<string, string>();
  failSource = false;

  getSource(id: string) { return this.sources.get(id); }
  getStyle() { return { sources: Object.fromEntries(this.sources), glyphs: undefined, sprite: undefined }; }
  setGlyphs() { return this; }
  setSprite() { return this; }
  addSource(id: string, source: unknown) {
    if (this.failSource) throw new Error("reference source unavailable");
    this.sources.set(id, source);
  }
  getLayer(id: string) { return this.layers.get(id); }
  addLayer(layer: { id: string }) { this.layers.set(layer.id, layer); }
  setLayoutProperty(id: string, _name: string, value: string) {
    this.visibility.set(id, value);
  }
}

function asMap(stub: ReferenceMapStub): MapLibreMap {
  return stub as unknown as MapLibreMap;
}

test("R0 remains source-free and all map modes use one packaged PMTiles source", () => {
  const stub = new ReferenceMapStub();
  expect(applyReferenceMode(asMap(stub), "r0_grid")).toEqual({
    status: "off",
    geometryLayerCount: 0,
    labelLayerCount: 0,
  });
  expect(stub.sources.size).toBe(0);

  const physical = applyReferenceMode(asMap(stub), "r1_physical");
  expect(physical.status).toBe("loading");
  expect(physical.geometryLayerCount).toBeGreaterThan(0);
  expect(physical.labelLayerCount).toBe(0);
  const source = stub.sources.get(MODERN_REFERENCE_SOURCE_ID) as { url: string };
  expect(source.url).toContain(`pmtiles://`);
  expect(source.url).toContain(OFFLINE_REFERENCE_ARCHIVE_PATH);
  expect(stub.visibility.get("reference-water")).toBe("visible");

  const minimal = applyReferenceMode(asMap(stub), "r2_minimal_modern");
  expect(minimal.geometryLayerCount).toBeGreaterThan(physical.geometryLayerCount);
  expect(minimal.labelLayerCount).toBeGreaterThan(0);
  expect(stub.visibility.get("reference-places_locality")).toBe("visible");
  expect(stub.visibility.get("reference-roads_major")).toBe("visible");

  const admin = applyReferenceMode(asMap(stub), "r3_modern_admin");
  expect(admin.geometryLayerCount).toBeGreaterThan(0);
  expect(admin.labelLayerCount).toBeGreaterThan(0);
  expect(stub.visibility.get("reference-boundaries")).toBe("visible");
  expect(stub.visibility.get("reference-places_region")).toBe("visible");

  const color = applyReferenceMode(asMap(stub), "r4_color_geography");
  expect(color.status).toBe("loading");
  expect(color.geometryLayerCount).toBeGreaterThan(minimal.geometryLayerCount);
  expect(color.labelLayerCount).toBeGreaterThan(minimal.labelLayerCount);
  expect(stub.visibility.get("reference-landcover")).toBe("visible");
  expect(stub.visibility.get("reference-landuse_park")).toBe("visible");
  expect(stub.sources.size).toBe(1);
});

test("packaged reference failure is contained and classified without remote-host heuristics", () => {
  const stub = new ReferenceMapStub();
  stub.failSource = true;
  expect(() => applyReferenceMode(asMap(stub), "r1_physical")).not.toThrow();
  expect(applyReferenceMode(asMap(stub), "r1_physical")).toMatchObject({
    status: "unavailable",
    geometryLayerCount: 0,
    labelLayerCount: 0,
  });
  expect(isModernReferenceMapError({ sourceId: MODERN_REFERENCE_SOURCE_ID })).toBe(true);
  expect(isModernReferenceMapError({
    error: { message: `Failed to fetch ${OFFLINE_REFERENCE_ARCHIVE_PATH}` },
  })).toBe(true);
  expect(isModernReferenceMapError({
    error: { message: "Failed to fetch https://tiles.openfreemap.org/planet" },
  })).toBe(false);
  expect(isModernReferenceMapError({ error: { message: "unrelated source failed" } })).toBe(false);
});

test("R2 completeness contract protects inland orientation and Qingdao water context", () => {
  expect(R2_REFERENCE_COMPLETENESS_CONTRACT.sceneRequirements).toEqual({
    beijing: ["reference-roads_major", "reference-places_locality"],
    chengdu: ["reference-roads_major", "reference-places_locality"],
    qingdao: ["reference-water", "reference-places_locality"],
  });
  for (const layerIds of Object.values(R2_REFERENCE_COMPLETENESS_CONTRACT.sceneRequirements)) {
    for (const layerId of layerIds) expect(MODERN_REFERENCE_LAYER_IDS).toContain(layerId);
  }
});

test("packaged glyph template preserves MapLibre fontstack and range tokens", () => {
  const glyphs = offlineReferenceGlyphsUrl();
  expect(glyphs).toContain("{fontstack}");
  expect(glyphs).toContain("{range}");
  expect(glyphs).not.toContain("%7Bfontstack%7D");
  expect(glyphs).not.toContain("%7Brange%7D");
});