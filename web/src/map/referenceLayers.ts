import { layers, namedFlavor } from "@protomaps/basemaps";
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

export const MODERN_REFERENCE_SOURCE_ID = "chronochina-offline-reference";
export const MODERN_REFERENCE_RASTER_SOURCE_ID = "chronochina-offline-reference-unused";
export const OFFLINE_REFERENCE_ARCHIVE_PATH = "/reference/china_z9.pmtiles";
export const OFFLINE_REFERENCE_GLYPHS_PATH = "/reference/assets/fonts/{fontstack}/{range}.pbf";
export const OFFLINE_REFERENCE_SPRITE_PATH = "/reference/assets/sprites/v4/light";

function absoluteAssetUrl(path: string): string {
  if (typeof window === "undefined") return path;
  return new URL(path, window.location.href).toString();
}

export function offlineReferenceArchiveAssetUrl(): string {
  return absoluteAssetUrl(OFFLINE_REFERENCE_ARCHIVE_PATH);
}

export function offlineReferenceArchiveUrl(): string {
  return `pmtiles://${offlineReferenceArchiveAssetUrl()}`;
}

export function offlineReferenceGlyphsUrl(): string {
  const templatedPath = OFFLINE_REFERENCE_GLYPHS_PATH
    .replace("{fontstack}", "__FONTSTACK__")
    .replace("{range}", "__RANGE__");
  return absoluteAssetUrl(templatedPath)
    .replace("__FONTSTACK__", "{fontstack}")
    .replace("__RANGE__", "{range}");
}

export function offlineReferenceSpriteUrl(): string {
  return absoluteAssetUrl(OFFLINE_REFERENCE_SPRITE_PATH);
}

function referenceLayerId(id: string): string {
  return `reference-${id}`;
}

const GENERATED_LAYERS = layers(
  MODERN_REFERENCE_SOURCE_ID,
  namedFlavor("light"),
  { lang: "zh-Hans" },
).map((layer) => ({
  ...layer,
  id: referenceLayerId(layer.id),
  layout: { ...layer.layout, visibility: "none" as const },
})) as LayerSpecification[];

const BY_ID = new Map(GENERATED_LAYERS.map((layer) => [layer.id, layer]));
const ALL_IDS = GENERATED_LAYERS.map((layer) => layer.id);
const PHYSICAL_NAMES = new Set([
  "background", "earth", "landcover", "water", "water_stream", "water_river",
]);
const MINIMAL_NAMES = new Set([
  ...PHYSICAL_NAMES,
  "roads_major_casing_early", "roads_major", "roads_highway_casing_early", "roads_highway",
  "boundaries_country", "boundaries", "places_locality", "places_region", "places_country",
]);
const ADMIN_NAMES = new Set([
  ...PHYSICAL_NAMES, "boundaries_country", "boundaries", "places_region", "places_country",
]);

function idsFor(names: ReadonlySet<string>): string[] {
  return [...names].map(referenceLayerId).filter((id) => BY_ID.has(id));
}

function splitByType(ids: readonly string[], symbol: boolean): string[] {
  return ids.filter((id) => (BY_ID.get(id)?.type === "symbol") === symbol);
}

function modeFromIds(
  id: ReferenceModeId,
  code: ReferenceMode["code"],
  label: string,
  description: string,
  layerIds: string[],
): ReferenceMode {
  return {
    id,
    code,
    label,
    description,
    geometryLayerIds: splitByType(layerIds, false),
    labelLayerIds: splitByType(layerIds, true),
  };
}

export const REFERENCE_MODES: ReferenceMode[] = [
  modeFromIds("r0_grid", "R0", "抽象网格", "不显示现代地理参考。", []),
  modeFromIds("r1_physical", "R1", "极简", "离线轮廓、水体与植被底图。", idsFor(PHYSICAL_NAMES)),
  modeFromIds(
    "r2_minimal_modern",
    "R2",
    "标准",
    "离线自然地理、主要道路、现代行政线与稀疏地名。",
    idsFor(MINIMAL_NAMES),
  ),
  modeFromIds(
    "r3_modern_admin",
    "R3",
    "现代行政参考",
    "内置离线现代行政线与区域地名；不是历史边界。",
    idsFor(ADMIN_NAMES),
  ),
  modeFromIds(
    "r4_color_geography",
    "R4",
    "丰富",
    "离线水体、植被、土地利用、道路与地名；不是卫星影像。",
    ALL_IDS,
  ),
];

export const MODERN_REFERENCE_LAYER_IDS = ALL_IDS;

export const R2_REFERENCE_COMPLETENESS_CONTRACT = {
  modeId: "r2_minimal_modern" as const,
  geometryLayerIds: [
    referenceLayerId("earth"),
    referenceLayerId("water"),
    referenceLayerId("roads_major"),
    referenceLayerId("boundaries"),
  ],
  labelLayerIds: [referenceLayerId("places_locality")],
  sceneRequirements: {
    beijing: [referenceLayerId("roads_major"), referenceLayerId("places_locality")],
    chengdu: [referenceLayerId("roads_major"), referenceLayerId("places_locality")],
    qingdao: [referenceLayerId("water"), referenceLayerId("places_locality")],
  },
} as const;

export function referenceMode(modeId: ReferenceModeId): ReferenceMode {
  return REFERENCE_MODES.find((mode) => mode.id === modeId) ?? REFERENCE_MODES[0];
}

function hideAvailableReferenceLayers(map: MapLibreMap): void {
  for (const layerId of MODERN_REFERENCE_LAYER_IDS) {
    if (map.getLayer(layerId)) map.setLayoutProperty(layerId, "visibility", "none");
  }
}

function ensureReferenceLayers(map: MapLibreMap, layerIds: ReadonlySet<string>): void {
  const style = map.getStyle();
  if (!style.glyphs) map.setGlyphs(offlineReferenceGlyphsUrl());
  if (!style.sprite) map.setSprite(offlineReferenceSpriteUrl());
  if (!map.getSource(MODERN_REFERENCE_SOURCE_ID)) {
    map.addSource(MODERN_REFERENCE_SOURCE_ID, {
      type: "vector",
      url: offlineReferenceArchiveUrl(),
      attribution:
        '<a href="https://protomaps.com/">Protomaps</a> · ' +
        '<a href="https://www.openstreetmap.org/copyright">© OpenStreetMap contributors</a>',
    });
  }
  for (const layer of GENERATED_LAYERS) {
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
    const visibleLayerIds = new Set([...mode.geometryLayerIds, ...mode.labelLayerIds]);
    ensureReferenceLayers(map, visibleLayerIds);
    for (const layerId of MODERN_REFERENCE_LAYER_IDS) {
      if (map.getLayer(layerId)) {
        map.setLayoutProperty(layerId, "visibility", visibleLayerIds.has(layerId) ? "visible" : "none");
      }
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
      // Reference failure must never block historical markers.
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
  const candidate = event as { sourceId?: unknown; error?: { message?: unknown } };
  if (candidate.sourceId === MODERN_REFERENCE_SOURCE_ID) return true;
  return String(candidate.error?.message ?? "").includes(OFFLINE_REFERENCE_ARCHIVE_PATH);
}
