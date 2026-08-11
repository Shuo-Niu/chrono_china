import type { Map as MapLibreMap } from "maplibre-gl";
import { afterEach, expect, test, vi } from "vitest";

import {
  assessR2Reference,
  startR2ReferenceMonitor,
  type ReferenceReadinessSnapshot,
} from "./referenceReadiness";


class ReadinessMapStub {
  rendered = new Set<string>();
  handlers = new Map<string, Set<(event: { sourceId?: string }) => void>>();

  getLayer() { return {}; }
  queryRenderedFeatures(options?: { layers?: string[] }) {
    return options?.layers?.some((layerId) => this.rendered.has(layerId)) ? [{}] : [];
  }
  on(event: string, callback: (event: { sourceId?: string }) => void) {
    const callbacks = this.handlers.get(event) ?? new Set();
    callbacks.add(callback);
    this.handlers.set(event, callbacks);
  }
  off(event: string, callback: (event: { sourceId?: string }) => void) {
    this.handlers.get(event)?.delete(callback);
  }
  emit(event: string, payload: { sourceId?: string } = {}) {
    this.handlers.get(event)?.forEach((callback) => callback(payload));
  }
}

const asMap = (stub: ReadinessMapStub) => stub as unknown as MapLibreMap;

afterEach(() => vi.useRealTimers());

test("R2 starts loading and becomes ready only after rendered geometry and labels exist", () => {
  const stub = new ReadinessMapStub();
  expect(assessR2Reference(asMap(stub)).state).toBe("loading");
  stub.rendered.add("reference-major-road");
  expect(assessR2Reference(asMap(stub)).state).toBe("loading");
  stub.rendered.add("reference-settlement-label");
  expect(assessR2Reference(asMap(stub))).toMatchObject({
    state: "ready",
    fallbackActive: false,
  });
});

test("monitor publishes ready from actual critical content", () => {
  vi.useFakeTimers();
  const stub = new ReadinessMapStub();
  const states: ReferenceReadinessSnapshot[] = [];
  const monitor = startR2ReferenceMonitor(asMap(stub), (state) => states.push(state), 100);
  expect(states.at(-1)?.state).toBe("loading");
  stub.rendered.add("reference-major-road");
  stub.rendered.add("reference-settlement-label");
  stub.emit("idle");
  expect(states.at(-1)?.state).toBe("ready");
  vi.advanceTimersByTime(100);
  expect(states.at(-1)?.state).toBe("ready");
  monitor.stop();
});

test("timeout with partial content becomes degraded without fallback", () => {
  vi.useFakeTimers();
  const stub = new ReadinessMapStub();
  stub.rendered.add("reference-water");
  const states: ReferenceReadinessSnapshot[] = [];
  const monitor = startR2ReferenceMonitor(asMap(stub), (state) => states.push(state), 100);
  vi.advanceTimersByTime(100);
  expect(states.at(-1)).toMatchObject({
    state: "degraded",
    timeoutReached: true,
    fallbackActive: false,
  });
  monitor.stop();
});

test("timeout without rendered content fails and requests R0 fallback", () => {
  vi.useFakeTimers();
  const timeoutStub = new ReadinessMapStub();
  const timeoutStates: ReferenceReadinessSnapshot[] = [];
  startR2ReferenceMonitor(asMap(timeoutStub), (state) => timeoutStates.push(state), 100);
  vi.advanceTimersByTime(100);
  expect(timeoutStates.at(-1)).toMatchObject({
    state: "failed",
    timeoutReached: true,
    fallbackActive: true,
  });

});

test("one tile error stays loading and can recover when critical content renders", () => {
  vi.useFakeTimers();
  const stub = new ReadinessMapStub();
  const states: ReferenceReadinessSnapshot[] = [];
  const monitor = startR2ReferenceMonitor(asMap(stub), (state) => states.push(state), 100);
  monitor.handleError(new Error("one tile request failed"));
  expect(states.at(-1)).toMatchObject({
    state: "loading",
    timeoutReached: false,
    fallbackActive: false,
    lastError: "Error: one tile request failed",
  });
  stub.rendered.add("reference-major-road");
  stub.rendered.add("reference-settlement-label");
  stub.emit("idle");
  expect(states.at(-1)).toMatchObject({
    state: "ready",
    fallbackActive: false,
    lastError: "Error: one tile request failed",
  });
  monitor.stop();
});

test("source errors become failed only at timeout when no content ever renders", () => {
  vi.useFakeTimers();
  const stub = new ReadinessMapStub();
  const states: ReferenceReadinessSnapshot[] = [];
  startR2ReferenceMonitor(asMap(stub), (state) => states.push(state), 100)
    .handleError(new Error("all tile requests failed"));
  vi.advanceTimersByTime(100);
  expect(states.at(-1)).toMatchObject({
    state: "failed",
    timeoutReached: true,
    fallbackActive: true,
    lastError: "Error: all tile requests failed",
  });
});
