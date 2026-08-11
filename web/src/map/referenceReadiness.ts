import type { Map as MapLibreMap } from "maplibre-gl";

import {
  MODERN_REFERENCE_SOURCE_ID,
  R2_REFERENCE_COMPLETENESS_CONTRACT,
} from "./referenceLayers";


export const R2_REFERENCE_TIMEOUT_MS = 15_000;
export type R2ReferenceState = "loading" | "ready" | "degraded" | "failed";

export interface ReferenceReadinessSnapshot {
  state: R2ReferenceState;
  loadedCriticalLayerIds: string[];
  failedCriticalLayerIds: string[];
  timeoutReached: boolean;
  fallbackActive: boolean;
  lastError: string | null;
}

export interface ReferenceReadinessMonitor {
  handleError(error: unknown): void;
  stop(): void;
}

type TerminalCause = "progress" | "timeout";

function renderedLayerIds(map: MapLibreMap): string[] {
  const layerIds = [
    ...R2_REFERENCE_COMPLETENESS_CONTRACT.geometryLayerIds,
    ...R2_REFERENCE_COMPLETENESS_CONTRACT.labelLayerIds,
  ];
  return layerIds.filter((layerId) => {
    if (!map.getLayer(layerId)) return false;
    try {
      return map.queryRenderedFeatures({ layers: [layerId] }).length > 0;
    } catch {
      return false;
    }
  });
}

export function assessR2Reference(
  map: MapLibreMap,
  cause: TerminalCause = "progress",
  lastError: string | null = null,
): ReferenceReadinessSnapshot {
  const loadedCriticalLayerIds = renderedLayerIds(map);
  const loaded = new Set(loadedCriticalLayerIds);
  const hasGeometry = R2_REFERENCE_COMPLETENESS_CONTRACT.geometryLayerIds.some(
    (layerId) => loaded.has(layerId),
  );
  const hasLabels = R2_REFERENCE_COMPLETENESS_CONTRACT.labelLayerIds.some(
    (layerId) => loaded.has(layerId),
  );
  const timedOut = cause === "timeout";
  let state: R2ReferenceState = "loading";
  if (hasGeometry && hasLabels) {
    state = "ready";
  } else if (cause !== "progress" && (hasGeometry || hasLabels)) {
    state = "degraded";
  } else if (cause !== "progress") {
    state = "failed";
  }
  return {
    state,
    loadedCriticalLayerIds,
    failedCriticalLayerIds: [
      ...R2_REFERENCE_COMPLETENESS_CONTRACT.geometryLayerIds,
      ...R2_REFERENCE_COMPLETENESS_CONTRACT.labelLayerIds,
    ].filter((layerId) => !loaded.has(layerId)),
    timeoutReached: timedOut,
    fallbackActive: state === "failed",
    lastError,
  };
}

export function startR2ReferenceMonitor(
  map: MapLibreMap,
  onChange: (snapshot: ReferenceReadinessSnapshot) => void,
  timeoutMs = R2_REFERENCE_TIMEOUT_MS,
): ReferenceReadinessMonitor {
  let stopped = false;
  let state: R2ReferenceState = "loading";
  let timer: ReturnType<typeof setTimeout> | null = null;
  let lastError: string | null = null;

  const publish = (cause: TerminalCause) => {
    if (stopped || (state !== "loading" && cause === "progress")) return;
    const snapshot = assessR2Reference(map, cause, lastError);
    state = snapshot.state;
    onChange(snapshot);
    if (state !== "loading" && timer !== null) {
      clearTimeout(timer);
      timer = null;
    }
  };
  const onIdle = () => publish("progress");
  const onSourceData = (event: { sourceId?: string }) => {
    if (event.sourceId === MODERN_REFERENCE_SOURCE_ID) publish("progress");
  };

  map.on("idle", onIdle);
  map.on("sourcedata", onSourceData);
  onChange(assessR2Reference(map));
  timer = setTimeout(() => publish("timeout"), timeoutMs);

  return {
    handleError(error: unknown) {
      lastError = String(error);
      publish("progress");
    },
    stop() {
      if (stopped) return;
      stopped = true;
      if (timer !== null) clearTimeout(timer);
      map.off("idle", onIdle);
      map.off("sourcedata", onSourceData);
    },
  };
}
