import { mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { resolve } from "node:path";

import { expect, test, type Page } from "@playwright/test";

const UPDATE_ARTIFACTS = process.env.UPDATE_PHASE1_3_1C_TRACK_B === "1";

async function enterExplore(page: Page) {
  await page.getByRole("button", { name: "自由探索" }).click();
  const map = page.getByTestId("map");
  await expect(map).toHaveAttribute("data-view-mode", "explore");
  await expect(map).toHaveAttribute("data-explore-index-status", "ready", { timeout: 20_000 });
  await expect(map).toHaveAttribute("data-explore-index-record-count", "71393");
  await expect.poll(async () => Number(await map.getAttribute("data-explore-query-sequence"))).toBeGreaterThan(0);
  return map;
}

async function setExactYear(page: Page, year: number) {
  const input = page.getByLabel("年份（负数表示公元前）");
  await input.fill(String(year));
  await page.getByRole("button", { name: "应用年份" }).click();
  await expect(page.getByTestId("map")).toHaveAttribute("data-snapshot-year", String(year));
}

async function fitViewport(page: Page, bbox: [number, number, number, number]) {
  const map = page.getByTestId("map");
  const before = Number(await map.getAttribute("data-explore-query-sequence"));
  await page.evaluate((bounds) => {
    const qaMap = (window as typeof window & {
      __CHRONOCHINA_QA_MAP__?: {
        fitBounds(bounds: [[number, number], [number, number]], options: { duration: number }): void;
      };
    }).__CHRONOCHINA_QA_MAP__;
    qaMap?.fitBounds([[bounds[0], bounds[1]], [bounds[2], bounds[3]]], { duration: 0 });
  }, bbox);
  await expect.poll(async () => Number(await map.getAttribute("data-explore-query-sequence"))).toBeGreaterThan(before);
}

test("Track B Flow A: Explore opens a real 71k viewport query at exact year 1911", async ({ page }) => {
  await page.goto("/");
  const map = await enterExplore(page);
  await expect(map).toHaveAttribute("data-snapshot-year", "1911");
  await expect(map).toHaveAttribute("data-explore-coverage-status", "covered_with_active_records");
  expect(Number(await map.getAttribute("data-explore-active-record-count"))).toBeGreaterThan(0);
  expect(Number(await map.getAttribute("data-explore-query-latency-ms"))).toBeLessThan(100);
  await expect(page.locator(".history-marker").first()).toBeVisible();
  await expect(page.getByTestId("temporal-rail")).toHaveCount(0);
});

test("Track B Flow B: panning to Chengdu changes data scope without choosing an anchor", async ({ page }) => {
  await page.goto("/");
  const map = await enterExplore(page);
  const beforeIds = await map.getAttribute("data-historical-point-ids");
  await fitViewport(page, [103.1, 29.9, 105.1, 31.4]);
  await expect(map).toHaveAttribute("data-explore-coverage-status", "covered_with_active_records");
  expect(await map.getAttribute("data-historical-point-ids")).not.toBe(beforeIds);
  await expect(page.getByLabel("现代地点")).toHaveValue("beijing");
});

test("Track B Flow C: BCE exact-year query and locator-only search remain separate", async ({ page }) => {
  await page.goto("/");
  const map = await enterExplore(page);
  await page.getByLabel("现代地点").selectOption("qingdao");
  await expect(map).toHaveAttribute("data-map-center", /120\.3/, { timeout: 5_000 });
  await setExactYear(page, -201);
  await expect(page.getByRole("heading", { name: "公元前 201 年" })).toBeVisible();
  await expect(map).toHaveAttribute("data-explore-coverage-status", "covered_with_active_records");
  expect(Number(await map.getAttribute("data-explore-active-record-count"))).toBeGreaterThan(0);
  await expect(page.getByText("仅用于地图定位，不决定历史数据范围")).toBeVisible();
});

test("Track B Flow D: known gap reports outside_source_scope rather than historical absence", async ({ page }) => {
  await page.goto("/");
  const map = await enterExplore(page);
  await fitViewport(page, [86.8, 43.2, 88.4, 44.4]);
  await expect(map).toHaveAttribute("data-explore-coverage-status", "outside_source_scope");
  await expect(page.getByTestId("explore-coverage-status")).toContainText("已知来源覆盖范围外");
  await expect(page.getByText(/空结果不自动解释为历史上没有地点/)).toBeVisible();
});

test("Track B Flow E: rapid view changes cancel superseded work and commit the last viewport", async ({ page }) => {
  await page.goto("/");
  const map = await enterExplore(page);
  const beforeSequence = Number(await map.getAttribute("data-explore-query-sequence"));
  const beforeCancelled = Number(await map.getAttribute("data-explore-cancelled-query-count"));
  await page.evaluate(async () => {
    const qaMap = (window as typeof window & {
      __CHRONOCHINA_QA_MAP__?: { jumpTo(options: { center: [number, number]; zoom: number }): void };
    }).__CHRONOCHINA_QA_MAP__!;
    qaMap.jumpTo({ center: [114.31, 30.59], zoom: 7.4 });
    await new Promise((resolveDelay) => setTimeout(resolveDelay, 70));
    qaMap.jumpTo({ center: [118.80, 32.06], zoom: 7.4 });
    await new Promise((resolveDelay) => setTimeout(resolveDelay, 70));
    qaMap.jumpTo({ center: [121.47, 31.23], zoom: 7.4 });
  });
  await expect.poll(async () => Number(await map.getAttribute("data-explore-query-sequence"))).toBeGreaterThan(beforeSequence);
  await expect(map).toHaveAttribute("data-map-center", /121\.470000,31\.230000/);
  expect(Number(await map.getAttribute("data-explore-cancelled-query-count"))).toBeGreaterThan(beforeCancelled);
});

test("Track B Flow F: Focus remains available and one R2 tile failure does not break Explore", async ({ page }) => {
  let aborted = false;
  await page.route("**/tiles.openfreemap.org/**", async (route) => {
    if (!aborted && route.request().url().endsWith(".pbf")) {
      aborted = true;
      await route.abort("failed");
      return;
    }
    await route.continue();
  });
  await page.goto("/");
  await expect(page.locator(".history-marker").first()).toBeVisible();
  await page.getByRole("button", { name: "自由探索" }).click();
  const map = page.getByTestId("map");
  await expect(map).toHaveAttribute("data-explore-index-status", "ready", { timeout: 20_000 });
  await expect(page.locator(".history-marker").first()).toBeVisible();
  await page.getByRole("button", { name: "五点聚焦" }).click();
  await expect(map).toHaveAttribute("data-view-mode", "focus");
  await expect(page.getByTestId("temporal-rail")).toBeVisible();
  await expect(page.locator(".history-marker").first()).toBeVisible();
});

test("capture Track B 20+ viewport measurements and seven screenshots", async ({ page }) => {
  test.setTimeout(240_000);
  test.skip(!UPDATE_ARTIFACTS, "Set UPDATE_PHASE1_3_1C_TRACK_B=1 to refresh evidence.");
  const artifactRoot = resolve("../artifacts/phase1_3_1c/track_b");
  await rm(artifactRoot, { recursive: true, force: true });
  await mkdir(artifactRoot, { recursive: true });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  const map = await enterExplore(page);
  await page.screenshot({ path: resolve(artifactRoot, "initial-no-anchor-1911.png") });
  const manifest = JSON.parse(await readFile(resolve("../data/processed/explore/query_cases_manifest.json"), "utf8"));
  const observations = [];
  for (const item of manifest.cases) {
    await setExactYear(page, item.year);
    await fitViewport(page, item.bbox);
    observations.push({
      ...item,
      actualBbox: (await map.getAttribute("data-viewport-bbox"))?.split(",").map(Number),
      coverageStatus: await map.getAttribute("data-explore-coverage-status"),
      activeRecordCount: Number(await map.getAttribute("data-explore-active-record-count")),
      spatialRecordCount: Number(await map.getAttribute("data-explore-spatial-record-count")),
      visibleUnitCount: Number(await map.getAttribute("data-historical-point-count")),
      coLocatedGroupCount: Number(await map.getAttribute("data-co-located-group-count")),
      zoom: Number(await map.getAttribute("data-map-zoom")),
      queryLatencyMs: Number(await map.getAttribute("data-explore-query-latency-ms")),
      querySequence: Number(await map.getAttribute("data-explore-query-sequence")),
    });
  }
  const browserMemoryAfterCases = await page.evaluate(() => {
    const memory = (performance as Performance & {
      memory?: { jsHeapSizeLimit: number; totalJSHeapSize: number; usedJSHeapSize: number };
    }).memory;
    return memory ? {
      available: true,
      jsHeapSizeLimit: memory.jsHeapSizeLimit,
      totalJSHeapSize: memory.totalJSHeapSize,
      usedJSHeapSize: memory.usedJSHeapSize,
    } : { available: false };
  });
  await writeFile(
    resolve("../data/qa/phase1_3_1c_viewport_query_cases.json"),
    `${JSON.stringify({
      generatedAt: new Date().toISOString(),
      indexRecordCount: Number(await map.getAttribute("data-explore-index-record-count")),
      indexLoadMs: Number(await map.getAttribute("data-explore-index-load-ms")),
      targetPostLoadQueryMs: 100,
      allPostLoadQueriesBelowTarget: observations.every((item) => item.queryLatencyMs < 100),
      browserMemoryAfterCases,
      caseCount: observations.length,
      cases: observations,
    }, null, 2)}\n`,
    "utf8",
  );

  await setExactYear(page, 1911);
  await fitViewport(page, [120.47, 30.48, 122.47, 31.98]);
  await page.screenshot({ path: resolve(artifactRoot, "free-pan-shanghai-1911.png") });

  await page.getByLabel("现代地点").selectOption("chengdu");
  await expect(map).toHaveAttribute("data-map-center", /104\.066/, { timeout: 5_000 });
  await page.screenshot({ path: resolve(artifactRoot, "search-chengdu-fly-to.png") });

  const jumpTo = async (center: [number, number], zoom: number) => {
    const before = Number(await map.getAttribute("data-explore-query-sequence"));
    await page.evaluate(({ center: nextCenter, zoom: nextZoom }) => {
      (window as typeof window & {
        __CHRONOCHINA_QA_MAP__?: { jumpTo(options: { center: [number, number]; zoom: number }): void };
      }).__CHRONOCHINA_QA_MAP__?.jumpTo({ center: nextCenter, zoom: nextZoom });
    }, { center, zoom });
    await expect.poll(async () => Number(await map.getAttribute("data-explore-query-sequence"))).toBeGreaterThan(before);
  };
  await page.getByLabel("现代地点").selectOption("beijing");
  await expect(map).toHaveAttribute("data-map-center", /116\.397/, { timeout: 5_000 });
  await jumpTo([116.4, 39.9], 6.5);
  await page.screenshot({ path: resolve(artifactRoot, "beijing-low-zoom.png") });
  await jumpTo([116.4, 39.9], 10.8);
  await page.screenshot({ path: resolve(artifactRoot, "beijing-high-zoom.png") });

  await setExactYear(page, 23);
  await jumpTo([109.06952, 34.36034], 11);
  const group = page.locator('.history-marker[data-display-unit-kind="colocated_group"]')
    .filter({ hasText: "京兆郡" });
  await expect(group).toHaveCount(1);
  await group.click();
  await expect(page.getByRole("article", { name: "同址历史记录" })).toBeVisible();
  await page.screenshot({ path: resolve(artifactRoot, "xian-23-colocation-open.png") });

  await page.route("**/tiles.openfreemap.org/**", (route) => route.abort("failed"));
  await page.goto("/");
  const failedReferenceMap = await enterExplore(page);
  await expect(failedReferenceMap).toHaveAttribute("data-reference-source-status", "failed", { timeout: 20_000 });
  await expect(page.locator(".history-marker").first()).toBeVisible();
  await page.screenshot({ path: resolve(artifactRoot, "reference-failure-viewport.png") });
});
