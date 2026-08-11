import type { HistoricalFeature } from "../types";
import {
  displayFamily,
  familyConfig,
  isVisibleForMode,
  type DisplayFamily,
} from "./hierarchy";
import type { AnchorCoordinate } from "./ranking";

export interface DisplayUnit {
  id: string;
  kind: "feature" | "colocated_group";
  coordinate: [number, number];
  family: DisplayFamily;
  label: string;
  representative: HistoricalFeature;
  members: HistoricalFeature[];
}

export interface SemanticZoomSelection {
  units: DisplayUnit[];
  activeFamilies: DisplayFamily[];
  eligibleFamilies: DisplayFamily[];
  visibleFamilies: DisplayFamily[];
  eligibleFeatureCount: number;
  semanticHiddenFeatureCount: number;
  collisionHiddenUnitCount: number;
}

function compareText(first: string, second: string): number {
  return first < second ? -1 : first > second ? 1 : 0;
}

function featureOrder(first: HistoricalFeature, second: HistoricalFeature): number {
  return (
    familyConfig(displayFamily(first)).labelPriority -
      familyConfig(displayFamily(second)).labelPriority ||
    compareText(first.properties.tgaz_id, second.properties.tgaz_id)
  );
}

function coordinateKey(feature: HistoricalFeature): string {
  const [lon, lat] = feature.geometry.coordinates;
  return `${lon}:${lat}`;
}

export function groupCoLocatedFeatures(
  features: readonly HistoricalFeature[],
): DisplayUnit[] {
  const groups = new Map<string, HistoricalFeature[]>();
  for (const feature of features) {
    const key = coordinateKey(feature);
    groups.set(key, [...(groups.get(key) ?? []), feature]);
  }
  return [...groups.entries()]
    .map(([key, members]) => {
      const ordered = [...members].sort(featureOrder);
      const representative = ordered[0];
      const memberIds = ordered.map((item) => item.properties.tgaz_id).sort();
      return {
        id: memberIds.length === 1 ? representative.id : `colocated:${key}:${memberIds.join("+")}`,
        kind: memberIds.length === 1 ? "feature" as const : "colocated_group" as const,
        coordinate: representative.geometry.coordinates,
        family: displayFamily(representative),
        label: memberIds.length === 1
          ? representative.properties.name
          : `${representative.properties.name}等 · 同址 ${memberIds.length} 条`,
        representative,
        members: ordered,
      };
    })
    .sort((first, second) =>
      familyConfig(first.family).labelPriority - familyConfig(second.family).labelPriority ||
      Number(second.kind === "colocated_group") - Number(first.kind === "colocated_group") ||
      featureOrder(first.representative, second.representative),
    );
}

function orderedFamilies(families: Iterable<DisplayFamily>): DisplayFamily[] {
  return [...new Set(families)].sort(
    (first, second) => familyConfig(first).labelPriority - familyConfig(second).labelPriority,
  );
}

export function selectSemanticZoomUnits(
  features: readonly HistoricalFeature[],
  _anchor: AnchorCoordinate,
  _radiusKm: number,
  _zoom: number,
  enabledFamilies?: ReadonlySet<DisplayFamily>,
): SemanticZoomSelection {
  const userFeatures = features.filter((feature) => isVisibleForMode(feature, false));
  const activeFamilies = orderedFamilies(userFeatures.map(displayFamily));
  const enabled = enabledFamilies ?? new Set(
    activeFamilies,
  );
  const eligibleFeatures = userFeatures.filter((feature) =>
    enabled.has(displayFamily(feature)),
  );
  const eligibleFamilies = orderedFamilies(eligibleFeatures.map(displayFamily));
  const units = groupCoLocatedFeatures(eligibleFeatures);
  return {
    units,
    activeFamilies,
    eligibleFamilies,
    visibleFamilies: orderedFamilies(units.map((unit) => unit.family)),
    eligibleFeatureCount: eligibleFeatures.length,
    semanticHiddenFeatureCount: userFeatures.length - eligibleFeatures.length,
    collisionHiddenUnitCount: 0,
  };
}

export type LabelPlacement = "right" | "upper-right" | "lower-right" | "left";

export interface StableLabelPlacement {
  placement: LabelPlacement;
  offsetX: number;
  offsetY: number;
}

function stableHash(value: string): number {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

export function stableLabelPlacement(unitId: string, zoom: number): StableLabelPlacement {
  const zoomBucket = zoom < 6.8 ? "low" : zoom < 8.6 ? "medium" : zoom < 10.5 ? "high" : "maximum";
  const hash = stableHash(`${unitId}:${zoomBucket}`);
  const placement = (["right", "upper-right", "lower-right", "left"] as const)[hash % 4];
  const horizontal = 13 + (hash % 3) * 2;
  if (placement === "left") return { placement, offsetX: -horizontal, offsetY: 0 };
  if (placement === "upper-right") return { placement, offsetX: horizontal, offsetY: -10 };
  if (placement === "lower-right") return { placement, offsetX: horizontal, offsetY: 10 };
  return { placement, offsetX: horizontal, offsetY: 0 };
}
