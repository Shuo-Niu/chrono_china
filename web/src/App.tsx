import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import * as maplibregl from "maplibre-gl";
import type { Map as MapLibreMap, Marker } from "maplibre-gl";
import type {
  AnchorManifest,
  DetailCard,
  HistoricalFeature,
  HistoricalFeatureCollection,
  TemporalContextManifest,
} from "./types";
import {
  DISPLAY_STRATEGIES,
  selectDisplay,
  selectZoomAwareDisplayLabels,
  type DisplayStrategy,
} from "./display/ranking";
import {
  DISPLAY_FAMILY_REGISTRY,
  displayFamily,
  familyConfig,
  isVisibleForMode,
  markerVariables,
  type DisplayFamily,
} from "./display/hierarchy";
import {
  selectSemanticZoomUnits,
  stableLabelPlacement,
  type DisplayUnit,
} from "./display/semanticZoom";
import { diffDisplayUnits } from "./display/unitDiff";
import { prioritizeHistoricalLabelsAgainstAnchor } from "./map/labelPriority";
import {
  applyReferenceMode,
  isModernReferenceMapError,
  MODERN_REFERENCE_GLYPHS_URL,
  MODERN_REFERENCE_SOURCE_ID,
  REFERENCE_MODES,
  referenceMode,
  type ReferenceModeId,
  type ReferenceSourceStatus,
} from "./map/referenceLayers";
import {
  startR2ReferenceMonitor,
  type ReferenceReadinessMonitor,
  type ReferenceReadinessSnapshot,
} from "./map/referenceReadiness";
import { TemporalRail } from "./temporal/TemporalRail";
import { ContinuousTimeline } from "./temporal/ContinuousTimeline";
import { formatHistoricalYear } from "./temporal/temporal";
import {
  compactIndexYearRange,
  coverageStatusLabel,
  parseCompactIndex,
  queryCompactIndex,
  type CompactHistoricalIndex,
  type ViewportCoverageStatus,
  type ViewportQueryResult,
} from "./explore/viewportQuery";
import { DetailErrorBoundary } from "./detail/DetailErrorBoundary";
import {
  detailFromActiveFeature,
  formatDetailDistance,
  formatDetailYear,
  normalizeDetailPayload,
  sourceNotePresentation,
} from "./detail/detailSafety";

export { sourceNotePresentation } from "./detail/detailSafety";

declare global {
  interface Window {
    __CHRONOCHINA_QA_MAP__?: MapLibreMap;
  }
}

const ANCHORS = [
  { id: "beijing", name: "北京" },
  { id: "xian", name: "西安" },
  { id: "chengdu", name: "成都" },
  { id: "qingdao", name: "青岛" },
  { id: "qufu", name: "曲阜" },
];

const blankStyle: maplibregl.StyleSpecification = {
  version: 8,
  glyphs: MODERN_REFERENCE_GLYPHS_URL,
  sources: {},
  layers: [
    {
      id: "background",
      type: "background",
      paint: { "background-color": "#e9e3d8" },
    },
  ],
};

export function formatYear(year: number): string {
  return formatHistoricalYear(year);
}

export function confidenceLabel(value: string): string {
  return value === "source_point" ? "来源坐标" : "坐标存在未解冲突";
}

type HistoricalDisplayMode = "point_label" | "point_only";

function knownValue(value: string | null): string {
  return value && value !== "\\N" ? value : "上级未知 / 未加载";
}

