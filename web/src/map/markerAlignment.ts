export const MARKER_ALIGNMENT_TOLERANCE_PX = 1;

export type ScreenPoint = {
  x: number;
  y: number;
};

export type AlignmentMetrics = {
  dx: number;
  dy: number;
  distancePx: number;
};

export function alignmentMetrics(
  expected: ScreenPoint,
  actualPointCenter: ScreenPoint,
): AlignmentMetrics {
  const dx = actualPointCenter.x - expected.x;
  const dy = actualPointCenter.y - expected.y;
  return { dx, dy, distancePx: Math.hypot(dx, dy) };
}

export function isWithinAlignmentTolerance(
  metrics: AlignmentMetrics,
  tolerancePx = MARKER_ALIGNMENT_TOLERANCE_PX,
): boolean {
  return Math.abs(metrics.dx) <= tolerancePx && Math.abs(metrics.dy) <= tolerancePx;
}
