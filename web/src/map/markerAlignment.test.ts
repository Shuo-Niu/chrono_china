import { expect, test } from "vitest";

import {
  alignmentMetrics,
  isWithinAlignmentTolerance,
  MARKER_ALIGNMENT_TOLERANCE_PX,
} from "./markerAlignment";


test("exact historical point center has zero alignment error", () => {
  expect(alignmentMetrics({ x: 320, y: 240 }, { x: 320, y: 240 })).toEqual({
    dx: 0,
    dy: 0,
    distancePx: 0,
  });
});

test.each([
  [12.25, 18.75],
  [640.5, 360.5],
  [1267.875, 701.125],
])("alignment is position independent at %s,%s", (x, y) => {
  expect(isWithinAlignmentTolerance(alignmentMetrics({ x, y }, { x, y }))).toBe(true);
});

test("alignment is invariant across projected positions from multiple zooms", () => {
  const projectedByZoom = [
    { x: 590.125, y: 410.875 },
    { x: 622.5, y: 355.25 },
    { x: 751.875, y: 132.625 },
  ];
  expect(
    projectedByZoom.every((point) =>
      isWithinAlignmentTolerance(alignmentMetrics(point, point)),
    ),
  ).toBe(true);
});

test("label placement is not an input to point alignment", () => {
  const pointCenter = { x: 400, y: 300 };
  const labels = [
    { x: 421, y: 292 },
    { x: 421, y: 300 },
    { x: 421, y: 308 },
    { x: -1000, y: 2000 },
  ];
  expect(labels.map(() => alignmentMetrics(pointCenter, pointCenter))).toEqual(
    labels.map(() => ({ dx: 0, dy: 0, distancePx: 0 })),
  );
});

test("one CSS pixel is accepted but larger directional drift is rejected", () => {
  expect(
    isWithinAlignmentTolerance(
      { dx: 1, dy: -1, distancePx: Math.SQRT2 },
      MARKER_ALIGNMENT_TOLERANCE_PX,
    ),
  ).toBe(true);
  expect(
    isWithinAlignmentTolerance(
      { dx: 1.01, dy: 0, distancePx: 1.01 },
      MARKER_ALIGNMENT_TOLERANCE_PX,
    ),
  ).toBe(false);
});
