import type { HistoricalFeature } from "../types";
import {
  DISPLAY_CONFIG,
  labelRectangle,
  overlaps,
  type AnchorCoordinate,
  type Rectangle,
} from "../display/ranking";


export type LabelRole =
  | "ordinary_modern_reference"
  | "historical_label"
  | "modern_anchor";

export interface PositionedLabel {
  id: string;
  role: LabelRole;
  rectangle: Rectangle;
}

export const LABEL_PRIORITY: Record<LabelRole, number> = {
  ordinary_modern_reference: 1,
  historical_label: 2,
  modern_anchor: 3,
};

export const LABEL_LAYER_ORDER = [
  "ordinary_modern_reference",
  "historical_label",
  "modern_anchor",
] as const satisfies readonly LabelRole[];

export function resolveLabelCollisions(
  candidates: readonly PositionedLabel[],
): Set<string> {
  const visible = new Set<string>();
  const occupied: Rectangle[] = [];
  const ranked = candidates
    .map((candidate, index) => ({ candidate, index }))
    .sort(
      (first, second) =>
        LABEL_PRIORITY[second.candidate.role] -
          LABEL_PRIORITY[first.candidate.role] || first.index - second.index,
    );
  for (const { candidate } of ranked) {
    if (occupied.some((rectangle) => overlaps(rectangle, candidate.rectangle))) {
      continue;
    }
    visible.add(candidate.id);
    occupied.push(candidate.rectangle);
  }
  return visible;
}

function modernAnchorRectangle(anchorLabel: string): Rectangle {
  const centerX = DISPLAY_CONFIG.collisionCanvasWidthPx / 2;
  const centerY = DISPLAY_CONFIG.collisionCanvasHeightPx / 2;
  const labelWidth =
    DISPLAY_CONFIG.collisionLabelPaddingPx +
    Math.min(14, Array.from(anchorLabel).length) *
      DISPLAY_CONFIG.collisionCharacterWidthPx;
  return [
    centerX - 8,
    centerY - 22,
    centerX + 22 + 8 + labelWidth,
    centerY + 22,
  ];
}

export function prioritizeHistoricalLabelsAgainstAnchor(
  points: readonly HistoricalFeature[],
  labelIds: ReadonlySet<string>,
  anchor: AnchorCoordinate,
  radiusKm: number,
  anchorLabel: string,
): { visibleLabelIds: Set<string>; hiddenLabelIds: Set<string> } {
  const candidates: PositionedLabel[] = [
    {
      id: "modern-anchor",
      role: "modern_anchor",
      rectangle: modernAnchorRectangle(anchorLabel),
    },
  ];
  for (let rank = 0; rank < points.length; rank += 1) {
    const feature = points[rank];
    if (!labelIds.has(feature.id)) continue;
    candidates.push({
      id: feature.id,
      role: "historical_label",
      rectangle: labelRectangle(feature, anchor, radiusKm, rank),
    });
  }
  const resolved = resolveLabelCollisions(candidates);
  const visibleLabelIds = new Set(
    [...labelIds].filter((labelId) => resolved.has(labelId)),
  );
  return {
    visibleLabelIds,
    hiddenLabelIds: new Set(
      [...labelIds].filter((labelId) => !visibleLabelIds.has(labelId)),
    ),
  };
}
