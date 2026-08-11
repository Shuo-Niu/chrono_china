import type { DisplayUnit } from "./semanticZoom";

export interface DisplayUnitDiff {
  retainedIds: string[];
  enteringIds: string[];
  leavingIds: string[];
  changedGroupCoordinateKeys: string[];
}

function coordinateKey(unit: DisplayUnit): string {
  return `${unit.coordinate[0]}:${unit.coordinate[1]}`;
}

function memberKey(unit: DisplayUnit): string {
  return unit.members.map((member) => member.id).sort().join(",");
}

export function diffDisplayUnits(
  previous: DisplayUnit[],
  next: DisplayUnit[],
): DisplayUnitDiff {
  const previousIds = new Set(previous.map((unit) => unit.id));
  const nextIds = new Set(next.map((unit) => unit.id));
  const previousByCoordinate = new Map(
    previous.map((unit) => [coordinateKey(unit), memberKey(unit)]),
  );
  const nextByCoordinate = new Map(
    next.map((unit) => [coordinateKey(unit), memberKey(unit)]),
  );

  return {
    retainedIds: next.filter((unit) => previousIds.has(unit.id)).map((unit) => unit.id),
    enteringIds: next.filter((unit) => !previousIds.has(unit.id)).map((unit) => unit.id),
    leavingIds: previous.filter((unit) => !nextIds.has(unit.id)).map((unit) => unit.id),
    changedGroupCoordinateKeys: [...nextByCoordinate].flatMap(([key, members]) =>
      previousByCoordinate.has(key) && previousByCoordinate.get(key) !== members
        ? [key]
        : [],
    ),
  };
}
