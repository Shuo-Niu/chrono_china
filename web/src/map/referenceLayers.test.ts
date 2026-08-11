import { expect, test } from "vitest";
import type { Map as MapLibreMap } from "maplibre-gl";

import {
  applyReferenceMode,
  isModernReferenceMapError,
  MODERN_REFERENCE_LAYER_IDS,
  MODERN_REFERENCE_SOURCE_ID,
  R2_REFERENCE_COMPLETENESS_CONTRACT,
} from "./referenceLayers";


class ReferenceMapStub {
  sources = new Map<string, unknown>();
  layers = new Map<string, { id: string }>();
  visibility = new Map<string, string>();
  failSource = false;

  getSource(id: string) { return this.sources.get(id); }
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

test("R0 remains source-free and reference modes add only their controlled layers", () => {
  const stub = new ReferenceMapStub();
  expect(applyReferenceMode(asMap(stub), "r0_grid")).toEqual({
    status: "off",
    geometryLayerCount: 0,
    labelLayerCount: 0,
  });
  expect(stub.sources.size).toBe(0);

  expect(applyReferenceMode(asMap(stub), "r1_physical")).toMatchObject({
    status: "loading",
    geometryLayerCount: 2,
    labelLayerCount: 0,
  });
  expect(stub.sources.has(MODERN_REFERENCE_SOURCE_ID)).toBe(true);
  expect(stub.layers.size).toBe(2);
  expect(stub.visibility.get("reference-water")).toBe("visible");

  expect(applyReferenceMode(asMap(stub), "r2_minimal_modern")).toMatchObject({
    geometryLayerCount: 3,
    labelLayerCount: 1,
  });
  expect(stub.visibility.get("reference-settlement-label")).toBe("visible");
  expect(stub.visibility.get("reference-major-road")).toBe("visible");
  expect(stub.visibility.get("reference-modern-admin-boundary")).toBe("none");

  expect(applyReferenceMode(asMap(stub), "r3_modern_admin")).toMatchObject({
    geometryLayerCount: 3,
    labelLayerCount: 1,
  });
  expect(stub.visibility.get("reference-modern-admin-boundary")).toBe("visible");
  expect(stub.visibility.get("reference-modern-admin-label")).toBe("visible");

  expect(applyReferenceMode(asMap(stub), "r4_color_geography")).toMatchObject({
    status: "loading",
    geometryLayerCount: 8,
    labelLayerCount: 2,
  });
  expect(stub.visibility.get("reference-color-landcover")).toBe("visible");
  expect(stub.visibility.get("reference-color-water")).toBe("visible");
  expect(stub.visibility.get("reference-color-building")).toBe("visible");
  expect(stub.visibility.get("reference-modern-admin-boundary")).toBe("none");
});

test("reference source failure is contained and classified", () => {
  const stub = new ReferenceMapStub();
  stub.failSource = true;
  expect(() => applyReferenceMode(asMap(stub), "r1_physical")).not.toThrow();
  expect(applyReferenceMode(asMap(stub), "r1_physical")).toMatchObject({
    status: "unavailable",
    geometryLayerCount: 0,
    labelLayerCount: 0,
  });
  expect(
    isModernReferenceMapError({ sourceId: MODERN_REFERENCE_SOURCE_ID }),
  ).toBe(true);
  expect(
    isModernReferenceMapError({ error: { message: "unrelated source failed" } }),
  ).toBe(false);
  expect(
    isModernReferenceMapError({
      error: {
        message: "Failed to fetch https://tiles.openfreemap.org/planet/0/0/0.pbf",
      },
    }),
  ).toBe(true);
  expect(
    isModernReferenceMapError({
      error: {
        message: "Failed to fetch https://tiles.openfreemap.org.evil.example/planet",
      },
    }),
  ).toBe(false);
  expect(
    isModernReferenceMapError({
      error: {
        message: "Failed to fetch https://evil.example/tiles.openfreemap.org",
      },
    }),
  ).toBe(false);
  expect(
    isModernReferenceMapError({
      error: {
        message: "Failed to fetch https://tiles.openfreemap.org@evil.example/planet",
      },
    }),
  ).toBe(false);
});

test("R2 completeness contract protects inland orientation and Qingdao water context", () => {
  expect(R2_REFERENCE_COMPLETENESS_CONTRACT.sceneRequirements).toEqual({
    beijing: ["reference-major-road", "reference-settlement-label"],
    chengdu: ["reference-major-road", "reference-settlement-label"],
    qingdao: ["reference-water", "reference-settlement-label"],
  });
  for (const layerIds of Object.values(
    R2_REFERENCE_COMPLETENESS_CONTRACT.sceneRequirements,
  )) {
    for (const layerId of layerIds) {
      expect(MODERN_REFERENCE_LAYER_IDS).toContain(layerId);
    }
  }
});
