import { expect, test } from "vitest";

import type { TemporalSnapshot } from "../types";
import {
  formatHistoricalYear,
  nearestSupportedYear,
  provisionalYearAtDisplayPosition,
  shortcutTargetYear,
  snapDisplayPositionToSupportedYear,
} from "./temporal";


function snapshot(year: number, displayPosition: number, shortcutLabel: string): TemporalSnapshot {
  return {
    snapshot_id: `test:${year}`,
    anchor_id: "test",
    snapshot_year: year,
    display_year: formatHistoricalYear(year),
    broad_era_label: shortcutLabel,
    shortcut_label: shortcutLabel,
    regional_context_label: null,
    context_confidence: "high",
    source_status: "supported",
    source_ids: ["source"],
    notes: "reviewed",
    whether_context_is_manual_reviewed: true,
    whether_context_is_safe_for_user_display: true,
    unresolved_conflicts: [],
    sequence_index: 0,
    sequence_count: 4,
    previous_snapshot_year: null,
    changes_from_previous: { added_records: 0, removed_records: 0, mechanical_only: true },
    timeline: {
      year,
      linear_normalized_position: displayPosition,
      display_normalized_position: displayPosition,
      position_adjusted: false,
      scale_scope: "per_anchor",
      display_algorithm: "linear_with_minimum_gap_0_10",
    },
  };
}

const snapshots = [
  snapshot(14, 0, "汉"),
  snapshot(220, 0.1, "三国"),
  snapshot(1368, 0.7, "明"),
  snapshot(1911, 1, "清"),
];

test("Chinese formatter handles BCE and CE and rejects year zero", () => {
  expect(formatHistoricalYear(-201)).toBe("公元前 201 年");
  expect(formatHistoricalYear(553)).toBe("公元 553 年");
  expect(() => formatHistoricalYear(0)).toThrow("不存在 0 年");
});

test("nearest snapshot uses real-year midpoint with deterministic earlier tie", () => {
  expect(nearestSupportedYear([14, 220], 117)).toBe(14);
  expect(nearestSupportedYear([14, 220], 118)).toBe(220);
});

test("nonlinear display position maps through year semantics before snapping", () => {
  expect(provisionalYearAtDisplayPosition(snapshots, 0.05)).toBe(117);
  expect(snapDisplayPositionToSupportedYear(snapshots, 0.05)).toBe(14);
  expect(snapDisplayPositionToSupportedYear(snapshots, 0.051)).toBe(220);
  expect(snapDisplayPositionToSupportedYear(snapshots, 0.5)).toBe(1368);
});

test("era shortcut only returns an existing supported snapshot", () => {
  expect(shortcutTargetYear(snapshots, "明", 1911)).toBe(1368);
  expect(shortcutTargetYear(snapshots, "唐", 1911)).toBeNull();
});
