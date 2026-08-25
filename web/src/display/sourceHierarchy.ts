import type { CompactHistoricalIndex, CompactRecord } from "../explore/viewportQuery";
import type { HistoricalFeature } from "../types";
import { displayFamilyFromRawType } from "./hierarchy";

export type HistoricalLayerTier =
  | "upper_governance"
  | "regional_governance"
  | "local_governance"
  | "basic_administration"
  | "unresolved";

export interface HistoricalLayerTierConfig {
  id: HistoricalLayerTier;
  labelZh: string;
  descriptionZh: string;
  shape: "diamond" | "square" | "circle" | "hexagon";
  fill: string;
  stroke: string;
  halo: string;
  labelPriority: number;
  userVisible: boolean;
}

export interface SourceHierarchyClassification {
  tier: HistoricalLayerTier;
  method: "explicit_polity_chain" | "explicit_high_admin_chain" | "audited_type_fallback" | "unresolved";
  parentChainIds: string[];
  issue: "missing_parent" | "cycle" | "none";
}

export interface SourceHierarchyNode {
  sourceRecordId: string;
  name: string;
  featureType: string;
  validFrom: number;
  validTo: number;
  activeAtSelectedYear: boolean;
}

export interface SourceHierarchyIndex {
  byId: ReadonlyMap<string, CompactRecord>;
  childrenByParentId: ReadonlyMap<string, readonly CompactRecord[]>;
  classifications: ReadonlyMap<string, SourceHierarchyClassification>;
}

export const HISTORICAL_LAYER_TIER_REGISTRY: readonly HistoricalLayerTierConfig[] = [
  {
    id: "upper_governance",
    labelZh: "上层统辖",
    descriptionZh: "由来源父链识别的政权直属或省级统辖单位",
    shape: "square",
    fill: "#8f3e29",
    stroke: "#18333f",
    halo: "#fffaf0",
    labelPriority: 0,
    userVisible: true,
  },
  {
    id: "regional_governance",
    labelZh: "区域统辖",
    descriptionZh: "由来源父链识别的第二层区域统辖单位",
    shape: "diamond",
    fill: "#a34a2e",
    stroke: "#18333f",
    halo: "#fffaf0",
    labelPriority: 1,
    userVisible: true,
  },
  {
    id: "local_governance",
    labelZh: "地方统辖",
    descriptionZh: "由来源父链识别的地方统辖单位",
    shape: "circle",
    fill: "#ad5337",
    stroke: "#6f301f",
    halo: "#fffaf0",
    labelPriority: 2,
    userVisible: true,
  },
  {
    id: "basic_administration",
    labelZh: "基层行政",
    descriptionZh: "由来源父链或审计类型识别的基层行政单位",
    shape: "circle",
    fill: "#b86a4d",
    stroke: "#713d2b",
    halo: "#fffaf0",
    labelPriority: 3,
    userVisible: true,
  },
  {
    id: "unresolved",
    labelZh: "层级未定（开发者）",
    descriptionZh: "来源父链和审计类型均不足以安全确定层级",
    shape: "hexagon",
    fill: "#806457",
    stroke: "#473b35",
    halo: "#fffaf0",
    labelPriority: 4,
    userVisible: false,
  },
] as const;

const CONFIG_BY_ID = new Map(HISTORICAL_LAYER_TIER_REGISTRY.map((item) => [item.id, item]));
const HIDDEN_USER_TYPES = new Set(["政权", "国", "村镇", "亭"]);
const HIGH_ADMIN_TYPES = new Set(["省", "行省", "省级", "王畿"]);

function tierByDistance(distance: number): HistoricalLayerTier {
  if (distance <= 1) return "upper_governance";
  if (distance === 2) return "regional_governance";
  if (distance === 3) return "local_governance";
  return "basic_administration";
}

function fallbackTier(rawType: string): HistoricalLayerTier {
  const family = displayFamilyFromRawType(rawType);
  if (family === "high_admin") return "upper_governance";
  if (family === "regional_admin") return "regional_governance";
  if (family === "county" || family === "settlement") return "basic_administration";
  return "unresolved";
}

