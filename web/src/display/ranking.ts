import type { HistoricalFeature } from "../types";
import { displayFamilyPriority } from "./hierarchy";

export type DisplayStrategy =
  | "nearest_n"
  | "type_diverse_distance"
  | "type_diverse_spatial";

export const DISPLAY_STRATEGIES: Array<{
  id: DisplayStrategy;
  label: string;
}> = [
  { id: "nearest_n", label: "Nearest N" },
  { id: "type_diverse_distance", label: "Type Diverse" },
  { id: "type_diverse_spatial", label: "Type + Spatial" },
];

export const DISPLAY_CONFIG = {
  nearestPointLimit: 12,
  diversePointLimit: 30,
  labelLimit: 12,
  spatialGridSize: 4,
  collisionCanvasWidthPx: 900,
  collisionCanvasHeightPx: 600,
  collisionLabelHeightPx: 24,
  collisionCharacterWidthPx: 14,
  collisionLabelPaddingPx: 16,
} as const;

export interface DisplaySelection {
  points: HistoricalFeature[];
  labels: HistoricalFeature[];
  labelIds: Set<string>;
  collisionHiddenLabelCount: number;
  collisionMetricKind: "estimated";
}

export interface AnchorCoordinate {
  lon: number;
  lat: number;
}

function compareText(first: string, second: string): number {
  return first < second ? -1 : first > second ? 1 : 0;
}

function compareDistance(first: HistoricalFeature, second: HistoricalFeature): number {
  return (
    first.properties.distance_to_anchor_km -
      second.properties.distance_to_anchor_km ||
    compareText(first.properties.tgaz_id, second.properties.tgaz_id)
  );
}

function typeGroup(feature: HistoricalFeature): string {
  return feature.properties.display_type_group || feature.properties.feature_type || "未分类";
}

export function rankNearest(features: readonly HistoricalFeature[]): HistoricalFeature[] {
  return [...features].sort(compareDistance);
}

export function rankTypeDiverse(
  features: readonly HistoricalFeature[],
): HistoricalFeature[] {
  const groups = new Map<string, HistoricalFeature[]>();
  for (const feature of features) {
    const group = typeGroup(feature);
    groups.set(group, [...(groups.get(group) ?? []), feature]);
  }
  for (const group of groups.values()) group.sort(compareDistance);
  const names = [...groups.keys()].sort((first, second) => {
    const firstFeature = groups.get(first)![0];
    const secondFeature = groups.get(second)![0];
    return (
      compareDistance(firstFeature, secondFeature) || compareText(first, second)
    );
  });

  const ranked: HistoricalFeature[] = [];
  for (let round = 0; ; round += 1) {
    let added = false;
    for (const name of names) {
      const feature = groups.get(name)?.[round];
      if (feature) {
        ranked.push(feature);
        added = true;
      }
    }
    if (!added) return ranked;
  }
}

