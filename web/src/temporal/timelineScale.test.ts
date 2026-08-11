import { describe, expect, test } from "vitest";
import {
  clampTimelineYear,
  ordinalToYear,
  timelinePosition,
  timelineTicks,
  yearToOrdinal,
} from "./timelineScale";

describe("continuous exact-year timeline scale", () => {
  test("round-trips every supported BCE and CE integer while omitting year zero", () => {
    for (const year of [-763, -2, -1, 1, 2, 1912]) {
      expect(ordinalToYear(yearToOrdinal(year))).toBe(year);
    }
    expect(ordinalToYear(-1)).toBe(-1);
    expect(ordinalToYear(0)).toBe(1);
    expect(() => yearToOrdinal(0)).toThrow("non-zero integer");
  });

  test("clamps and positions arbitrary exact years across the real index range", () => {
    const range = { minYear: -763, maxYear: 1912 };
    expect(clampTimelineYear(-900, range)).toBe(-763);
    expect(clampTimelineYear(3000, range)).toBe(1912);
    expect(timelinePosition(-763, range)).toBe(0);
    expect(timelinePosition(1912, range)).toBe(1);
  });

  test("major ticks are deterministic, bounded, and contain no year zero", () => {
    const range = { minYear: -763, maxYear: 1912 };
    const ticks = timelineTicks(range);
    expect(ticks[0]).toBe(-763);
    expect(ticks.at(-1)).toBe(1912);
    expect(ticks).not.toContain(0);
    expect(timelineTicks(range)).toEqual(ticks);
  });
});
