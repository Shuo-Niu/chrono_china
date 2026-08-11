import type { LayerSpecification, Map as MapLibreMap } from "maplibre-gl";


export type ReferenceModeId =
  | "r0_grid"
  | "r1_physical"
  | "r2_minimal_modern"
  | "r3_modern_admin"
  | "r4_color_geography";

export type ReferenceSourceStatus =
  | "off"
  | "loading"
  | "ready"
  | "degraded"
  | "failed"
  | "unavailable";

export interface ReferenceMode {
  id: ReferenceModeId;
  code: "R0" | "R1" | "R2" | "R3" | "R4";
  label: string;
  description: string;
  geometryLayerIds: string[];
  labelLayerIds: string[];
}

export interface ReferenceApplyResult {
  status: Exclude<ReferenceSourceStatus, "ready">;
  geometryLayerCount: number;
  labelLayerCount: number;
  error?: string;
}

export const MODERN_REFERENCE_SOURCE_ID = "chronochina-modern-reference";
export const MODERN_REFERENCE_SOURCE_URL = "https://tiles.openfreemap.org/planet";
export const MODERN_REFERENCE_GLYPHS_URL =
  "https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf";
const MODERN_REFERENCE_HOSTNAME = new URL(MODERN_REFERENCE_SOURCE_URL).hostname;

const WATER_LAYER_ID = "reference-water";
const WATERWAY_LAYER_ID = "reference-major-waterway";
const SETTLEMENT_LABEL_LAYER_ID = "reference-settlement-label";
const MAJOR_ROAD_LAYER_ID = "reference-major-road";
const ADMIN_BOUNDARY_LAYER_ID = "reference-modern-admin-boundary";
const ADMIN_LABEL_LAYER_ID = "reference-modern-admin-label";
const COLOR_LANDCOVER_LAYER_ID = "reference-color-landcover";
const COLOR_LANDUSE_LAYER_ID = "reference-color-landuse";
const COLOR_PARK_LAYER_ID = "reference-color-park";
const COLOR_WATER_LAYER_ID = "reference-color-water";
const COLOR_WATERWAY_LAYER_ID = "reference-color-waterway";
const COLOR_BUILDING_LAYER_ID = "reference-color-building";
const COLOR_PEAK_LAYER_ID = "reference-color-peak";
const COLOR_PEAK_LABEL_LAYER_ID = "reference-color-peak-label";

export const MODERN_REFERENCE_LAYER_IDS = [
  WATER_LAYER_ID,
  WATERWAY_LAYER_ID,
  SETTLEMENT_LABEL_LAYER_ID,
  MAJOR_ROAD_LAYER_ID,
  ADMIN_BOUNDARY_LAYER_ID,
  ADMIN_LABEL_LAYER_ID,
  COLOR_LANDCOVER_LAYER_ID,
  COLOR_LANDUSE_LAYER_ID,
  COLOR_PARK_LAYER_ID,
  COLOR_WATER_LAYER_ID,
  COLOR_WATERWAY_LAYER_ID,
  COLOR_BUILDING_LAYER_ID,
  COLOR_PEAK_LAYER_ID,
  COLOR_PEAK_LABEL_LAYER_ID,
] as const;