export default function App() {
  const mapContainer = useRef<HTMLDivElement>(null);
  const historyMarkerOverlay = useRef<HTMLDivElement>(null);
  const map = useRef<MapLibreMap | null>(null);
  const anchorMarker = useRef<Marker | null>(null);
  const referenceMonitor = useRef<ReferenceReadinessMonitor | null>(null);
  const exploreQuerySequence = useRef(0);
  const exploreInputAt = useRef<number | null>(null);
  const previousRenderedUnits = useRef<DisplayUnit[]>([]);
  const previousMarkerElements = useRef<Map<string, Element>>(new Map());
  const [mapReady, setMapReady] = useState(false);
  const [mapZoom, setMapZoom] = useState(7.4);
  const [mapRevision, setMapRevision] = useState(0);
  const [viewMode] = useState<"focus" | "explore">("explore");
  const [searchAnchorId, setSearchAnchorId] = useState("beijing");
  const [exploreYear, setExploreYear] = useState(1911);
  const [exploreYearDraft, setExploreYearDraft] = useState("1911");
  const [viewportBbox, setViewportBbox] = useState<[number, number, number, number] | null>(null);
  const [exploreIndex, setExploreIndex] = useState<CompactHistoricalIndex | null>(null);
  const [exploreIndexStatus, setExploreIndexStatus] = useState<"idle" | "loading" | "ready" | "failed">("idle");
  const [exploreIndexLoadMs, setExploreIndexLoadMs] = useState<number | null>(null);
  const [exploreResult, setExploreResult] = useState<ViewportQueryResult | null>(null);
  const [exploreCoverageStatus, setExploreCoverageStatus] =
    useState<ViewportCoverageStatus>("insufficient_source_coverage");
  const [exploreCoverageReason, setExploreCoverageReason] = useState("视口数据尚未查询");
  const [exploreCommittedSequence, setExploreCommittedSequence] = useState(0);
  const [exploreCancelledCount, setExploreCancelledCount] = useState(0);
  const [exploreStaleCommitCount, setExploreStaleCommitCount] = useState(0);
  const [exploreInputToMapLatencyMs, setExploreInputToMapLatencyMs] = useState<number | null>(null);
  const [activeAnchorId, setActiveAnchorId] = useState("beijing");
  const [manifest, setManifest] = useState<AnchorManifest | null>(null);
  const [temporalContext, setTemporalContext] =
    useState<TemporalContextManifest | null>(null);
  const [year, setYear] = useState<number | null>(null);
  const [collection, setCollection] = useState<HistoricalFeatureCollection | null>(null);
  const [detail, setDetail] = useState<DetailCard | null>(null);
  const [selectedGroup, setSelectedGroup] = useState<DisplayUnit | null>(null);
  const [displayStrategy, setDisplayStrategy] =
    useState<DisplayStrategy>("type_diverse_spatial");
  const [historicalDisplayMode, setHistoricalDisplayMode] =
    useState<HistoricalDisplayMode>("point_label");
  const [referenceModeId, setReferenceModeId] =
    useState<ReferenceModeId>("r2_minimal_modern");
  const [developerMode, setDeveloperMode] = useState(false);
  const [enabledFamilies, setEnabledFamilies] = useState<Set<DisplayFamily>>(
    () => new Set(
      DISPLAY_FAMILY_REGISTRY.filter((config) => config.userVisible).map((config) => config.id),
    ),
  );
  const [referenceSourceStatus, setReferenceSourceStatus] =
    useState<ReferenceSourceStatus>("off");
  const [referenceLayerCounts, setReferenceLayerCounts] = useState({
    geometry: 0,
    labels: 0,
  });
  const [effectiveReferenceModeId, setEffectiveReferenceModeId] =
    useState<ReferenceModeId>("r2_minimal_modern");
  const [referenceReadiness, setReferenceReadiness] =
    useState<ReferenceReadinessSnapshot | null>(null);
  const [retainedMarkerRecreationCount, setRetainedMarkerRecreationCount] = useState(0);
  const [fullLayerClearCount] = useState(0);
  const [maxVisiblePointCount, setMaxVisiblePointCount] = useState(0);
  const [lastDisplayDiff, setLastDisplayDiff] = useState({
    retained: 0,
    entering: 0,
    leaving: 0,
    changedGroups: 0,
  });
  const [status, setStatus] = useState("正在载入真实数据…");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!mapContainer.current || map.current) return;
    const instance = new maplibregl.Map({
      container: mapContainer.current,
      style: blankStyle,
      center: [116.39723, 39.9075],
      zoom: 7.4,
      attributionControl: false,
    });
    instance.addControl(
      new maplibregl.NavigationControl({ showCompass: false }),
      "bottom-right",
    );
    let markerAnimationFrame: number | null = null;
    const redrawProjectedMarkers = () => {
      if (markerAnimationFrame !== null) return;
      markerAnimationFrame = window.requestAnimationFrame(() => {
        markerAnimationFrame = null;
        setMapRevision((revision) => revision + 1);
      });
    };
    instance.addControl(
      new maplibregl.ScaleControl({ maxWidth: 120, unit: "metric" }),
      "bottom-right",
    );
    const recordViewport = () => {
      if (!mapContainer.current) return;
      const center = instance.getCenter();
      mapContainer.current.dataset.mapMoving = "false";
      mapContainer.current.dataset.mapCenter =
        `${center.lng.toFixed(6)},${center.lat.toFixed(6)}`;
      mapContainer.current.dataset.mapZoom = instance.getZoom().toFixed(4);
      setMapZoom(instance.getZoom());
      const bounds = instance.getBounds();
      setViewportBbox([
        bounds.getWest(),
        bounds.getSouth(),
        bounds.getEast(),
        bounds.getNorth(),
      ]);
      redrawProjectedMarkers();
    };
    instance.on("load", () => {
      recordViewport();
      setMapReady(true);
    });
    instance.on("movestart", () => {
      if (mapContainer.current) mapContainer.current.dataset.mapMoving = "true";
    });
    instance.on("move", redrawProjectedMarkers);
    instance.on("moveend", recordViewport);
    instance.on("sourcedata", (event) => {
      if (
        event.sourceId === MODERN_REFERENCE_SOURCE_ID &&
        event.isSourceLoaded &&
        mapContainer.current?.dataset.referenceMode !== "r0_grid" &&
        mapContainer.current?.dataset.referenceMode !== "r2_minimal_modern"
      ) {
        setReferenceSourceStatus("ready");
      }
    });
    instance.on("error", (event) => {
      if (
        isModernReferenceMapError(event) &&
        mapContainer.current?.dataset.referenceMode !== "r0_grid"
      ) {
        if (mapContainer.current?.dataset.referenceMode === "r2_minimal_modern") {
          referenceMonitor.current?.handleError(event.error ?? event);
        } else if (mapContainer.current?.dataset.referenceMode === "r4_color_geography") {
          setReferenceSourceStatus("unavailable");
          setReferenceModeId("r2_minimal_modern");
        } else {
          setReferenceSourceStatus("unavailable");
        }
      }
    });
    map.current = instance;
    if (import.meta.env.DEV) {
      window.__CHRONOCHINA_QA_MAP__ = instance;
    }
    return () => {
      referenceMonitor.current?.stop();
      anchorMarker.current?.remove();
      if (markerAnimationFrame !== null) window.cancelAnimationFrame(markerAnimationFrame);
      instance.remove();
      map.current = null;
      if (window.__CHRONOCHINA_QA_MAP__ === instance) {
        delete window.__CHRONOCHINA_QA_MAP__;
      }
    };
  }, []);

  useEffect(() => {
    if (exploreIndex || exploreIndexStatus === "loading") return;
    let cancelled = false;
    setExploreIndexStatus("loading");
    const started = performance.now();
    void fetch("/explore/tgaz_compact.json")
      .then((response) => {
        if (!response.ok) throw new Error(`compact index HTTP ${response.status}`);
        return response.json();
      })
      .then((payload) => {
        if (cancelled) return;
        setExploreIndex(parseCompactIndex(payload));
        setExploreIndexLoadMs(performance.now() - started);
        setExploreIndexStatus("ready");
      })
      .catch((reason) => {
        if (cancelled) return;
        setExploreIndexStatus("failed");
        setExploreCoverageStatus("query_failed");
        setExploreCoverageReason(String(reason));
      });
    return () => {
      cancelled = true;
    };
  }, [exploreIndex]);

  useEffect(() => {
    if (!exploreIndex || !viewportBbox) return;
    const sequence = ++exploreQuerySequence.current;
    let completed = false;
    const frame = window.requestAnimationFrame(() => {
      completed = true;
      try {
        const result = queryCompactIndex(exploreIndex, viewportBbox, exploreYear);
        if (sequence !== exploreQuerySequence.current) {
          setExploreStaleCommitCount((count) => count + 1);
          return;
        }
        setExploreResult(result);
        setExploreCoverageStatus(result.coverageStatus);
        setExploreCoverageReason(result.coverageReason);
        setExploreCommittedSequence(sequence);
        if (exploreInputAt.current !== null) {
          setExploreInputToMapLatencyMs(performance.now() - exploreInputAt.current);
        }
        exploreInputAt.current = null;
      } catch (reason) {
        if (sequence !== exploreQuerySequence.current) {
          setExploreStaleCommitCount((count) => count + 1);
          return;
        }
        setExploreResult(null);
        setExploreCoverageStatus("query_failed");
        setExploreCoverageReason(String(reason));
        setExploreCommittedSequence(sequence);
        if (exploreInputAt.current !== null) {
          setExploreInputToMapLatencyMs(performance.now() - exploreInputAt.current);
        }
        exploreInputAt.current = null;
      }
    });
    return () => {
      window.cancelAnimationFrame(frame);
      if (!completed && sequence === exploreQuerySequence.current) {
        exploreQuerySequence.current += 1;
        setExploreCancelledCount((count) => count + 1);
      }
    };
  }, [exploreIndex, exploreYear, viewportBbox]);

  useEffect(() => {
    if (!mapReady || !map.current || !mapContainer.current) return;
    referenceMonitor.current?.stop();
    referenceMonitor.current = null;
    mapContainer.current.dataset.referenceMode = referenceModeId;
    const result = applyReferenceMode(map.current, referenceModeId);
    setReferenceLayerCounts({
      geometry: result.geometryLayerCount,
      labels: result.labelLayerCount,
    });
    setReferenceSourceStatus(result.status);
    setEffectiveReferenceModeId(referenceModeId);
    setReferenceReadiness(null);
    if (referenceModeId === "r4_color_geography" && result.status === "unavailable") {
      setReferenceModeId("r2_minimal_modern");
      return;
    }
    if (referenceModeId === "r2_minimal_modern" && result.status === "loading") {
      const currentMap = map.current;
      referenceMonitor.current = startR2ReferenceMonitor(currentMap, (snapshot) => {
        setReferenceReadiness(snapshot);
        setReferenceSourceStatus(snapshot.state);
        if (snapshot.fallbackActive) {
          applyReferenceMode(currentMap, "r0_grid");
          setEffectiveReferenceModeId("r0_grid");
        }
      });
      return () => {
        referenceMonitor.current?.stop();
        referenceMonitor.current = null;
      };
    }
    if (referenceModeId === "r2_minimal_modern" && result.status === "unavailable") {
      const snapshot: ReferenceReadinessSnapshot = {
        state: "failed",
        loadedCriticalLayerIds: [],
        failedCriticalLayerIds: [],
        timeoutReached: false,
        fallbackActive: true,
        lastError: result.error ?? "reference initialization failed",
      };
      setReferenceReadiness(snapshot);
      setReferenceSourceStatus("failed");
      applyReferenceMode(map.current, "r0_grid");
      setEffectiveReferenceModeId("r0_grid");
      return;
    }
    if (
      result.status === "loading" &&
      map.current.isSourceLoaded(MODERN_REFERENCE_SOURCE_ID)
    ) {
      setReferenceSourceStatus("ready");
    }
  }, [mapReady, referenceModeId]);

  useEffect(() => {
    let cancelled = false;
    setManifest(null);
    setTemporalContext(null);
    setYear(null);
    setCollection(null);
    setDetail(null);
    setSelectedGroup(null);
    setError(null);
    setStatus("正在载入现代锚点与时期清单…");
    Promise.all([
      fetch(`/anchors/${activeAnchorId}/manifest.json`).then((response) => {
        if (!response.ok) throw new Error(`anchor manifest HTTP ${response.status}`);
        return response.json() as Promise<AnchorManifest>;
      }),
      fetch(`/temporal_context/${activeAnchorId}.json`).then((response) => {
        if (!response.ok) throw new Error(`temporal context HTTP ${response.status}`);
        return response.json() as Promise<TemporalContextManifest>;
      }),
    ])
      .then(([loaded, loadedTemporalContext]) => {
        if (cancelled) return;
        if (
          loadedTemporalContext.anchor_id !== loaded.anchor_id ||
          loadedTemporalContext.snapshots.some(
            (snapshot) => !loaded.available_periods.includes(snapshot.snapshot_year),
          )
        ) {
          throw new Error("temporal context does not match frozen anchor snapshots");
        }
        setManifest(loaded);
        setTemporalContext(loadedTemporalContext);
        setYear(loaded.default_period ?? loaded.available_periods[0] ?? null);
        map.current?.easeTo({
          center: [loaded.modern_location.lon, loaded.modern_location.lat],
          zoom: 7.4,
          duration: 450,
        });
      })
      .catch((reason: unknown) => {
        if (!cancelled) {
          setError(`现代锚点载入失败：${String(reason)}`);
          setStatus("锚点数据不可用");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [activeAnchorId]);

  useEffect(() => {
    if (!manifest || year === null) return;
    if (!manifest.slices[String(year)]) {
      setCollection(null);
      setStatus("该时期尚未接入；没有沿用其他年份的数据");
      return;
    }
    let cancelled = false;
    setCollection(null);
    setDetail(null);
    setSelectedGroup(null);
    setError(null);
    setStatus(`${formatYear(year)} · 正在载入历史切片…`);
    const activeSlicePath = `phase1_1/anchors/${manifest.anchor_id}/slices/${year}.geojson`;
    fetch(`/${activeSlicePath}`)
      .then((response) => {
        if (!response.ok) throw new Error(`historical slice HTTP ${response.status}`);
        return response.json() as Promise<HistoricalFeatureCollection>;
      })
      .then((loaded) => {
        if (cancelled) return;
        setCollection(loaded);
        setStatus(`${formatYear(year)} · 已载入完整 active features`);
      })
      .catch((reason: unknown) => {
        if (!cancelled) {
          setError(`历史切片载入失败：${String(reason)}`);
          setStatus("历史切片不可用");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [manifest, year]);

  const rankedSelection = useMemo(
    () =>
      selectDisplay(
        collection?.features ?? [],
        displayStrategy,
        {
          lon: manifest?.modern_location.lon ?? 116.39723,
          lat: manifest?.modern_location.lat ?? 39.9075,
        },
        manifest?.default_radius_km ?? 75,
      ),
    [
      collection,
      displayStrategy,
      manifest?.default_radius_km,
      manifest?.modern_location.lat,
      manifest?.modern_location.lon,
    ],
  );

  // Keep the last committed collection mounted while the next exact-year query runs.
  // React's stable unit keys can then retain unchanged marker instances.
  const activeCollection = exploreResult?.collection ?? null;
  const activeYear = exploreYear;
  const semanticCenter = useMemo(() => {
    if (viewportBbox) {
      return {
        lon: (viewportBbox[0] + viewportBbox[2]) / 2,
        lat: (viewportBbox[1] + viewportBbox[3]) / 2,
      };
    }
    return {
      lon: manifest?.modern_location.lon ?? 116.39723,
      lat: manifest?.modern_location.lat ?? 39.9075,
    };
  }, [manifest, viewportBbox]);
  const semanticRadiusKm = useMemo(() => {
    if (!viewportBbox) return manifest?.default_radius_km ?? 75;
    const longitudeKm = Math.abs(viewportBbox[2] - viewportBbox[0]) *
      111.32 * Math.cos(semanticCenter.lat * Math.PI / 180);
    const latitudeKm = Math.abs(viewportBbox[3] - viewportBbox[1]) * 110.574;
    return Math.max(1, Math.hypot(longitudeKm, latitudeKm) / 2);
  }, [manifest?.default_radius_km, semanticCenter.lat, viewportBbox]);

  const displaySelection = useMemo(() => {
    const points = rankedSelection.points.filter((feature) =>
      isVisibleForMode(feature, developerMode),
    );
    const labelSelection = selectZoomAwareDisplayLabels(
      points,
      {
        lon: manifest?.modern_location.lon ?? 116.39723,
        lat: manifest?.modern_location.lat ?? 39.9075,
      },
      manifest?.default_radius_km ?? 75,
      mapZoom,
    );
    return {
      ...rankedSelection,
      points,
      labels: labelSelection.labels,
      labelIds: new Set(labelSelection.labels.map((feature) => feature.id)),
      collisionHiddenLabelCount: labelSelection.collisionHiddenLabelCount,
    };
  }, [developerMode, manifest, mapZoom, rankedSelection]);

  const labelPresentation = useMemo(() => {
    if (!manifest || !developerMode) {
      return {
        visibleLabelIds: new Set(displaySelection.labelIds),
        hiddenLabelIds: new Set<string>(),
      };
    }
    return prioritizeHistoricalLabelsAgainstAnchor(
      displaySelection.points,
      displaySelection.labelIds,
      manifest.modern_location,
      manifest.default_radius_km,
      `${manifest.display_name}（现代）`,
    );
  }, [developerMode, displaySelection, manifest]);

  const semanticSelection = useMemo(
    () =>
      selectSemanticZoomUnits(
        activeCollection?.features ?? [],
        semanticCenter,
        semanticRadiusKm,
        mapZoom,
        enabledFamilies,
      ),
    [activeCollection, enabledFamilies, mapZoom, semanticCenter, semanticRadiusKm],
  );

  const renderedUnits = useMemo<DisplayUnit[]>(() => {
    return semanticSelection.units;
  }, [semanticSelection.units]);

  const renderedMemberIds = useMemo(
    () => renderedUnits.flatMap((unit) => unit.members.map((feature) => feature.id)),
    [renderedUnits],
  );
  const renderedLabelIds = useMemo(
    () => historicalDisplayMode === "point_label"
      ? renderedUnits.map((unit) => unit.id)
      : [],
    [historicalDisplayMode, renderedUnits],
  );

  useLayoutEffect(() => {
    const diff = diffDisplayUnits(previousRenderedUnits.current, renderedUnits);
    const currentElements = new Map<string, Element>();
    historyMarkerOverlay.current
      ?.querySelectorAll<HTMLElement>("[data-display-unit-id]")
      .forEach((element) => {
        const id = element.dataset.displayUnitId;
        if (id) currentElements.set(id, element);
      });
    const recreated = diff.retainedIds.filter((id) =>
      previousMarkerElements.current.has(id) &&
      previousMarkerElements.current.get(id) !== currentElements.get(id),
    ).length;
    if (recreated > 0) {
      setRetainedMarkerRecreationCount((count) => count + recreated);
    }
    setMaxVisiblePointCount((count) => Math.max(count, renderedUnits.length));
    setLastDisplayDiff({
      retained: diff.retainedIds.length,
      entering: diff.enteringIds.length,
      leaving: diff.leavingIds.length,
      changedGroups: diff.changedGroupCoordinateKeys.length,
    });
    previousRenderedUnits.current = renderedUnits;
    previousMarkerElements.current = currentElements;
  }, [renderedUnits]);
  const visibleLegendFamilies = useMemo(
    () => DISPLAY_FAMILY_REGISTRY.filter((config) =>
      config.legend && config.userVisible,
    ),
    [],
  );

  const toggleFamily = useCallback((family: DisplayFamily) => {
    setEnabledFamilies((current) => {
      const next = new Set(current);
      if (next.has(family)) next.delete(family);
      else next.add(family);
      return next;
    });
    setDetail(null);
    setSelectedGroup(null);
  }, []);

  const timelineRange = useMemo(() => {
    const [minYear, maxYear] = exploreIndex ? compactIndexYearRange(exploreIndex) : [-763, 1912];
    return { minYear, maxYear };
  }, [exploreIndex]);

  const projectedUnits = useMemo(() => {
    if (!mapReady || !map.current) return [];
    return renderedUnits.map((unit, displayIndex) => {
      const point = map.current!.project(unit.coordinate);
      const placement = stableLabelPlacement(unit.id, mapZoom);
      return { unit, displayIndex, point, placement };
    });
  }, [mapReady, mapRevision, mapZoom, renderedUnits]);

  const openDetail = useCallback(async (feature: HistoricalFeature) => {
    setError(null);
    const fallback = detailFromActiveFeature(
      feature,
      activeYear ?? feature.properties.valid_from,
    );
    if (!feature.properties.detail_path) {
      setDetail(fallback);
      return;
    }
    try {
      const response = await fetch(`/${feature.properties.detail_path}`);
      if (!response.ok) throw new Error(`detail HTTP ${response.status}`);
      setDetail(normalizeDetailPayload(await response.json(), feature, fallback.snapshot_year));
    } catch (reason) {
      console.error("[ChronoChina detail load]", feature.properties.tgaz_id, reason);
      setDetail(fallback);
      setError("该条记录的部分详情暂时无法显示");
    }
  }, [activeYear]);

  useEffect(() => {
    if (!mapReady || !map.current) return;
    anchorMarker.current?.remove();
    anchorMarker.current = null;
    if (!manifest || !developerMode || viewMode !== "focus") return;

    const anchorElement = document.createElement("div");
    anchorElement.className = "anchor-marker";
    anchorElement.setAttribute("aria-label", `${manifest.display_name}（现代）`);
    const anchorPin = document.createElement("span");
    anchorPin.className = "anchor-marker__pin";
    const anchorLabel = document.createElement("span");
    anchorLabel.className = "anchor-marker__label";
    anchorLabel.textContent = `${manifest.display_name}（现代）`;
    anchorElement.append(anchorPin, anchorLabel);
    anchorMarker.current = new maplibregl.Marker({ element: anchorElement, anchor: "left" })
      .setLngLat([manifest.modern_location.lon, manifest.modern_location.lat])
      .addTo(map.current);
  }, [developerMode, manifest, mapReady, viewMode]);

  const activePeriod = manifest?.periods.find((period) => period.year === year);
  const activeTemporalSnapshot = temporalContext?.snapshots.find(
    (snapshot) => snapshot.snapshot_year === year,
  );
  const periodIndex = manifest && year !== null ? manifest.available_periods.indexOf(year) : -1;
  const activeReferenceMode = referenceMode(referenceModeId);
  const sliceStatus =
    collection && manifest && year !== null
      ? `${formatYear(year)} · ${manifest.default_radius_km} km 内底层 ` +
        `${collection.features.length} 条有效记录 · 展示 ` +
        `${renderedUnits.length} 个可交互位置 · 当前标注 ` +
        `${renderedLabelIds.length} 个`
      : status;

  async function selectModernPlace(anchorId: string) {
    setSearchAnchorId(anchorId);
    setError(null);
    try {
      const response = await fetch(`/anchors/${anchorId}/manifest.json`);
      if (!response.ok) throw new Error(`anchor HTTP ${response.status}`);
      const locator = (await response.json()) as AnchorManifest;
      map.current?.easeTo({
        center: [locator.modern_location.lon, locator.modern_location.lat],
        zoom: 7.4,
        duration: 450,
      });
    } catch (reason) {
      setError(`现代地点定位失败：${String(reason)}`);
    }
  }

  function applyExploreYear() {
    const nextYear = Number(exploreYearDraft);
    if (!Number.isInteger(nextYear) || nextYear === 0) {
      setError("精确年份必须是非零整数；公元纪年不存在 0 年。");
      return;
    }
    setError(null);
    setExploreYear(nextYear);
  }

  function selectSupportedYear(selectedYear: number) {
    if (!temporalContext?.snapshots.some((snapshot) => snapshot.snapshot_year === selectedYear)) {
      setError(`不支持的历史年份：${selectedYear}；地图未创建中间状态`);
      return;
    }
    setYear(selectedYear);
  }

  function setMode(nextDeveloperMode: boolean) {
    setDeveloperMode(nextDeveloperMode);
    if (!nextDeveloperMode) {
      setDisplayStrategy("type_diverse_spatial");
      if (referenceModeId !== "r2_minimal_modern" && referenceModeId !== "r4_color_geography") {
        setReferenceModeId("r2_minimal_modern");
      }
    }
  }

  const detailSourceNote = sourceNotePresentation(detail?.source?.source_note ?? null);

  return (
    <main className="app-shell">
      <header className="masthead">
        <div>
          <p className="eyebrow">CHRONOCHINA · VIEWPORT + FIVE-ANCHOR MVP</p>
          <h1>中国历史地理时间地图</h1>
          <p className="subtitle">
            移动地图，以精确年份查看当前视口内的历史地名。
          </p>
        </div>
        <div className="masthead__actions">
          {developerMode && (
            <div className="anchor-select">
              <label htmlFor="anchor-select">现代地点</label>
              <select
                id="anchor-select"
                value={searchAnchorId}
                onChange={(event) => void selectModernPlace(event.target.value)}
              >
                {ANCHORS.map((anchor) => (
                  <option key={anchor.id} value={anchor.id}>{anchor.name}</option>
                ))}
              </select>
              <span>Developer QA fly-to</span>
            </div>
          )}
          <button
            className="mode-toggle"
            type="button"
            aria-pressed={developerMode}
            onClick={() => setMode(!developerMode)}
          >
            {developerMode ? "返回用户模式" : "开发者模式"}
          </button>
        </div>
      </header>

      <section className={`map-stage map-stage--${developerMode ? "developer" : "user"}`} aria-label="历史地图">
        <div
          ref={mapContainer}
          className="map"
          data-testid="map"
          data-reference-mode={referenceModeId}
          data-reference-effective-mode={effectiveReferenceModeId}
          data-reference-source-status={referenceSourceStatus}
          data-reference-fallback-active={referenceReadiness?.fallbackActive ?? false}
          data-reference-timeout-reached={referenceReadiness?.timeoutReached ?? false}
          data-reference-loaded-critical-layers={
            referenceReadiness?.loadedCriticalLayerIds.join(",") ?? ""
          }
          data-reference-failed-critical-layers={
            referenceReadiness?.failedCriticalLayerIds.join(",") ?? ""
          }
          data-reference-last-error={referenceReadiness?.lastError ?? ""}
          data-reference-geometry-layer-count={referenceLayerCounts.geometry}
          data-reference-label-layer-count={referenceLayerCounts.labels}
          data-display-strategy={displayStrategy}
          data-historical-display-mode={historicalDisplayMode}
          data-query-pending={activeCollection?.metadata.year !== exploreYear}
          data-app-mode={developerMode ? "developer" : "user"}
          data-view-mode="unified_viewport"
          data-snapshot-id={viewMode === "focus" ? activeTemporalSnapshot?.snapshot_id ?? "" : `viewport:${exploreYear}`}
          data-snapshot-year={activeYear ?? ""}
          data-query-result-year={activeCollection?.metadata.year ?? ""}
          data-explore-index-status={exploreIndexStatus}
          data-explore-index-record-count={exploreIndex?.source.record_count ?? 0}
          data-explore-index-load-ms={exploreIndexLoadMs?.toFixed(3) ?? ""}
          data-explore-query-sequence={exploreCommittedSequence}
          data-explore-cancelled-query-count={exploreCancelledCount}
          data-stale-commit-count={exploreStaleCommitCount}
          data-explore-query-latency-ms={exploreResult?.queryLatencyMs.toFixed(3) ?? ""}
          data-timeline-input-to-map-latency-ms={exploreInputToMapLatencyMs?.toFixed(3) ?? ""}
          data-explore-coverage-status={exploreCoverageStatus}
          data-explore-active-record-count={exploreResult?.activeRecordCount ?? 0}
          data-explore-spatial-record-count={exploreResult?.spatialRecordCount ?? 0}
          data-viewport-bbox={viewportBbox?.map((value) => value.toFixed(6)).join(",") ?? ""}
          data-timeline-linear-position={
            activeTemporalSnapshot?.timeline.linear_normalized_position ?? ""
          }
          data-timeline-display-position={
            activeTemporalSnapshot?.timeline.display_normalized_position ?? ""
          }
          data-active-feature-count={activeCollection?.features.length ?? 0}
          data-eligible-record-count={semanticSelection.eligibleFeatureCount}
          data-enabled-display-families={[...enabledFamilies].sort().join(",")}
          data-strategy-ranked-point-count={rankedSelection.points.length}
          data-strategy-ranked-point-ids={rankedSelection.points.map((feature) => feature.id).join(",")}
          data-historical-point-count={renderedUnits.length}
          data-historical-point-ids={renderedMemberIds.join(",")}
          data-historical-label-count={renderedLabelIds.length}
          data-historical-label-ids={renderedLabelIds.join(",")}
          data-display-unit-ids={renderedUnits.map((unit) => unit.id).join(",")}
          data-active-display-families={semanticSelection.activeFamilies.join(",")}
          data-eligible-display-families={semanticSelection.eligibleFamilies.join(",")}
          data-visible-display-families={visibleLegendFamilies.map((config) => config.id).join(",")}
          data-semantic-hidden-feature-count={semanticSelection.semanticHiddenFeatureCount}
          data-co-located-group-count={renderedUnits.filter((unit) => unit.kind === "colocated_group").length}
          data-anchor-hidden-label-count={labelPresentation.hiddenLabelIds.size}
          data-historical-label-collision-count={
            semanticSelection.collisionHiddenUnitCount
          }
          data-historical-label-collision-metric="deterministic-placement"
          data-retained-marker-recreation-count={retainedMarkerRecreationCount}
          data-full-historical-layer-clear-count={fullLayerClearCount}
          data-max-visible-point-count={maxVisiblePointCount}
          data-last-diff-retained={lastDisplayDiff.retained}
          data-last-diff-entering={lastDisplayDiff.entering}
          data-last-diff-leaving={lastDisplayDiff.leaving}
          data-last-diff-changed-groups={lastDisplayDiff.changedGroups}
        />

        <div ref={historyMarkerOverlay} className="history-marker-overlay" aria-label="历史地点图层">
          {projectedUnits.map(({ unit, displayIndex, point, placement }) => {
            const feature = unit.representative;
            const style = {
              left: `${point.x}px`,
              top: `${point.y}px`,
              "--history-marker-stack-order": String(renderedUnits.length - displayIndex),
              "--history-label-offset-x": `${placement.offsetX}px`,
              "--history-label-offset-y": `${placement.offsetY}px`,
              ...markerVariables(unit.family, mapZoom),
            } as CSSProperties;
            return (
              <button
                key={unit.id}
                type="button"
                className={
                  `history-marker history-marker--${feature.properties.location_confidence} ` +
                  `history-marker--family-${unit.family} ` +
                  `history-marker--shape-${familyConfig(unit.family).shape} ` +
                  `${unit.kind === "colocated_group" ? "history-marker--colocated " : ""}` +
                  `history-marker--placement-${placement.placement}`
                }
                style={style}
                data-tgaz-id={feature.properties.tgaz_id}
                data-display-unit-id={unit.id}
                data-display-unit-kind={unit.kind}
                data-member-ids={unit.members.map((member) => member.id).join(",")}
                data-colocated-count={unit.members.length}
                data-snapshot-year={activeCollection?.metadata.year}
                data-has-persistent-label={historicalDisplayMode === "point_label"}
                data-longitude={unit.coordinate[0]}
                data-latitude={unit.coordinate[1]}
                data-marker-anchor="center"
                data-maplibre-anchor="center"
                data-display-family={unit.family}
                data-label-placement={placement.placement}
                data-label-offset={`${placement.offsetX},${placement.offsetY}`}
                title={unit.label}
                aria-label={
                  unit.kind === "colocated_group"
                    ? `${unit.label}，点击查看 ${unit.members.length} 条独立记录`
                    : `${feature.properties.name}，历史点`
                }
                onClick={() => {
                  if (unit.kind === "colocated_group") {
                    setDetail(null);
                    setSelectedGroup(unit);
                  } else {
                    setSelectedGroup(null);
                    void openDetail(feature);
                  }
                }}
              >
                <span className="history-marker__dot">
                  {unit.kind === "colocated_group" && (
                    <span className="history-marker__count">{unit.members.length}</span>
                  )}
                </span>
                <span className={
                  historicalDisplayMode === "point_label"
                    ? "history-marker__label history-marker__label--persistent"
                    : "history-marker__label history-marker__label--hover"
                }>
                  {unit.label}
                </span>
              </button>
            );
          })}
        </div>

        <div className="map-display-controls" data-testid="map-display-controls">
          <fieldset aria-label="历史点显示模式">
            <legend>历史点</legend>
            <button
              type="button"
              aria-pressed={historicalDisplayMode === "point_label"}
              onClick={() => setHistoricalDisplayMode("point_label")}
            >点 + 标签</button>
            <button
              type="button"
              aria-pressed={historicalDisplayMode === "point_only"}
              onClick={() => setHistoricalDisplayMode("point_only")}
            >仅点</button>
          </fieldset>
          <fieldset aria-label="背景地图模式">
            <legend>底图</legend>
            <button
              type="button"
              aria-pressed={referenceModeId === "r2_minimal_modern"}
              onClick={() => setReferenceModeId("r2_minimal_modern")}
            >简洁</button>
            <button
              type="button"
              aria-pressed={referenceModeId === "r4_color_geography"}
              onClick={() => setReferenceModeId("r4_color_geography")}
            >彩色地理</button>
          </fieldset>
        </div>

        {viewMode === "focus" && (
        <section className="period-control" aria-label="代表时期">
          <div className="period-control__heading">
            <div>
              <p className="panel-kicker">时间与历史语境</p>
              <h2>{activeTemporalSnapshot?.display_year ?? "载入中"}</h2>
            </div>
            {developerMode && (
              <span data-testid="snapshot-sequence">
                {activeTemporalSnapshot
                  ? `第 ${activeTemporalSnapshot.sequence_index + 1} / ${activeTemporalSnapshot.sequence_count} 个代表状态`
                  : "—"}
              </span>
            )}
          </div>
          {activeTemporalSnapshot && (
            <div className="temporal-context" data-testid="temporal-context">
              <p className="temporal-context__era">{activeTemporalSnapshot.broad_era_label}</p>
              {activeTemporalSnapshot.regional_context_label && (
                <p className="temporal-context__regional">
                  {manifest?.display_name}区域：{activeTemporalSnapshot.regional_context_label}
                </p>
              )}
            </div>
          )}
          {temporalContext && year !== null && (
            <TemporalRail
              snapshots={temporalContext.snapshots}
              currentYear={year}
              developerMode={developerMode}
              onSelectYear={selectSupportedYear}
            />
          )}
          <div className="period-stepper">
            <button
              type="button"
              disabled={periodIndex <= 0}
              onClick={() =>
                manifest && selectSupportedYear(manifest.available_periods[periodIndex - 1])
              }
            >
              ← 上一时期
            </button>
            <button
              type="button"
              disabled={!manifest || periodIndex < 0 || periodIndex >= manifest.available_periods.length - 1}
              onClick={() =>
                manifest && selectSupportedYear(manifest.available_periods[periodIndex + 1])
              }
            >
              下一时期 →
            </button>
          </div>
          {activeTemporalSnapshot && (
            <p className="period-reason" data-testid="snapshot-change-summary">
              {activeTemporalSnapshot.previous_snapshot_year === null
                ? "这是当前地点最早的已收录代表时期。"
                : `与上一时期相比：新增 ${activeTemporalSnapshot.changes_from_previous.added_records} 条记录，移除 ${activeTemporalSnapshot.changes_from_previous.removed_records} 条记录。`}
            </p>
          )}
          {developerMode && (
            <div className="developer-controls" data-testid="developer-controls">
              <div className="period-buttons" role="group" aria-label="历史年份 QA baseline">
                {(manifest?.available_periods ?? []).map((availableYear) => (
                  <button
                    key={availableYear}
                    type="button"
                    aria-pressed={availableYear === year}
                    onClick={() => selectSupportedYear(availableYear)}
                  >
                    {formatYear(availableYear)}
                  </button>
                ))}
              </div>
              <fieldset className="reference-switcher" aria-label="现代参考层">
                <legend>现代参考层 · Phase 1.2</legend>
                <div>
                  {REFERENCE_MODES.map((mode) => (
                    <label key={mode.id}>
                      <input
                        type="radio"
                        name="reference-mode"
                        value={mode.id}
                        checked={referenceModeId === mode.id}
                        onChange={() => setReferenceModeId(mode.id)}
                      />
                      <span><b>{mode.code}</b>{mode.label}</span>
                    </label>
                  ))}
                </div>
                <p>{activeReferenceMode.description}</p>
                {referenceSourceStatus === "loading" && (
                  <p className="reference-status">现代参考正在载入；历史层可继续使用。</p>
                )}
                {referenceSourceStatus === "unavailable" && (
                  <p className="reference-status reference-status--unavailable" role="status">
                    现代参考暂不可用；历史层仍可使用。
                  </p>
                )}
              </fieldset>
              <fieldset className="strategy-switcher" aria-label="Display Strategy">
                <legend>Display Strategy · QA</legend>
                <div>
                  {DISPLAY_STRATEGIES.map((strategy) => (
                    <label key={strategy.id}>
                      <input
                        type="radio"
                        name="display-strategy"
                        value={strategy.id}
                        checked={displayStrategy === strategy.id}
                        onChange={() => setDisplayStrategy(strategy.id)}
                      />
                      {strategy.label}
                      {strategy.id === "type_diverse_spatial" && (
                        <span className="default-strategy" aria-hidden="true">默认</span>
                      )}
                    </label>
                  ))}
                </div>
              </fieldset>
              {activeTemporalSnapshot && (
                <dl className="temporal-debug" aria-label="Temporal QA">
                  <div><dt>snapshot ID</dt><dd>{activeTemporalSnapshot.snapshot_id}</dd></div>
                  <div><dt>exact year</dt><dd>{activeTemporalSnapshot.snapshot_year}</dd></div>
                  <div><dt>context sources</dt><dd>{activeTemporalSnapshot.source_ids.join(", ")}</dd></div>
                  <div>
                    <dt>normalized position</dt>
                    <dd>{activeTemporalSnapshot.timeline.linear_normalized_position.toFixed(6)}</dd>
                  </div>
                  <div>
                    <dt>display position</dt>
                    <dd>{activeTemporalSnapshot.timeline.display_normalized_position.toFixed(6)}</dd>
                  </div>
                  <div>
                    <dt>minimum spacing</dt>
                    <dd>{activeTemporalSnapshot.timeline.position_adjusted ? "applied" : "not needed"}</dd>
                  </div>
                </dl>
              )}
            </div>
          )}
          <p className="slice-status" data-testid="slice-status">
            {developerMode
              ? sliceStatus
              : collection
                ? `当前地图显示 ${renderedUnits.length} 个可交互历史位置`
                : status}
          </p>
          <p
            className="density-notice"
            data-qa-density-semantics="source density != historical density"
          >
            不同时期资料完整度不同，地图数量不代表当时聚落总量。
          </p>
          {developerMode && activePeriod && (
            <p className="period-reason">
              由附近历史地点集合变化自动选出；较上一代表时期新增 {activePeriod.added_since_previous}、
              移除 {activePeriod.removed_since_previous} 条记录。
            </p>
          )}
        </section>
        )}

        {developerMode && viewMode === "explore" && (
          <section className="period-control explore-control" aria-label="自由探索时间与范围">
            <p className="panel-kicker">自由探索 · 精确年份</p>
            <h2>{formatYear(exploreYear)}</h2>
            <div className="explore-year-control">
              <label htmlFor="explore-year">年份（负数表示公元前）</label>
              <div>
                <input
                  id="explore-year"
                  type="number"
                  step="1"
                  value={exploreYearDraft}
                  onChange={(event) => setExploreYearDraft(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") applyExploreYear();
                  }}
                />
                <button type="button" onClick={applyExploreYear}>应用年份</button>
              </div>
            </div>
            <p className={`coverage-status coverage-status--${exploreCoverageStatus}`} data-testid="explore-coverage-status">
              {coverageStatusLabel(exploreCoverageStatus)}
            </p>
            <p className="coverage-reason">{exploreCoverageReason}</p>
            <dl className="explore-query-stats">
              <div><dt>索引匹配记录</dt><dd>{exploreResult?.activeRecordCount ?? 0}</dd></div>
              <div><dt>可交互历史位置</dt><dd>{renderedUnits.length}</dd></div>
              <div><dt>查询耗时</dt><dd>{exploreResult ? `${exploreResult.queryLatencyMs.toFixed(1)} ms` : "—"}</dd></div>
            </dl>
            <p className="density-notice" data-qa-density-semantics="source density != historical density">
              移动或缩放地图会重新查询。空结果不自动解释为历史上没有地点。
            </p>
            {developerMode && (
              <p className="period-reason">
                compact index {exploreIndexStatus} · {exploreIndex?.source.record_count ?? 0} records ·
                request {exploreCommittedSequence} · cancelled {exploreCancelledCount}
              </p>
            )}
          </section>
        )}

        {referenceModeId !== "r0_grid" && (
          <div className="reference-badge" data-testid="reference-badge">
            {referenceModeId === "r2_minimal_modern" && referenceSourceStatus === "failed"
              ? "现代地图参考未加载"
              : referenceModeId === "r4_color_geography"
              ? "彩色地理参考 · 非卫星影像"
              : referenceModeId === "r3_modern_admin"
              ? "现代行政参考 · 非历史边界"
              : developerMode
                ? `${activeReferenceMode.code} · 现代地理参考`
                : "现代地理参考"}
          </div>
        )}

        {!developerMode && referenceModeId !== "r0_grid" &&
          referenceSourceStatus !== "ready" && (
          <div
            className={`reference-message reference-message--${referenceSourceStatus}`}
            data-testid="reference-status-message"
            role="status"
          >
            {referenceSourceStatus === "loading"
              ? "正在加载现代地图参考…"
              : referenceSourceStatus === "degraded"
                ? "部分现代地图参考暂未加载。"
                : "现代地图参考加载失败，历史地点仍可正常浏览。"}
          </div>
        )}

        <aside className="legend" aria-label="地图图例" data-testid="layer-switcher">
          {visibleLegendFamilies.map((config) => (
            <button
              key={config.id}
              type="button"
              data-legend-family={config.id}
              aria-pressed={enabledFamilies.has(config.id)}
              aria-label={`${config.labelZh}：${enabledFamilies.has(config.id) ? "已显示" : "已隐藏"}`}
              onClick={() => toggleFamily(config.id)}
            >
              <i
                className={`legend__dot history-marker--shape-${config.shape}`}
                style={markerVariables(config.id, mapZoom) as CSSProperties}
              />
              <span>{config.labelZh}</span>
            </button>
          ))}
          <small className="legend__counts" data-testid="layer-counts">
            源 {activeCollection?.features.length ?? 0} · 已启用 {semanticSelection.eligibleFeatureCount} · 位置 {renderedUnits.length}
          </small>
        </aside>

        <ContinuousTimeline
          minYear={timelineRange.minYear}
          maxYear={timelineRange.maxYear}
          year={exploreYear}
          onChange={(nextYear) => {
            exploreInputAt.current = performance.now();
            setExploreYear(nextYear);
            setExploreYearDraft(String(nextYear));
            setDetail(null);
            setSelectedGroup(null);
            setError(null);
          }}
        />

        {error && <div className="error-banner" role="alert">{error}</div>}

        {selectedGroup && (
          <article className="colocated-card" aria-label="同址历史记录">
            <button
              className="detail-card__close"
              type="button"
              onClick={() => setSelectedGroup(null)}
              aria-label="关闭同址记录"
            >×</button>
            <p className="detail-card__kicker">同一来源坐标 · {selectedGroup.members.length} 条独立记录</p>
            <h2>请选择一条历史记录</h2>
            <p className="colocated-card__notice">这里只组合显示，不合并 ID、名称或历史实体。</p>
            <ul>
              {selectedGroup.members.map((feature) => (
                <li key={feature.id}>
                  <button
                    type="button"
                    data-colocated-member-id={feature.id}
                    onClick={() => {
                      setSelectedGroup(null);
                      void openDetail(feature);
                    }}
                  >
                    <strong>{feature.properties.name}</strong>
                    <span>
                      {feature.properties.feature_type} · {formatDetailYear(feature.properties.valid_from)}—
                      {formatDetailYear(feature.properties.valid_to)}
                    </span>
                    <small>{feature.properties.tgaz_id}</small>
                  </button>
                </li>
              ))}
            </ul>
          </article>
        )}

        {detail && (
          <DetailErrorBoundary
            key={detail.source_record_id || detail.name}
            onClose={() => setDetail(null)}
          >
          <article className="detail-card" aria-label="历史地点详情">
            <button
              className="detail-card__close"
              type="button"
              onClick={() => setDetail(null)}
              aria-label="关闭详情"
            >×</button>
            <p className="detail-card__kicker">
              {viewMode === "explore" ? "当前视口内的历史地点" : "现代地点附近的历史地点"} · {detail.feature_type}
            </p>
            <h2>{detail.name}</h2>
            {detail.name_pinyin && <p className="pinyin">{detail.name_pinyin}</p>}
            <dl>
              <div><dt>当前快照</dt><dd>{formatDetailYear(detail.snapshot_year)}</dd></div>
              <div><dt>有效时期</dt><dd>{formatDetailYear(detail.valid_from)} — {formatDetailYear(detail.valid_to)}</dd></div>
              <div><dt>上级</dt><dd>{knownValue(detail.parent_name)}</dd></div>
              <div>
                <dt>{viewMode === "explore" ? "距视口中心" : "距现代锚点"}</dt>
                <dd>{formatDetailDistance(detail.distance_to_anchor_km)}</dd>
              </div>
              <div><dt>位置可信度</dt><dd>{confidenceLabel(detail.location_confidence)}</dd></div>
              <div><dt>TGAZ ID</dt><dd>{detail.source_record_id}</dd></div>
              <div>
                <dt>来源 / 许可</dt>
                <dd>
                  {detail.source?.data_source || detail.source?.system || "来源信息暂不可用"} · {detail.license ?? "许可未逐条重新获取"}
                </dd>
              </div>
            </dl>
            {detailSourceNote.text ? (
              <section className="source-note" aria-label="完整来源说明">
                <h3>来源说明（完整）</h3>
                <p data-testid="source-note-full">{detailSourceNote.text}</p>
                {detailSourceNote.rawDiffers && (
                  <details>
                    <summary>查看未经改写的源文本</summary>
                    <pre data-testid="source-note-raw">{detailSourceNote.raw}</pre>
                  </details>
                )}
              </section>
            ) : (
              <p className="source-note source-note--empty">源记录未提供来源说明。</p>
            )}
            <a href={detail.canonical_uri} target="_blank" rel="noreferrer">
              查看 TGAZ canonical record
            </a>
            <p className="semantic-notice">
              {viewMode === "explore"
                ? "这里仅表示记录位于当前视口；地图不建立地点之间的同一实体、前身、后继或改名关系。"
                : "这些地点只是位于现代地点附近；地图不表示它们是现代城市的前身或旧称。"}
            </p>
          </article>
          </DetailErrorBoundary>
        )}
      </section>

      <footer className="provenance-bar">
        <span>
          {developerMode
            ? `Developer fly-to：${ANCHORS.find((anchor) => anchor.id === searchAnchorId)?.name ?? "北京"}`
            : "浏览范围：当前地图视口"}
        </span>
        <span>
          {viewMode === "explore"
            ? "历史点仅表示当前视口成员，不建立同一实体、前身、后继或改名关系"
            : developerMode
            ? "历史点：TGAZ / CHGIS snapshot · 未缓存记录不臆测逐条许可"
            : "历史地点来自可追溯的历史地理数据；详情保留来源信息"}
        </span>
        {referenceModeId !== "r0_grid" && (
          <span className="reference-attribution">
            现代参考：<a href="https://openfreemap.org/" target="_blank" rel="noreferrer">OpenFreeMap</a>
            {" · "}<a href="https://openmaptiles.org/" target="_blank" rel="noreferrer">© OpenMapTiles</a>
            {" · "}<a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">© OpenStreetMap contributors</a>
          </span>
        )}
        <span>
          {developerMode
            ? "仅展示 Spatial Neighborhood，不生成 Historical Lineage"
            : "历史数据范围由当前视口、年份与用户开启的层级共同决定"}
        </span>
        <span className="coverage-gap">1912–1949：未公开接入；未沿用 1911 数据</span>
      </footer>
    </main>
  );
}