function classifyRecord(
  record: CompactRecord,
  byId: ReadonlyMap<string, CompactRecord>,
): SourceHierarchyClassification {
  const parentChainIds: string[] = [];
  const visited = new Set([record[0]]);
  let cursor = record;
  let missingParent = false;
  let cycle = false;
  let highAdminDistance: number | null = HIGH_ADMIN_TYPES.has(record[7]) ? 0 : null;

  while (cursor[8]) {
    const parentId = cursor[8];
    if (visited.has(parentId)) {
      cycle = true;
      break;
    }
    visited.add(parentId);
    parentChainIds.push(parentId);
    const parent = byId.get(parentId);
    if (!parent) {
      missingParent = true;
      break;
    }
    const distance = parentChainIds.length;
    if (highAdminDistance === null && HIGH_ADMIN_TYPES.has(parent[7])) {
      highAdminDistance = distance;
    }
    if (parent[7] === "政权") {
      return {
        tier: tierByDistance(distance),
        method: "explicit_polity_chain",
        parentChainIds,
        issue: "none",
      };
    }
    cursor = parent;
  }

  if (!cycle && highAdminDistance !== null) {
    return {
      tier: tierByDistance(highAdminDistance + 1),
      method: "explicit_high_admin_chain",
      parentChainIds,
      issue: missingParent ? "missing_parent" : "none",
    };
  }

  const tier = fallbackTier(record[7]);
  return {
    tier,
    method: tier === "unresolved" ? "unresolved" : "audited_type_fallback",
    parentChainIds,
    issue: cycle ? "cycle" : missingParent ? "missing_parent" : "none",
  };
}

export function buildSourceHierarchyIndex(index: CompactHistoricalIndex): SourceHierarchyIndex {
  const byId = new Map(index.records.map((record) => [record[0], record] as const));
  const children = new Map<string, CompactRecord[]>();
  for (const record of index.records) {
    if (!record[8]) continue;
    const current = children.get(record[8]) ?? [];
    current.push(record);
    children.set(record[8], current);
  }
  const classifications = new Map<string, SourceHierarchyClassification>();
  for (const record of index.records) {
    classifications.set(record[0], classifyRecord(record, byId));
  }
  return { byId, childrenByParentId: children, classifications };
}

export function historicalLayerTier(
  feature: HistoricalFeature,
  hierarchy: SourceHierarchyIndex | null,
): HistoricalLayerTier {
  return hierarchy?.classifications.get(feature.properties.source_record_id)?.tier ??
    fallbackTier(feature.properties.feature_type);
}

export function tierConfig(tier: HistoricalLayerTier): HistoricalLayerTierConfig {
  return CONFIG_BY_ID.get(tier)!;
}

export function isHistoricalFeatureVisibleForUser(
  feature: HistoricalFeature,
  hierarchy: SourceHierarchyIndex | null,
): boolean {
  if (HIDDEN_USER_TYPES.has(feature.properties.feature_type)) return false;
  return tierConfig(historicalLayerTier(feature, hierarchy)).userVisible;
}

export function hierarchyBreadcrumb(
  hierarchy: SourceHierarchyIndex | null,
  sourceRecordId: string,
  year: number,
): SourceHierarchyNode[] {
  if (!hierarchy) return [];
  const classification = hierarchy.classifications.get(sourceRecordId);
  if (!classification) return [];
  return classification.parentChainIds.flatMap((id) => {
    const record = hierarchy.byId.get(id);
    if (!record) return [];
    return [{
      sourceRecordId: id,
      name: record[1],
      featureType: record[7],
      validFrom: record[3],
      validTo: record[4],
      activeAtSelectedYear: record[3] <= year && year <= record[4],
    }];
  });
}

export function activeDirectSubordinates(
  hierarchy: SourceHierarchyIndex | null,
  sourceRecordId: string,
  year: number,
): SourceHierarchyNode[] {
  if (!hierarchy) return [];
  return (hierarchy.childrenByParentId.get(sourceRecordId) ?? [])
    .filter((record) => record[3] <= year && year <= record[4])
    .map((record) => ({
      sourceRecordId: record[0],
      name: record[1],
      featureType: record[7],
      validFrom: record[3],
      validTo: record[4],
      activeAtSelectedYear: true,
    }))
    .sort((first, second) => first.name.localeCompare(second.name, "zh-Hans-CN"));
}

export function tierMarkerVariables(
  tier: HistoricalLayerTier,
  zoom: number,
): Record<string, string> {
  const config = tierConfig(tier);
  const size = config.labelPriority === 0
    ? (zoom < 6.8 ? 16 : zoom < 10.5 ? 18 : 19)
    : config.labelPriority === 1
      ? (zoom < 6.8 ? 13 : zoom < 10.5 ? 15 : 16)
      : config.labelPriority === 2
        ? (zoom < 6.8 ? 10 : zoom < 10.5 ? 12 : 13)
        : (zoom < 6.8 ? 8 : zoom < 10.5 ? 10 : 11);
  return {
    "--history-marker-size": `${size}px`,
    "--history-marker-fill": config.fill,
    "--history-marker-stroke": config.stroke,
    "--history-marker-halo": config.halo,
  };
}