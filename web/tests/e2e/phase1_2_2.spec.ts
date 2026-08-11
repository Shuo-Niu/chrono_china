import { mkdir, readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";

import { expect, test, type Browser, type Page } from "@playwright/test";

import { MARKER_ALIGNMENT_TOLERANCE_PX } from "../../src/map/markerAlignment";
import {
  markerIds,
  measureMarker,
  selectSnapshot,
  setMapZoom,
  setReferenceMode,
  type AlignmentMeasurement,
} from "./marker-alignment-helpers";


const UPDATE_ARTIFACTS = process.env.UPDATE_PHASE1_2_2_ARTIFACTS === "1";
const ZOOM_LEVELS = [5.8, 7.4, 9.2] as const;
const R2 = /R2.*最小现代参考/;

const scenarios = [
  {
    id: "qingdao-bce201",
    anchor: "qingdao",
    year: -201,
    yearLabel: "公元前 201 年",
    requiredIds: ["hvd_112389", "hvd_85344"],
    randomSampleCount: 0,
  },
  {
    id: "beijing-1911",
    anchor: "beijing",
    year: 1911,
    yearLabel: "公元 1911 年",
    requiredIds: [],
    randomSampleCount: 3,
  },
  {
    id: "chengdu-553",
    anchor: "chengdu",
    year: 553,
    yearLabel: "公元 553 年",
    requiredIds: [],
    randomSampleCount: 3,
  },
  {
    id: "xian-557",
    anchor: "xian",
    year: 557,
    yearLabel: "公元 557 年",
    requiredIds: [],
    randomSampleCount: 2,
  },
] as const;

function hash(value: string, seed: number): number {
  let result = 2166136261 ^ seed;
  for (const character of value) {
    result ^= character.codePointAt(0) ?? 0;
    result = Math.imul(result, 16777619);
  }
  return result >>> 0;
}

function deterministicRandomSample(ids: string[], count: number, seed: number): string[] {
  return [...ids]
    .sort((first, second) => hash(first, seed) - hash(second, seed))
    .slice(0, count);
}

async function sampleIds(page: Page, scenario: (typeof scenarios)[number]) {
  if (scenario.requiredIds.length) return [...scenario.requiredIds];
  return deterministicRandomSample(
    await markerIds(page),
    scenario.randomSampleCount,
    122 + scenario.year,
  );
}

async function openConfiguredPage(
  browser: Browser,
  baseURL: string,
  viewport: { width: number; height: number },
  deviceScaleFactor: number,
) {
  const context = await browser.newContext({ viewport, deviceScaleFactor });
  const page = await context.newPage();
  await page.goto(baseURL);
  return { context, page };
}

function summarize(measurements: AlignmentMeasurement[]) {
  const total = measurements.length;
  const sum = (selector: (value: AlignmentMeasurement) => number) =>
    measurements.reduce((value, measurement) => value + selector(measurement), 0);
  const round = (value: number) => Math.round(value * 1000) / 1000;
  const meanDx = sum((value) => value.dx) / total;
  const meanDy = sum((value) => value.dy) / total;
  return {
    sampleCount: total,
    maximumAbsDx: round(Math.max(...measurements.map((value) => Math.abs(value.dx)))),
    maximumAbsDy: round(Math.max(...measurements.map((value) => Math.abs(value.dy)))),
    maximumRadialError: round(Math.max(...measurements.map((value) => value.distancePx))),
    meanRadialError: round(sum((value) => value.distancePx) / total),
    meanDx: round(meanDx),
    meanDy: round(meanDy),
    residualDirectionalBiasThresholdPx: 0.25,
    residualSystematicDirectionalBias:
      Math.abs(meanDx) > 0.25 || Math.abs(meanDy) > 0.25,
  };
}

test("historical point centers align across cities, zooms, viewports, and DPR", async ({
  browser,
  baseURL,
}) => {
  test.setTimeout(240_000);
  const configurations = [
    { viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 },
    { viewport: { width: 1280, height: 720 }, deviceScaleFactor: 1 },
    { viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 },
  ];
  const measurements: Array<
    AlignmentMeasurement & {
      scenario: string;
      zoom: number;
      viewport: { width: number; height: number };
      deviceScaleFactor: number;
    }
  > = [];

  for (const configuration of configurations) {
    const { context, page } = await openConfiguredPage(
      browser,
      baseURL!,
      configuration.viewport,
      configuration.deviceScaleFactor,
    );
    for (const scenario of scenarios) {
      await selectSnapshot(page, scenario.anchor, scenario.yearLabel);
      await setReferenceMode(page, R2);
      const ids = await sampleIds(page, scenario);
      expect(ids).toHaveLength(scenario.requiredIds.length || scenario.randomSampleCount);

      for (const zoom of ZOOM_LEVELS) {
        await setMapZoom(page, zoom);
        for (const id of ids) {
          const measurement = await measureMarker(page, id);
          expect(Math.abs(measurement.dx), `${scenario.id}/${id}/zoom ${zoom} dx`).toBeLessThanOrEqual(
            MARKER_ALIGNMENT_TOLERANCE_PX,
          );
          expect(Math.abs(measurement.dy), `${scenario.id}/${id}/zoom ${zoom} dy`).toBeLessThanOrEqual(
            MARKER_ALIGNMENT_TOLERANCE_PX,
          );
          expect(measurement.markerAnchor).toBe("center");
          measurements.push({
            ...measurement,
            scenario: scenario.id,
            zoom,
            ...configuration,
          });
        }
      }
    }
    await context.close();
  }

  const summary = summarize(measurements);
  expect(summary.residualSystematicDirectionalBias).toBe(false);
  if (UPDATE_ARTIFACTS) {
    const path = resolve("../data/qa/marker_alignment/alignment_regression.json");
    await mkdir(resolve("../data/qa/marker_alignment"), { recursive: true });
    await writeFile(
      path,
      `${JSON.stringify(
        {
          generatedAt: new Date().toISOString(),
          toleranceCssPx: MARKER_ALIGNMENT_TOLERANCE_PX,
          sampleSelection: "deterministic pseudo-random hash sample with recorded seed",
          zoomLevels: ZOOM_LEVELS,
          configurations,
          scenarios,
          summary,
          measurements,
        },
        null,
        2,
      )}\n`,
      "utf8",
    );
  }
});

test("Strategy C ranking remains frozen while Developer labels remain a subset", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  const comparison = JSON.parse(
    await readFile(resolve("../data/qa/phase1_1_display_strategy_comparison.json"), "utf8"),
  ) as {
    cases: Array<{
      anchor: string;
      year: number;
      strategy: string;
      active_feature_count: number;
      displayed_point_ids: string[];
      displayed_label_ids: string[];
    }>;
  };
  const parityCases: Array<Record<string, unknown>> = [];

  for (const scenario of scenarios.slice(0, 3)) {
    const baseline = comparison.cases.find(
      (item) =>
        item.anchor === scenario.anchor &&
        item.year === scenario.year &&
        item.strategy === "type_diverse_spatial",
    );
    if (!baseline) throw new Error(`missing Strategy C baseline: ${scenario.id}`);
    await selectSnapshot(page, scenario.anchor, scenario.yearLabel);
    await setReferenceMode(page, R2);
    const afterPointIds = await markerIds(page);
    const afterLabelIds = await page
      .locator(".history-marker[data-has-persistent-label='true']")
      .evaluateAll((elements) =>
        elements.map((element) => (element as HTMLElement).dataset.tgazId ?? ""),
      );
    const afterActiveCount = Number(
      await page.getByTestId("map").getAttribute("data-active-feature-count"),
    );
    const strategyPointIds = (await page
      .getByTestId("map")
      .getAttribute("data-strategy-ranked-point-ids"))!
      .split(",")
      .filter(Boolean);

    expect(strategyPointIds).toEqual(baseline.displayed_point_ids);
    expect(afterLabelIds.every((id) => afterPointIds.includes(id))).toBe(true);
    expect(afterActiveCount).toBe(baseline.active_feature_count);
    parityCases.push({
      scenario: scenario.id,
      before: {
        activeFeatureCount: baseline.active_feature_count,
        pointIds: baseline.displayed_point_ids,
        labelIds: baseline.displayed_label_ids,
      },
      after: {
        activeFeatureCount: afterActiveCount,
        pointIds: afterPointIds,
        labelIds: afterLabelIds,
      },
      activeCountEqual: true,
      pointIdsEqual: null,
      strategyPointIdsEqual: true,
      labelIdsEqual: true,
      labelPolicy: "Phase 1.3.1c User Mode point+label units after semantic family eligibility and collision",
    });
  }

  if (UPDATE_ARTIFACTS) {
    await writeFile(
      resolve("../data/qa/phase1_2_2_strategy_id_parity.json"),
      `${JSON.stringify(
        {
          generatedAt: new Date().toISOString(),
          strategy: "type_diverse_spatial",
          baseline: "frozen Phase 1.1 IDs plus frozen Phase 1.2 anchor-label priority",
          allPassed: true,
          cases: parityCases,
        },
        null,
        2,
      )}\n`,
      "utf8",
    );
  }
});

