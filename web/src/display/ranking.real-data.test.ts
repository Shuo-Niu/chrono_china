import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { expect, test } from "vitest";

import type { HistoricalFeatureCollection } from "../types";
import { selectDisplay, type DisplayStrategy } from "./ranking";


interface ComparisonCase {
  anchor: string;
  year: number;
  strategy: DisplayStrategy;
  displayed_point_ids: string[];
  displayed_label_ids: string[];
}

interface ExperimentIndex {
  anchors: Record<
    string,
    {
      modern_location: { lon: number; lat: number };
      radius_km: number;
      slices: Record<string, string>;
    }
  >;
}

test("browser ranking matches all 60 Python QA cases on the frozen data", () => {
  const projectRoot = resolve(process.cwd(), "..");
  const comparison = JSON.parse(
    readFileSync(
      resolve(projectRoot, "data/qa/phase1_1_display_strategy_comparison.json"),
      "utf8",
    ),
  ) as { cases: ComparisonCase[] };
  const index = JSON.parse(
    readFileSync(resolve(projectRoot, "data/processed/phase1_1/index.json"), "utf8"),
  ) as ExperimentIndex;
  const slices = new Map<string, HistoricalFeatureCollection>();

  expect(comparison.cases).toHaveLength(60);
  for (const expected of comparison.cases) {
    const anchor = index.anchors[expected.anchor];
    const relativePath = anchor.slices[String(expected.year)];
    let collection = slices.get(relativePath);
    if (!collection) {
      collection = JSON.parse(
        readFileSync(resolve(projectRoot, "data/processed", relativePath), "utf8"),
      ) as HistoricalFeatureCollection;
      slices.set(relativePath, collection);
    }
    const actual = selectDisplay(
      collection.features,
      expected.strategy,
      anchor.modern_location,
      anchor.radius_km,
    );
    expect(
      actual.points.map((feature) => feature.id),
      `${expected.anchor}/${expected.year}/${expected.strategy} points`,
    ).toEqual(expected.displayed_point_ids);
    expect(
      actual.labels.map((feature) => feature.id),
      `${expected.anchor}/${expected.year}/${expected.strategy} labels`,
    ).toEqual(expected.displayed_label_ids);
  }
});
