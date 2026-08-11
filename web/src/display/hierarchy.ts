import type { HistoricalFeature } from "../types";

export type DisplayFamily =
  | "polity"
  | "high_admin"
  | "regional_admin"
  | "county"
  | "settlement"
  | "other";

export type ZoomBand = "low" | "medium" | "high" | "maximum";

export interface DisplayFamilyConfig {
  id: DisplayFamily;
  labelZh: string;
  rawTypes: readonly string[];
  shape: "diamond" | "square" | "circle" | "triangle" | "hexagon";
  sizeByZoom: Record<ZoomBand, number>;
  fill: string;
  stroke: string;
  halo: string;
  labelPriority: number;
  userVisible: boolean;
  developerVisible: boolean;
  legend: boolean;
}

export const DISPLAY_FAMILY_REGISTRY: readonly DisplayFamilyConfig[] = [
  {
    id: "high_admin",
    labelZh: "省、行省、省级、王畿",
    rawTypes: ["省", "行省", "省级", "王畿"],
    shape: "square",
    sizeByZoom: { low: 16, medium: 17, high: 18, maximum: 19 },
    fill: "#8f3e29",
    stroke: "#18333f",
    halo: "#fffaf0",
    labelPriority: 0,
    userVisible: true,
    developerVisible: true,
    legend: true,
  },
  {
    id: "regional_admin",
    labelZh: "郡、侨郡、府、州、直隶州、路、道、侯国、厅、军、军镇、防镇、监",
    rawTypes: [
      "郡", "侨郡", "府", "州", "直隶州", "路", "道", "侯国", "厅", "军", "军镇", "防镇", "监",
    ],
    shape: "diamond",
    sizeByZoom: { low: 13, medium: 14, high: 15, maximum: 16 },
    fill: "#a34a2e",
    stroke: "#18333f",
    halo: "#fffaf0",
    labelPriority: 1,
    userVisible: true,
    developerVisible: true,
    legend: true,
  },
  {
    id: "county",
    labelZh: "县、侨县",
    rawTypes: ["县", "侨县"],
    shape: "circle",
    sizeByZoom: { low: 9, medium: 11, high: 12, maximum: 13 },
    fill: "#ad5337",
    stroke: "#6f301f",
    halo: "#fffaf0",
    labelPriority: 2,
    userVisible: true,
    developerVisible: true,
    legend: true,
  },
  {
    id: "settlement",
    labelZh: "村镇、亭",
    rawTypes: ["村镇", "亭"],
    shape: "triangle",
    sizeByZoom: { low: 7, medium: 8, high: 9, maximum: 10 },
    fill: "#b86a4d",
    stroke: "#713d2b",
    halo: "#fffaf0",
    labelPriority: 3,
    userVisible: true,
    developerVisible: true,
    legend: true,
  },
  {
    id: "other",
    labelZh: "其他未分类来源类型",
    rawTypes: [],
    shape: "hexagon",
    sizeByZoom: { low: 8, medium: 9, high: 10, maximum: 11 },
    fill: "#806457",
    stroke: "#473b35",
    halo: "#fffaf0",
    labelPriority: 4,
    userVisible: true,
    developerVisible: true,
    legend: true,
  },
  {
    id: "polity",
    labelZh: "政权、国（开发者）",
    rawTypes: ["政权", "国"],
    shape: "diamond",
    sizeByZoom: { low: 15, medium: 16, high: 17, maximum: 18 },
    fill: "#64526f",
    stroke: "#2f2635",
    halo: "#fffaf0",
    labelPriority: 5,
    userVisible: false,
    developerVisible: true,
    legend: true,
  },
] as const;

const CONFIG_BY_ID = new Map(DISPLAY_FAMILY_REGISTRY.map((item) => [item.id, item]));
const FAMILY_BY_RAW_TYPE = new Map(
  DISPLAY_FAMILY_REGISTRY.flatMap((item) =>
    item.rawTypes.map((rawType) => [rawType, item.id] as const),
  ),
);

export function zoomBand(zoom: number): ZoomBand {
  if (zoom < 6.8) return "low";
  if (zoom < 8.6) return "medium";
  if (zoom < 10.5) return "high";
  return "maximum";
}

export function familyConfig(family: DisplayFamily): DisplayFamilyConfig {
  return CONFIG_BY_ID.get(family)!;
}

export function displayFamily(feature: HistoricalFeature): DisplayFamily {
  return FAMILY_BY_RAW_TYPE.get(feature.properties.feature_type) ?? "other";
}

export function displayFamilyPriority(feature: HistoricalFeature): number {
  return familyConfig(displayFamily(feature)).labelPriority;
}

export function isVisibleForMode(
  feature: HistoricalFeature,
  developerMode: boolean,
): boolean {
  const config = familyConfig(displayFamily(feature));
  return developerMode ? config.developerVisible : config.userVisible;
}

export function markerVariables(family: DisplayFamily, zoom: number): Record<string, string> {
  const config = familyConfig(family);
  return {
    "--history-marker-size": `${config.sizeByZoom[zoomBand(zoom)]}px`,
    "--history-marker-fill": config.fill,
    "--history-marker-stroke": config.stroke,
    "--history-marker-halo": config.halo,
  };
}
