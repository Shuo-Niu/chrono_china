import { mkdir, readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";

import { expect, test, type Page } from "@playwright/test";

import { measureMarker } from "./marker-alignment-helpers";


const CAPTURE_BEFORE = process.env.CAPTURE_PHASE1_3_1A_BEFORE === "1";
const CAPTURE_AFTER = process.env.CAPTURE_PHASE1_3_1A_AFTER === "1";

async function selectSnapshot(page: Page, anchorId: string, year: number) {
  await page.getByLabel("现代地点").selectOption(anchorId);
  const node = page.locator(`.temporal-node[data-snapshot-year="${year}"]`);
  await expect(node).toBeVisible();
  await node.click();
  await expect(page.getByTestId("map")).toHaveAttribute("data-snapshot-year", String(year));
  await expect(page.locator(".history-marker").first()).toBeVisible();
}

async function historicalPointIds(page: Page) {
  return page.locator(".history-marker").evaluateAll((nodes) =>
    nodes.map((node) => (node as HTMLElement).dataset.tgazId),
  );
}

async function strategyPointIds(page: Page) {
  return (await page.getByTestId("map").getAttribute("data-strategy-ranked-point-ids"))
    ?.split(",")
    .filter(Boolean) ?? [];
}

async function expectedBeforeIds(anchor: string) {
  const observations = JSON.parse(
    await readFile(resolve("../data/qa/phase1_3_1a_before_observations.json"), "utf8"),
  ) as Array<{ anchor: string; historicalPointIds: string[] }>;
  return observations.find((item) => item.anchor === anchor)?.historicalPointIds ?? [];
}

async function waitForReferenceResult(page: Page) {
  const map = page.getByTestId("map");
  await expect(map).toHaveAttribute("data-reference-source-status", /^(ready|degraded)$/, {
    timeout: 20_000,
  });
  await expect(map).toHaveAttribute("data-reference-effective-mode", "r2_minimal_modern");
}

async function renderedReferenceCounts(page: Page, layerIds: string[]) {
  return page.evaluate((ids) => {
    const qaMap = (window as typeof window & {
      __CHRONOCHINA_QA_MAP__?: {
        queryRenderedFeatures(options: { layers: string[] }): unknown[];
      };
    }).__CHRONOCHINA_QA_MAP__;
    if (!qaMap) throw new Error("QA map unavailable");
    return Object.fromEntries(
      ids.map((layerId) => [
        layerId,
        qaMap.queryRenderedFeatures({ layers: [layerId] }).length,
      ]),
    );
  }, layerIds);
}

test("capture the three pre-fix R2 scenarios and loading-state reproduction", async ({ page }) => {
  test.skip(!CAPTURE_BEFORE, "Set CAPTURE_PHASE1_3_1A_BEFORE=1 before changing R2.");
  const artifactDir = resolve("../artifacts/phase1_3_1a");
  await mkdir(artifactDir, { recursive: true });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");

  const cases = [
    { anchor: "beijing", year: 1368, slug: "beijing-1368-before" },
    { anchor: "chengdu", year: 553, slug: "chengdu-553-before" },
    { anchor: "qingdao", year: -201, slug: "qingdao-bce201-before" },
  ];
  const observations = [];
  for (const item of cases) {
    await selectSnapshot(page, item.anchor, item.year);
    const map = page.getByTestId("map");
    await expect(map).toHaveAttribute("data-app-mode", "user");
    await expect(map).toHaveAttribute("data-display-strategy", "type_diverse_spatial");
    await expect(map).toHaveAttribute("data-reference-mode", "r2_minimal_modern");
    await page.waitForTimeout(6_000);
    observations.push({
      ...item,
      center: await map.getAttribute("data-map-center"),
      zoom: await map.getAttribute("data-map-zoom"),
      referenceStatus: await map.getAttribute("data-reference-source-status"),
      historicalPointIds: await page.locator(".history-marker").evaluateAll((nodes) =>
        nodes.map((node) => (node as HTMLElement).dataset.tgazId),
      ),
    });
    await page.screenshot({
      path: resolve(artifactDir, `${item.slug}.png`),
      fullPage: false,
    });
  }
  await writeFile(
    resolve("../data/qa/phase1_3_1a_before_observations.json"),
    `${JSON.stringify(observations, null, 2)}\n`,
    "utf8",
  );
});

test("record the pre-fix unbounded loading behavior", async ({ page }) => {
  test.skip(!CAPTURE_BEFORE, "Set CAPTURE_PHASE1_3_1A_BEFORE=1 before changing R2.");
  await page.route("**/tiles.openfreemap.org/**", async (route) => {
    await new Promise((resolveDelay) => setTimeout(resolveDelay, 15_000));
    await route.abort();
  });
  await page.goto("/");
  const map = page.getByTestId("map");
  await expect(page.locator(".history-marker").first()).toBeVisible();
  await page.waitForTimeout(10_000);
  const observation = {
    waitedMs: 10_000,
    referenceStatus: await map.getAttribute("data-reference-source-status"),
    historicalPointCount: await page.locator(".history-marker").count(),
    modernAnchorVisible: await page.getByLabel("北京（现代）").isVisible(),
  };
  await writeFile(
    resolve("../data/qa/phase1_3_1a_loading_reproduction.json"),
    `${JSON.stringify(observation, null, 2)}\n`,
    "utf8",
  );
  expect(observation.referenceStatus).toBe("loading");
});

test("Flow A: Beijing R2 reaches real inland reference readiness with unchanged history", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  await selectSnapshot(page, "beijing", 1368);
  await waitForReferenceResult(page);
  const counts = await renderedReferenceCounts(page, [
    "reference-major-road",
    "reference-settlement-label",
  ]);
  expect(counts["reference-major-road"]).toBeGreaterThan(0);
  expect(counts["reference-settlement-label"]).toBeGreaterThan(0);
  expect(await strategyPointIds(page)).toEqual(await expectedBeforeIds("beijing"));
});

