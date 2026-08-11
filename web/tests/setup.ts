import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

vi.mock("maplibre-gl", () => {
  class MockMap {
    private sources = new Map<string, unknown>();
    private layers = new Map<string, unknown>();
    addControl(control: object) {
      if (control.constructor.name === "MockScaleControl") {
        const scale = document.createElement("div");
        scale.className = "maplibregl-ctrl-scale";
        scale.textContent = "100 km";
        document.body.appendChild(scale);
      }
      return this;
    }
    addSource(id: string, source: unknown) {
      if ((globalThis as { __CHRONO_TEST_REFERENCE_FAILURE__?: boolean })
        .__CHRONO_TEST_REFERENCE_FAILURE__) {
        throw new Error("reference source unavailable");
      }
      this.sources.set(id, source);
      return this;
    }
    getSource(id: string) { return this.sources.get(id); }
    addLayer(layer: { id: string }) {
      if (
        layer.id.startsWith("reference-color") &&
        (globalThis as { __CHRONO_TEST_COLOR_BASEMAP_FAILURE__?: boolean })
          .__CHRONO_TEST_COLOR_BASEMAP_FAILURE__
      ) {
        throw new Error("color basemap layer unavailable");
      }
      this.layers.set(layer.id, layer);
      return this;
    }
    getLayer(id: string) { return this.layers.get(id); }
    setLayoutProperty() { return this; }
    isSourceLoaded(id: string) { return this.sources.has(id); }
    queryRenderedFeatures(options?: { layers?: string[] }) {
      const visibleInTest = new Set([
        "reference-major-road",
        "reference-settlement-label",
      ]);
      return options?.layers?.some((layerId) => visibleInTest.has(layerId)) ? [{}] : [];
    }
    easeTo() { return this; }
    getCenter() { return { lng: 116.39723, lat: 39.9075 }; }
    getZoom() { return 7.4; }
    project(coordinate: [number, number]) {
      return {
        x: 720 + (coordinate[0] - 116.39723) * 100,
        y: 400 - (coordinate[1] - 39.9075) * 100,
      };
    }
    getBounds() {
      return {
        getWest: () => 115.4,
        getSouth: () => 39.15,
        getEast: () => 117.4,
        getNorth: () => 40.65,
      };
    }
    on(event: string, callback: () => void) {
      if (event === "load") queueMicrotask(callback);
      return this;
    }
    off() { return this; }
    remove() { return undefined; }
  }

  class MockMarker {
    private element: HTMLElement;
    constructor(options: { element: HTMLElement; anchor?: string }) {
      this.element = options.element;
      this.element.dataset.maplibreAnchor = options.anchor ?? "center";
    }
    setLngLat() { return this; }
    addTo() {
      document.body.appendChild(this.element);
      return this;
    }
    remove() { this.element.remove(); }
  }

  class MockNavigationControl {}
  class MockScaleControl {}

  return {
    default: {
      Map: MockMap,
      Marker: MockMarker,
      NavigationControl: MockNavigationControl,
      ScaleControl: MockScaleControl,
    },
    Map: MockMap,
    Marker: MockMarker,
    NavigationControl: MockNavigationControl,
    ScaleControl: MockScaleControl,
  };
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  document.body.innerHTML = "";
  delete (globalThis as { __CHRONO_TEST_REFERENCE_FAILURE__?: boolean })
    .__CHRONO_TEST_REFERENCE_FAILURE__;
  delete (globalThis as { __CHRONO_TEST_COLOR_BASEMAP_FAILURE__?: boolean })
    .__CHRONO_TEST_COLOR_BASEMAP_FAILURE__;
});
