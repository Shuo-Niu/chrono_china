import type { TemporalSnapshot } from "../types";


export const ERA_SHORTCUTS = ["汉", "三国", "南北朝", "隋", "唐", "明", "清"] as const;

export function formatHistoricalYear(year: number): string {
  if (year === 0) throw new Error("公元纪年不存在 0 年");
  return year < 0 ? `公元前 ${Math.abs(year)} 年` : `公元 ${year} 年`;
}

export function nearestSupportedYear(years: number[], provisionalYear: number): number {
  if (years.length === 0) throw new Error("supported snapshot list is empty");
  return [...years].sort(
    (left, right) =>
      Math.abs(left - provisionalYear) - Math.abs(right - provisionalYear) || left - right,
  )[0];
}

export function provisionalYearAtDisplayPosition(
  snapshots: TemporalSnapshot[],
  normalizedDisplayPosition: number,
): number {
  if (snapshots.length === 0) throw new Error("temporal context has no snapshots");
  const position = Math.min(1, Math.max(0, normalizedDisplayPosition));
  const sorted = [...snapshots].sort(
    (left, right) =>
      left.timeline.display_normalized_position - right.timeline.display_normalized_position,
  );
  if (position <= sorted[0].timeline.display_normalized_position) {
    return sorted[0].snapshot_year;
  }
  for (let index = 1; index < sorted.length; index += 1) {
    const right = sorted[index];
    const left = sorted[index - 1];
    if (position > right.timeline.display_normalized_position) continue;
    const displaySpan =
      right.timeline.display_normalized_position - left.timeline.display_normalized_position;
    const fraction =
      displaySpan === 0
        ? 0
        : (position - left.timeline.display_normalized_position) / displaySpan;
    return left.snapshot_year + fraction * (right.snapshot_year - left.snapshot_year);
  }
  return sorted.at(-1)!.snapshot_year;
}

export function snapDisplayPositionToSupportedYear(
  snapshots: TemporalSnapshot[],
  normalizedDisplayPosition: number,
): number {
  const provisionalYear = provisionalYearAtDisplayPosition(
    snapshots,
    normalizedDisplayPosition,
  );
  return nearestSupportedYear(
    snapshots.map((snapshot) => snapshot.snapshot_year),
    provisionalYear,
  );
}

export function shortcutTargetYear(
  snapshots: TemporalSnapshot[],
  shortcutLabel: string,
  currentYear: number,
): number | null {
  const years = snapshots
    .filter((snapshot) => snapshot.shortcut_label === shortcutLabel)
    .map((snapshot) => snapshot.snapshot_year);
  return years.length === 0 ? null : nearestSupportedYear(years, currentYear);
}