test("Flow B: Chengdu 553 has inland reference with unchanged history", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  await selectSnapshot(page, "chengdu", 553);
  await waitForReferenceResult(page);
  const counts = await renderedReferenceCounts(page, [
    "reference-major-road",
    "reference-settlement-label",
  ]);
  expect(counts["reference-major-road"]).toBeGreaterThan(0);
  expect(counts["reference-settlement-label"]).toBeGreaterThan(0);
  expect(await strategyPointIds(page)).toEqual(await expectedBeforeIds("chengdu"));
});

test("Flow C: Qingdao BCE201 keeps coastline and marker alignment", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  await selectSnapshot(page, "qingdao", -201);
  await waitForReferenceResult(page);
  const counts = await renderedReferenceCounts(page, [
    "reference-water",
    "reference-settlement-label",
  ]);
  expect(counts["reference-water"]).toBeGreaterThan(0);
  expect(counts["reference-settlement-label"]).toBeGreaterThan(0);
  const ids = await historicalPointIds(page);
  expect(ids.length).toBeGreaterThan(0);
  expect(await strategyPointIds(page)).toEqual(await expectedBeforeIds("qingdao"));
  expect((await measureMarker(page, ids[0]!)).distancePx).toBeLessThanOrEqual(0.75);
});

test("Flow D: forced modern-reference failure falls back without breaking history", async ({ page }) => {
  const pageErrors: Error[] = [];
  page.on("pageerror", (error) => pageErrors.push(error));
  await page.route("**/tiles.openfreemap.org/**", (route) => route.abort("failed"));
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  const map = page.getByTestId("map");
  await expect(page.locator(".history-marker").first()).toBeVisible();
  await expect(page.getByLabel("北京（现代）")).toHaveCount(0);
  await expect(map).toHaveAttribute("data-reference-source-status", "failed", {
    timeout: 20_000,
  });
  await expect(map).toHaveAttribute("data-reference-effective-mode", "r0_grid");
  await expect(map).toHaveAttribute("data-reference-fallback-active", "true");
  await expect(page.getByTestId("reference-status-message")).toHaveText(
    "现代地图参考加载失败，历史地点仍可正常浏览。",
  );
  await expect(page.getByTestId("temporal-rail")).toBeVisible();

  await page.locator('.history-marker[data-display-unit-kind="feature"]').first().click();
  await expect(page.getByRole("article", { name: "历史地点详情" })).toBeVisible();
  await page.locator('.temporal-node[data-snapshot-year="1368"]').click();
  await expect(map).toHaveAttribute("data-snapshot-year", "1368");
  await page.getByLabel("现代地点").selectOption("chengdu");
  await expect(page.getByLabel("成都（现代）")).toHaveCount(0);
  await expect(page.locator(".history-marker").first()).toBeVisible();
  await expect(map).toHaveAttribute("data-reference-source-status", "failed");
  expect(pageErrors).toEqual([]);
});

test("Flow E: one vector-tile error does not discard otherwise usable R2", async ({ page }) => {
  let abortedVectorTile = false;
  await page.route("**/tiles.openfreemap.org/**", async (route) => {
    const url = route.request().url();
    if (!abortedVectorTile && url.endsWith(".pbf") && !url.includes("/fonts/")) {
      abortedVectorTile = true;
      await route.abort("failed");
      return;
    }
    await route.continue();
  });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  const map = page.getByTestId("map");
  await expect(page.locator(".history-marker").first()).toBeVisible();
  await expect.poll(() => abortedVectorTile, { timeout: 10_000 }).toBe(true);
  await expect(map).toHaveAttribute("data-reference-source-status", /^(ready|degraded)$/, {
    timeout: 20_000,
  });
  await expect(map).toHaveAttribute("data-reference-effective-mode", "r2_minimal_modern");
  await expect(map).toHaveAttribute("data-reference-fallback-active", "false");
  await expect(map).not.toHaveAttribute("data-reference-last-error", "");
  await expect(page.getByTestId("reference-status-message")).toHaveCount(0);
});

test("capture three post-fix scenarios and the forced-failure fallback", async ({ page }) => {
  test.skip(!CAPTURE_AFTER, "Set CAPTURE_PHASE1_3_1A_AFTER=1 to refresh evidence.");
  const artifactDir = resolve("../artifacts/phase1_3_1a");
  await mkdir(artifactDir, { recursive: true });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  for (const item of [
    { anchor: "beijing", year: 1368, slug: "beijing-1368-after" },
    { anchor: "chengdu", year: 553, slug: "chengdu-553-after" },
    { anchor: "qingdao", year: -201, slug: "qingdao-bce201-after" },
  ]) {
    await selectSnapshot(page, item.anchor, item.year);
    await waitForReferenceResult(page);
    await page.screenshot({
      path: resolve(artifactDir, `${item.slug}.png`),
      fullPage: false,
    });
  }

  const context = page.context();
  await page.close();
  const failurePage = await context.newPage();
  await failurePage.route("**/tiles.openfreemap.org/**", (route) => route.abort("failed"));
  await failurePage.setViewportSize({ width: 1440, height: 900 });
  await failurePage.goto("/");
  await expect(failurePage.getByTestId("map")).toHaveAttribute(
    "data-reference-source-status",
    "failed",
    { timeout: 20_000 },
  );
  await expect(failurePage.locator(".history-marker").first()).toBeVisible();
  await failurePage.screenshot({
    path: resolve(artifactDir, "reference_failure_fallback.png"),
    fullPage: false,
  });
});