function haversineBetween(first: HistoricalFeature, second: HistoricalFeature): number {
  const [firstLon, firstLat] = first.geometry.coordinates;
  const [secondLon, secondLat] = second.geometry.coordinates;
  const toRadians = (value: number) => (value * Math.PI) / 180;
  const deltaLat = toRadians(secondLat - firstLat);
  const deltaLon = toRadians(secondLon - firstLon);
  const firstLatRadians = toRadians(firstLat);
  const secondLatRadians = toRadians(secondLat);
  const a =
    Math.sin(deltaLat / 2) ** 2 +
    Math.cos(firstLatRadians) *
      Math.cos(secondLatRadians) *
      Math.sin(deltaLon / 2) ** 2;
  return 6371.0088 * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

export function rankTypeSpatial(
  features: readonly HistoricalFeature[],
  limit = features.length,
): HistoricalFeature[] {
  const base = rankTypeDiverse(features);
  const targetCount = Math.min(base.length, limit);
  if (targetCount === 0) return [];
  const baseRank = new Map(base.map((feature, index) => [feature.id, index]));
  const selected: HistoricalFeature[] = [];
  const selectedIds = new Set<string>();
  const selectedTypes = new Set<string>();

  for (const feature of base) {
    const group = typeGroup(feature);
    if (selectedTypes.has(group)) continue;
    selected.push(feature);
    selectedIds.add(feature.id);
    selectedTypes.add(group);
    if (selected.length >= targetCount) return selected;
  }

  const remaining = base.filter((feature) => !selectedIds.has(feature.id));
  while (remaining.length > 0 && selected.length < targetCount) {
    let chosenIndex = 0;
    let chosenSeparation = -1;
    for (let index = 0; index < remaining.length; index += 1) {
      const candidate = remaining[index];
      const separation = Math.min(
        ...selected.map((selectedFeature) =>
          haversineBetween(candidate, selectedFeature),
        ),
      );
      const chosen = remaining[chosenIndex];
      const earlierBaseRank =
        (baseRank.get(candidate.id) ?? Infinity) <
        (baseRank.get(chosen.id) ?? Infinity);
      const sameBaseRank = baseRank.get(candidate.id) === baseRank.get(chosen.id);
      const nearer =
        candidate.properties.distance_to_anchor_km <
        chosen.properties.distance_to_anchor_km;
      const sameDistance =
        candidate.properties.distance_to_anchor_km ===
        chosen.properties.distance_to_anchor_km;
      if (
        separation > chosenSeparation ||
        (separation === chosenSeparation && earlierBaseRank) ||
        (separation === chosenSeparation && sameBaseRank && nearer) ||
        (separation === chosenSeparation &&
          sameBaseRank &&
          sameDistance &&
          compareText(candidate.properties.tgaz_id, chosen.properties.tgaz_id) < 0)
      ) {
        chosenIndex = index;
        chosenSeparation = separation;
      }
    }
    selected.push(remaining.splice(chosenIndex, 1)[0]);
  }
  return selected;
}

export function selectDisplayPoints(
  features: readonly HistoricalFeature[],
  strategy: DisplayStrategy,
): HistoricalFeature[] {
  if (strategy === "nearest_n") {
    return rankNearest(features).slice(0, DISPLAY_CONFIG.nearestPointLimit);
  }
  if (strategy === "type_diverse_distance") {
    return rankTypeDiverse(features).slice(0, DISPLAY_CONFIG.diversePointLimit);
  }
  return rankTypeSpatial(features, DISPLAY_CONFIG.diversePointLimit);
}

function localCoordinates(
  feature: HistoricalFeature,
  anchor: AnchorCoordinate,
): [number, number] {
  const [lon, lat] = feature.geometry.coordinates;
  const wrappedLongitudeDelta = ((lon - anchor.lon + 540) % 360) - 180;
  return [
    wrappedLongitudeDelta * 111.32 * Math.cos((anchor.lat * Math.PI) / 180),
    (lat - anchor.lat) * 110.574,
  ];
}

export type Rectangle = [number, number, number, number];

export function labelRectangle(
  feature: HistoricalFeature,
  anchor: AnchorCoordinate,
  radiusKm: number,
  rank: number,
): Rectangle {
  const [xKm, yKm] = localCoordinates(feature, anchor);
  const x =
    DISPLAY_CONFIG.collisionCanvasWidthPx / 2 +
    (xKm / radiusKm) * DISPLAY_CONFIG.collisionCanvasWidthPx * 0.44;
  const y =
    DISPLAY_CONFIG.collisionCanvasHeightPx / 2 -
    (yKm / radiusKm) * DISPLAY_CONFIG.collisionCanvasHeightPx * 0.44;
  const laneOffset = [0, -10, 10][rank % 3];
  const characterCount = Math.min(
    14,
    Array.from(feature.properties.name || feature.properties.tgaz_id).length,
  );
  const width =
    DISPLAY_CONFIG.collisionLabelPaddingPx +
    characterCount * DISPLAY_CONFIG.collisionCharacterWidthPx;
  const height = DISPLAY_CONFIG.collisionLabelHeightPx;
  return [x + 9, y - height / 2 + laneOffset, x + 9 + width, y + height / 2 + laneOffset];
}

export function overlaps(first: Rectangle, second: Rectangle): boolean {
  return !(
    first[2] <= second[0] ||
    second[2] <= first[0] ||
    first[3] <= second[1] ||
    second[3] <= first[1]
  );
}

export function selectDisplayLabels(
  points: readonly HistoricalFeature[],
  anchor: AnchorCoordinate,
  radiusKm: number,
): { labels: HistoricalFeature[]; collisionHiddenLabelCount: number } {
  const labels: HistoricalFeature[] = [];
  const rectangles: Rectangle[] = [];
  let collisionHiddenLabelCount = 0;
  for (let rank = 0; rank < points.length; rank += 1) {
    if (labels.length >= DISPLAY_CONFIG.labelLimit) break;
    const rectangle = labelRectangle(points[rank], anchor, radiusKm, rank);
    if (rectangles.some((existing) => overlaps(rectangle, existing))) {
      collisionHiddenLabelCount += 1;
      continue;
    }
    labels.push(points[rank]);
    rectangles.push(rectangle);
  }
  return { labels, collisionHiddenLabelCount };
}

export function zoomLabelLimit(zoom: number): number {
  if (zoom < 6.8) return 6;
  if (zoom < 8.6) return 12;
  return 24;
}

function zoomAdjustedLabelRectangle(
  feature: HistoricalFeature,
  anchor: AnchorCoordinate,
  radiusKm: number,
  rank: number,
  zoom: number,
): Rectangle {
  const rectangle = labelRectangle(feature, anchor, radiusKm, rank);
  const centerX = DISPLAY_CONFIG.collisionCanvasWidthPx / 2;
  const centerY = DISPLAY_CONFIG.collisionCanvasHeightPx / 2;
  const scale = 2 ** (zoom - 7.4);
  const width = rectangle[2] - rectangle[0];
  const height = rectangle[3] - rectangle[1];
  const left = centerX + (rectangle[0] - centerX) * scale;
  const top = centerY + (rectangle[1] - centerY) * scale;
  return [left, top, left + width, top + height];
}

export function selectZoomAwareDisplayLabels(
  points: readonly HistoricalFeature[],
  anchor: AnchorCoordinate,
  radiusKm: number,
  zoom: number,
): { labels: HistoricalFeature[]; collisionHiddenLabelCount: number } {
  const ordered = points
    .map((feature, index) => ({ feature, index }))
    .sort(
      (first, second) =>
        displayFamilyPriority(first.feature) - displayFamilyPriority(second.feature) ||
        first.index - second.index,
    );
  const labels: HistoricalFeature[] = [];
  const rectangles: Rectangle[] = [];
  let collisionHiddenLabelCount = 0;
  for (const { feature, index } of ordered) {
    if (labels.length >= zoomLabelLimit(zoom)) break;
    const rectangle = zoomAdjustedLabelRectangle(
      feature,
      anchor,
      radiusKm,
      index,
      zoom,
    );
    if (rectangles.some((existing) => overlaps(rectangle, existing))) {
      collisionHiddenLabelCount += 1;
      continue;
    }
    labels.push(feature);
    rectangles.push(rectangle);
  }
  return { labels, collisionHiddenLabelCount };
}

export function selectDisplay(
  features: readonly HistoricalFeature[],
  strategy: DisplayStrategy,
  anchor: AnchorCoordinate,
  radiusKm: number,
): DisplaySelection {
  const points = selectDisplayPoints(features, strategy);
  const labelSelection = selectDisplayLabels(points, anchor, radiusKm);
  return {
    points,
    labels: labelSelection.labels,
    labelIds: new Set(labelSelection.labels.map((feature) => feature.id)),
    collisionHiddenLabelCount: labelSelection.collisionHiddenLabelCount,
    collisionMetricKind: "estimated",
  };
}

export function spatialCoverageGridCells(
  features: readonly HistoricalFeature[],
  anchor: AnchorCoordinate,
  radiusKm: number,
): number {
  const occupied = new Set<string>();
  for (const feature of features) {
    const [xKm, yKm] = localCoordinates(feature, anchor);
    const x = Math.min(
      DISPLAY_CONFIG.spatialGridSize - 1,
      Math.max(
        0,
        Math.floor(
          ((xKm + radiusKm) / (2 * radiusKm)) * DISPLAY_CONFIG.spatialGridSize,
        ),
      ),
    );
    const y = Math.min(
      DISPLAY_CONFIG.spatialGridSize - 1,
      Math.max(
        0,
        Math.floor(
          ((yKm + radiusKm) / (2 * radiusKm)) * DISPLAY_CONFIG.spatialGridSize,
        ),
      ),
    );
    occupied.add(`${x}:${y}`);
  }
  return occupied.size;
}