export const REFERENCE_MODES: ReferenceMode[] = [
  {
    id: "r0_grid",
    code: "R0",
    label: "抽象网格",
    description: "不加载现代地理参考，保留 Phase 1.1 基线。",
    geometryLayerIds: [],
    labelLayerIds: [],
  },
  {
    id: "r1_physical",
    code: "R1",
    label: "自然地理",
    description: "仅加入现代海岸/水体与主要河流。",
    geometryLayerIds: [WATER_LAYER_ID, WATERWAY_LAYER_ID],
    labelLayerIds: [],
  },
  {
    id: "r2_minimal_modern",
    code: "R2",
    label: "最小现代参考",
    description: "R1 + 稀疏主要城市地名 + 极淡主要交通骨架；不含道路名称或密集街道。",
    geometryLayerIds: [WATER_LAYER_ID, WATERWAY_LAYER_ID, MAJOR_ROAD_LAYER_ID],
    labelLayerIds: [SETTLEMENT_LABEL_LAYER_ID],
  },
  {
    id: "r3_modern_admin",
    code: "R3",
    label: "现代行政参考",
    description: "R1 + 现代行政线与稀疏地名；不是历史边界。",
    geometryLayerIds: [WATER_LAYER_ID, WATERWAY_LAYER_ID, ADMIN_BOUNDARY_LAYER_ID],
    labelLayerIds: [ADMIN_LABEL_LAYER_ID],
  },
  {
    id: "r4_color_geography",
    code: "R4",
    label: "彩色地理参考",
    description: "彩色水体、植被、土地利用、建筑与山峰参考；不是卫星影像，也不是历史边界。",
    geometryLayerIds: [
      COLOR_LANDCOVER_LAYER_ID,
      COLOR_LANDUSE_LAYER_ID,
      COLOR_PARK_LAYER_ID,
      COLOR_WATER_LAYER_ID,
      COLOR_WATERWAY_LAYER_ID,
      COLOR_BUILDING_LAYER_ID,
      MAJOR_ROAD_LAYER_ID,
      COLOR_PEAK_LAYER_ID,
    ],
    labelLayerIds: [SETTLEMENT_LABEL_LAYER_ID, COLOR_PEAK_LABEL_LAYER_ID],
  },
];

