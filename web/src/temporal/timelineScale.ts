export interface TimelineRange {
  minYear: number;
  maxYear: number;
}

export function yearToOrdinal(year: number): number {
  if (!Number.isInteger(year) || year === 0) {
    throw new Error("historical year must be a non-zero integer");
  }
  return year < 0 ? year : year - 1;
}

export function ordinalToYear(ordinal: number): number {
  if (!Number.isInteger(ordinal)) throw new Error("timeline ordinal must be an integer");
  return ordinal < 0 ? ordinal : ordinal + 1;
}

export function clampTimelineYear(year: number, range: TimelineRange): number {
  const nonZeroYear = year === 0 ? 1 : year;
  return ordinalToYear(Math.min(
    yearToOrdinal(range.maxYear),
    Math.max(yearToOrdinal(range.minYear), yearToOrdinal(nonZeroYear)),
  ));
}

export function timelineTicks(range: TimelineRange, desiredCount = 7): number[] {
  const min = yearToOrdinal(range.minYear);
  const max = yearToOrdinal(range.maxYear);
  const span = Math.max(1, max - min);
  const rawStep = span / Math.max(1, desiredCount - 1);
  const magnitude = 10 ** Math.floor(Math.log10(rawStep));
  const normalized = rawStep / magnitude;
  const multiplier = normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10;
  const step = multiplier * magnitude;
  const ticks = [range.minYear];
  for (let ordinal = Math.ceil(min / step) * step; ordinal < max; ordinal += step) {
    const year = ordinalToYear(ordinal);
    if (year !== range.minYear && year !== range.maxYear) ticks.push(year);
  }
  ticks.push(range.maxYear);
  return [...new Set(ticks)];
}

export function timelinePosition(year: number, range: TimelineRange): number {
  const min = yearToOrdinal(range.minYear);
  const max = yearToOrdinal(range.maxYear);
  return (yearToOrdinal(year) - min) / Math.max(1, max - min);
}