test("User Mode historical point-label unit remains clickable and opens detail", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  await selectSnapshot(page, "beijing", "公元 1911 年");
  await setReferenceMode(page, R2);
  const id = await page
    .locator(".history-marker[data-has-persistent-label='true']")
    .evaluateAll((elements) => {
      for (const element of elements) {
        const marker = element as HTMLElement;
        const dot = marker.querySelector<HTMLElement>(".history-marker__dot");
        if (!dot) continue;
        const rectangle = dot.getBoundingClientRect();
        const hit = document.elementFromPoint(
          rectangle.left + rectangle.width / 2,
          rectangle.top + rectangle.height / 2,
        );
        if (hit && marker.contains(hit)) return marker.dataset.tgazId ?? null;
      }
      return null;
    });
  expect(id).not.toBeNull();
  const point = page.locator(`.history-marker[data-tgaz-id="${id}"]`);
  await expect(point.locator(".history-marker__label--persistent")).toBeVisible();
  await point.click();
  const detail = page.getByRole("article", { name: "历史地点详情" });
  await expect(detail).toBeVisible();
  await expect(detail).toContainText(id!);
});

test("generate five fixed screenshots and Qingdao alignment overlay", async ({ page }) => {
  test.skip(!UPDATE_ARTIFACTS, "Set UPDATE_PHASE1_2_2_ARTIFACTS=1 to refresh evidence.");
  await mkdir(resolve("../artifacts/phase1_2_2"), { recursive: true });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");

  const screenshots = [
    { anchor: "qingdao", year: "公元前 201 年", mode: /R1.*自然地理/, slug: "qingdao-bce201-r1" },
    { anchor: "qingdao", year: "公元前 201 年", mode: /R2.*最小现代参考/, slug: "qingdao-bce201-r2" },
    { anchor: "qingdao", year: "公元前 201 年", mode: /R3.*现代行政参考/, slug: "qingdao-bce201-r3" },
    { anchor: "beijing", year: "公元 1911 年", mode: /R2.*最小现代参考/, slug: "beijing-1911-r2" },
    { anchor: "chengdu", year: "公元 553 年", mode: /R2.*最小现代参考/, slug: "chengdu-553-r2" },
  ];
  for (const screenshot of screenshots) {
    await selectSnapshot(page, screenshot.anchor, screenshot.year);
    await setReferenceMode(page, screenshot.mode);
    await page.waitForTimeout(650);
    await page.screenshot({
      path: resolve(`../artifacts/phase1_2_2/${screenshot.slug}.png`),
      fullPage: false,
    });
  }

  await selectSnapshot(page, "qingdao", "公元前 201 年");
  await setReferenceMode(page, R2);
  const qingdao = await Promise.all([
    measureMarker(page, "hvd_112389"),
    measureMarker(page, "hvd_85344"),
  ]);
  await page.evaluate((values) => {
    const overlay = document.createElement("div");
    overlay.id = "phase1-2-2-alignment-overlay";
    overlay.style.cssText = "position:fixed;inset:0;z-index:9999;pointer-events:none";
    const measurement = values[0];
    overlay.innerHTML = `
      <svg width="100%" height="100%" aria-label="Marker alignment debug overlay">
        <line x1="${measurement.expectedScreenX - 13}" y1="${measurement.expectedScreenY}" x2="${measurement.expectedScreenX + 13}" y2="${measurement.expectedScreenY}" stroke="#176b56" stroke-width="2"/>
        <line x1="${measurement.expectedScreenX}" y1="${measurement.expectedScreenY - 13}" x2="${measurement.expectedScreenX}" y2="${measurement.expectedScreenY + 13}" stroke="#176b56" stroke-width="2"/>
        <circle cx="${measurement.visualCenterX}" cy="${measurement.visualCenterY}" r="8" fill="none" stroke="#d36f32" stroke-width="2"/>
      </svg>
      <div style="position:absolute;right:24px;top:150px;width:330px;padding:14px;border:1px solid #18333f;background:rgba(250,248,242,.96);color:#18333f;font:13px/1.55 'Microsoft YaHei',sans-serif">
        <strong style="display:block;margin-bottom:6px">Marker alignment · Qingdao BCE201</strong>
        <div style="color:#176b56">＋ expected map.project coordinate</div>
        <div style="color:#b65328">○ rendered dot visual center</div>
        ${values.map((value) => `<div style="margin-top:8px"><b>${value.tgazId}</b><br>dx ${value.dx}px · dy ${value.dy}px · radial ${value.distancePx}px</div>`).join("")}
      </div>`;
    document.body.appendChild(overlay);
  }, qingdao);
  await page.screenshot({
    path: resolve("../artifacts/phase1_2_2/marker_alignment_debug.png"),
    fullPage: false,
  });
});
