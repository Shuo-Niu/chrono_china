import type { HistoricalFeature } from "../types";
import { zoomBand, type ZoomBand } from "./hierarchy";

export type HistoricalUnitCategory =
  | "province"
  | "dao_lu"
  | "prefecture"
  | "commandery"
  | "county"
  | "military_special"
  | "unclassified";

export interface HistoricalUnitCategoryConfig {
  id: HistoricalUnitCategory;
  labelZh: string;
  rawTypes: readonly string[];
  descriptionZh: string;
  shape: "diamond" | "square" | "circle" | "triangle" | "hexagon";
  sizeByZoom: Record<ZoomBand, number>;
  fill: string;
  stroke: string;
  halo: string;
  labelPriority: number;
  userVisible: boolean;
}

export const HISTORICAL_UNIT_CATEGORY_REGISTRY: readonly HistoricalUnitCategoryConfig[] = [
  {
    id: "province",
    labelZh: "省与行省",
    rawTypes: ["省", "行省", "省级", "王畿"],
    descriptionZh: "省、行省、省级、王畿",
    shape: "square",
    sizeByZoom: { low: 16, medium: 17, high: 18, maximum: 19 },
    fill: "#8f3e29",
    stroke: "#18333f",
    halo: "#fffaf0",
    labelPriority: 0,
    userVisible: true,
  },
  {
    id: "dao_lu",
    labelZh: "道与路",
    rawTypes: ["道", "路"],
    descriptionZh: "道、路",
    shape: "diamond",
    sizeByZoom: { low: 14, medium: 15, high: 16, maximum: 17 },
    fill: "#9d442b",
    stroke: "#18333f",
    halo: "#fffaf0",
    labelPriority: 1,
    userVisible: true,
  },
  {
    id: "prefecture",
    labelZh: "府州厅",
    rawTypes: ["府", "州", "直隶州", "厅"],
    descriptionZh: "府、州、直隶州、厅",
    shape: "circle",
    sizeByZoom: { low: 13, medium: 14, high: 15, maximum: 16 },
    fill: "#a34a2e",
    stroke: "#18333f",
    halo: "#fffaf0",
    labelPriority: 2,
    userVisible: true,
  },
  {
    id: "commandery",
    labelZh: "郡与侯国",
    rawTypes: ["郡", "侨郡", "侯国"],
    descriptionZh: "郡、侨郡、侯国",
    shape: "hexagon",
    sizeByZoom: { low: 12, medium: 13, high: 14, maximum: 15 },
    fill: "#aa5336",
    stroke: "#18333f",
    halo: "#fffaf0",
    labelPriority: 3,
    userVisible: true,
  },
  {
    id: "county",
    labelZh: "县",
    rawTypes: ["县", "侨县"],
    descriptionZh: "县、侨县",
    shape: "circle",
    sizeByZoom: { low: 9, medium: 11, high: 12, maximum: 13 },
    fill: "#ad5d42",
    stroke: "#6f301f",
    halo: "#fffaf0",
    labelPriority: 4,
    userVisible: true,
  },
  {
    id: "military_special",
    labelZh: "军政特殊",
    rawTypes: ["军", "监", "军镇", "防镇"],
    descriptionZh: "军、监、军镇、防镇",
    shape: "triangle",
    sizeByZoom: { low: 10, medium: 11, high: 12, maximum: 13 },
    fill: "#77584c",
    stroke: "#18333f",
    halo: "#fffaf0",
    labelPriority: 5,
    userVisible: true,
  },
  {
    id: "unclassified",
    labelZh: "其他来源类型（开发者）",
    rawTypes: [],
    descriptionZh: "未列入 User Mode 的来源类型，包括村镇、亭、政权、国及其他未分类类型",
    shape: "hexagon",
    sizeByZoom: { low: 8, medium: 9, high: 10, maximum: 11 },
    fill: "#806457",
    stroke: "#473b35",
    halo: "#fffaf0",
    labelPriority: 6,
    userVisible: false,
  },
] as const;

const CONFIG_BY_ID = new Map(HISTORICAL_UNIT_CATEGORY_REGISTRY.map((item) => [item.id, item]));
const CATEGORY_BY_RAW_TYPE = new Map(
  HISTORICAL_UNIT_CATEGORY_REGISTRY.flatMap((item) =>
    item.rawTypes.map((rawType) => [rawType, item.id] as const),
  ),
);

export function historicalUnitCategoryFromRawType(rawType: string): HistoricalUnitCategory {
  return CATEGORY_BY_RAW_TYPE.get(rawType) ?? "unclassified";
}

export function historicalUnitCategory(feature: HistoricalFeature): HistoricalUnitCategory {
  return historicalUnitCategoryFromRawType(feature.properties.feature_type);
}

export function unitCategoryConfig(category: HistoricalUnitCategory): HistoricalUnitCategoryConfig {
  return CONFIG_BY_ID.get(category)!;
}

export function isHistoricalUnitVisibleForUser(feature: HistoricalFeature): boolean {
  return unitCategoryConfig(historicalUnitCategory(feature)).userVisible;
}

export function unitCategoryMarkerVariables(
  category: HistoricalUnitCategory,
  zoom: number,
): Record<string, string> {
  const config = unitCategoryConfig(category);
  return {
    "--history-marker-size": `${config.sizeByZoom[zoomBand(zoom)]}px`,
    "--history-marker-fill": config.fill,
    "--history-marker-stroke": config.stroke,
    "--history-marker-halo": config.halo,
  };
}