const MODERN_REFERENCE_LAYERS: LayerSpecification[] = [
  {
    id: WATER_LAYER_ID,
    type: "fill",
    source: MODERN_REFERENCE_SOURCE_ID,
    "source-layer": "water",
    layout: { visibility: "none" },
    paint: {
      "fill-color": "#90b7c1",
      "fill-opacity": 0.26,
    },
  },
  {
    id: WATERWAY_LAYER_ID,
    type: "line",
    source: MODERN_REFERENCE_SOURCE_ID,
    "source-layer": "waterway",
    minzoom: 4,
    filter: ["match", ["get", "class"], ["river", "canal"], true, false],
    layout: {
      visibility: "none",
      "line-cap": "round",
      "line-join": "round",
    },
    paint: {
      "line-color": "#638f9d",
      "line-opacity": 0.38,
      "line-width": [
        "interpolate",
        ["linear"],
        ["zoom"],
        4,
        0.35,
        9,
        1.15,
        12,
        1.8,
      ],
    },
  },
  {
    id: SETTLEMENT_LABEL_LAYER_ID,
    type: "symbol",
    source: MODERN_REFERENCE_SOURCE_ID,
    "source-layer": "place",
    minzoom: 6,
    filter: [
      "all",
      ["==", ["get", "class"], "city"],
      ["<=", ["coalesce", ["get", "rank"], 99], 10],
    ],
    layout: {
      visibility: "none",
      "symbol-sort-key": ["coalesce", ["get", "rank"], 99],
      "text-field": ["coalesce", ["get", "name:zh"], ["get", "name"]],
      "text-font": ["Noto Sans Regular"],
      "text-size": 10.5,
      "text-max-width": 8,
      "text-padding": 18,
      "text-allow-overlap": false,
    },
    paint: {
      "text-color": "#536a70",
      "text-opacity": 0.54,
      "text-halo-color": "rgba(245, 241, 232, 0.92)",
      "text-halo-width": 1.2,
    },
  },
  {
    id: MAJOR_ROAD_LAYER_ID,
    type: "line",
    source: MODERN_REFERENCE_SOURCE_ID,
    "source-layer": "transportation",
    minzoom: 5,
    filter: [
      "match",
      ["get", "class"],
      ["motorway", "trunk", "primary"],
      true,
      false,
    ],
    layout: {
      visibility: "none",
      "line-cap": "round",
      "line-join": "round",
    },
    paint: {
      "line-color": "#75868a",
      "line-opacity": 0.16,
      "line-width": [
        "interpolate",
        ["linear"],
        ["zoom"],
        5,
        0.28,
        9,
        0.7,
        12,
        1.05,
      ],
    },
  },
  {
    id: ADMIN_BOUNDARY_LAYER_ID,
    type: "line",
    source: MODERN_REFERENCE_SOURCE_ID,
    "source-layer": "boundary",
    minzoom: 4,
    filter: [
      "match",
      ["get", "admin_level"],
      [4, 5, 6],
      true,
      false,
    ],
    layout: { visibility: "none" },
    paint: {
      "line-color": "#65747a",
      "line-opacity": 0.31,
      "line-width": ["interpolate", ["linear"], ["zoom"], 4, 0.55, 10, 1.2],
      "line-dasharray": [2, 3],
    },
  },
  {
    id: ADMIN_LABEL_LAYER_ID,
    type: "symbol",
    source: MODERN_REFERENCE_SOURCE_ID,
    "source-layer": "place",
    minzoom: 5,
    filter: [
      "all",
      [
        "match",
        ["get", "class"],
        ["state", "province", "city"],
        true,
        false,
      ],
      ["<=", ["coalesce", ["get", "rank"], 99], 12],
    ],
    layout: {
      visibility: "none",
      "symbol-sort-key": ["coalesce", ["get", "rank"], 99],
      "text-field": ["coalesce", ["get", "name:zh"], ["get", "name"]],
      "text-font": ["Noto Sans Regular"],
      "text-size": 10.5,
      "text-max-width": 8,
      "text-padding": 20,
      "text-allow-overlap": false,
    },
    paint: {
      "text-color": "#59696f",
      "text-opacity": 0.5,
      "text-halo-color": "rgba(245, 241, 232, 0.94)",
      "text-halo-width": 1.2,
    },
  },
  {
    id: COLOR_LANDCOVER_LAYER_ID,
    type: "fill",
    source: MODERN_REFERENCE_SOURCE_ID,
    "source-layer": "landcover",
    layout: { visibility: "none" },
    paint: {
      "fill-color": [
        "match",
        ["get", "class"],
        "wood", "#a8c99f",
        "grass", "#c7d8a2",
        "wetland", "#b5d1bd",
        "rock", "#c8c1b4",
        "sand", "#ead9ab",
        "#d9d3c5",
      ],
      "fill-opacity": 0.5,
    },
  },
  {
    id: COLOR_LANDUSE_LAYER_ID,
    type: "fill",
    source: MODERN_REFERENCE_SOURCE_ID,
    "source-layer": "landuse",
    layout: { visibility: "none" },
    paint: {
      "fill-color": [
        "match",
        ["get", "class"],
        ["residential", "commercial", "industrial", "retail"], "#d8cec0",
        ["agriculture", "farmland"], "#ddd7a6",
        ["park", "grass", "cemetery"], "#b9d6a6",
        "#d9d2c6",
      ],
      "fill-opacity": 0.48,
    },
  },
  {
    id: COLOR_PARK_LAYER_ID,
    type: "fill",
    source: MODERN_REFERENCE_SOURCE_ID,
    "source-layer": "park",
    layout: { visibility: "none" },
    paint: { "fill-color": "#a8d09a", "fill-opacity": 0.55 },
  },
  {
    id: COLOR_WATER_LAYER_ID,
    type: "fill",
    source: MODERN_REFERENCE_SOURCE_ID,
    "source-layer": "water",
    layout: { visibility: "none" },
    paint: { "fill-color": "#85b9d5", "fill-opacity": 0.72 },
  },
  {
    id: COLOR_WATERWAY_LAYER_ID,
    type: "line",
    source: MODERN_REFERENCE_SOURCE_ID,
    "source-layer": "waterway",
    minzoom: 4,
    layout: { visibility: "none", "line-cap": "round" },
    paint: { "line-color": "#659fbe", "line-opacity": 0.78, "line-width": 1.1 },
  },
  {
    id: COLOR_BUILDING_LAYER_ID,
    type: "fill",
    source: MODERN_REFERENCE_SOURCE_ID,
    "source-layer": "building",
    minzoom: 11,
    layout: { visibility: "none" },
    paint: { "fill-color": "#b7a899", "fill-opacity": 0.58 },
  },
  {
    id: COLOR_PEAK_LAYER_ID,
    type: "circle",
    source: MODERN_REFERENCE_SOURCE_ID,
    "source-layer": "mountain_peak",
    minzoom: 7,
    layout: { visibility: "none" },
    paint: {
      "circle-radius": 2.5,
      "circle-color": "#786f66",
      "circle-stroke-color": "#f7f1e6",
      "circle-stroke-width": 1,
    },
  },
  {
    id: COLOR_PEAK_LABEL_LAYER_ID,
    type: "symbol",
    source: MODERN_REFERENCE_SOURCE_ID,
    "source-layer": "mountain_peak",
    minzoom: 8,
    layout: {
      visibility: "none",
      "text-field": ["coalesce", ["get", "name:zh"], ["get", "name"]],
      "text-font": ["Noto Sans Regular"],
      "text-size": 9,
      "text-offset": [0, 0.8],
      "text-allow-overlap": false,
    },
    paint: {
      "text-color": "#6f665d",
      "text-halo-color": "rgba(247, 241, 230, 0.9)",
      "text-halo-width": 1,
    },
  },
];

export function referenceMode(modeId: ReferenceModeId): ReferenceMode {
  return REFERENCE_MODES.find((mode) => mode.id === modeId) ?? REFERENCE_MODES[0];
}

export const R2_REFERENCE_COMPLETENESS_CONTRACT = {
  modeId: "r2_minimal_modern" as const,
  geometryLayerIds: [WATER_LAYER_ID, WATERWAY_LAYER_ID, MAJOR_ROAD_LAYER_ID],
  labelLayerIds: [SETTLEMENT_LABEL_LAYER_ID],
  sceneRequirements: {
    beijing: [MAJOR_ROAD_LAYER_ID, SETTLEMENT_LABEL_LAYER_ID],
    chengdu: [MAJOR_ROAD_LAYER_ID, SETTLEMENT_LABEL_LAYER_ID],
    qingdao: [WATER_LAYER_ID, SETTLEMENT_LABEL_LAYER_ID],
  },
} as const;

function hideAvailableReferenceLayers(map: MapLibreMap): void {
  for (const layerId of MODERN_REFERENCE_LAYER_IDS) {
    if (!map.getLayer(layerId)) continue;
    map.setLayoutProperty(layerId, "visibility", "none");
  }
}

function ensureReferenceLayers(map: MapLibreMap, layerIds: Set<string>): void {
  if (!map.getSource(MODERN_REFERENCE_SOURCE_ID)) {
    map.addSource(MODERN_REFERENCE_SOURCE_ID, {
      type: "vector",
      url: MODERN_REFERENCE_SOURCE_URL,
      attribution:
        '<a href="https://openfreemap.org/">OpenFreeMap</a> · ' +
        '<a href="https://openmaptiles.org/">© OpenMapTiles</a> · ' +
        '<a href="https://www.openstreetmap.org/copyright">© OpenStreetMap contributors</a>',
    });
  }
  for (const layer of MODERN_REFERENCE_LAYERS) {
    if (layerIds.has(layer.id) && !map.getLayer(layer.id)) map.addLayer(layer);
  }
}

export function applyReferenceMode(
  map: MapLibreMap,
  modeId: ReferenceModeId,
): ReferenceApplyResult {
  const mode = referenceMode(modeId);
  try {
    if (modeId === "r0_grid") {
      hideAvailableReferenceLayers(map);
      return { status: "off", geometryLayerCount: 0, labelLayerCount: 0 };
    }
    const visibleLayerIds = new Set([
      ...mode.geometryLayerIds,
      ...mode.labelLayerIds,
    ]);
    ensureReferenceLayers(map, visibleLayerIds);
    for (const layerId of MODERN_REFERENCE_LAYER_IDS) {
      map.setLayoutProperty(
        layerId,
        "visibility",
        visibleLayerIds.has(layerId) ? "visible" : "none",
      );
    }
    return {
      status: "loading",
      geometryLayerCount: mode.geometryLayerIds.length,
      labelLayerCount: mode.labelLayerIds.length,
    };
  } catch (reason) {
    try {
      hideAvailableReferenceLayers(map);
    } catch {
      // A partially initialized remote source must never block historical markers.
    }
    return {
      status: "unavailable",
      geometryLayerCount: 0,
      labelLayerCount: 0,
      error: String(reason),
    };
  }
}

export function isModernReferenceMapError(event: unknown): boolean {
  if (!event || typeof event !== "object") return false;
  const candidate = event as {
    sourceId?: unknown;
    error?: { message?: unknown };
  };
  if (candidate.sourceId === MODERN_REFERENCE_SOURCE_ID) return true;
  const urls =
    String(candidate.error?.message ?? "").match(/https?:\/\/[^\s"'<>]+/g) ?? [];
  return urls.some((url) => {
    try {
      return new URL(url).hostname === MODERN_REFERENCE_HOSTNAME;
    } catch {
      return false;
    }
  });
}
