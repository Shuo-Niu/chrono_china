import { mkdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";

import { expect, test, type Page } from "@playwright/test";

const UPDATE_ARTIFACTS = process.env.UPDATE_PHASE1_3_1B_ARTIFACTS === "1";

const snapshots: Record<string, number[]> = {
  beijing: [14, 220, 1368, 1911],
  xian: [23, 557, 627, 1911],
  chengdu: [14, 553, 742, 1911],
  qingdao: [-201, 14, 190, 1911],
  qufu: [14, 556, 596, 1911],
};

async function selectSnapshot(page: Page, anchor: string, year: number) {
  await page.getByLabel("现代地点").selectOption(anchor);
  const node = page.locator(`.temporal-node[data-snapshot-year="${year}"]`);
  await expect(node).toBeVisible();
  await node.click();
  await expect(page.getByTestId("map")).toHaveAttribute("data-snapshot-year", String(year));
  await expect(page.locator(".history-marker").first()).toBeVisible();
}

async function setZoom(page: Page, zoom: number) {
  await page.evaluate((nextZoom) => {
    const qaMap = (window as typeof window & {
      __CHRONOCHINA_QA_MAP__?: { jumpTo(options: { zoom: number }): void };
    }).__CHRONOCHINA_QA_MAP__;
    if (!qaMap) throw new Error("QA map unavailable");
    qaMap.jumpTo({ zoom: nextZoom });
  }, zoom);
  await expect(page.getByTestId("map")).toHaveAttribute(
    "data-map-zoom",
    new RegExp(`^${zoom.toFixed(1)}`),
  );
}

test("Flow A: modern anchor is absent in User Mode and retained in Developer Mode", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator(".history-marker").first()).toBeVisible();
  await expect(page.getByLabel("北京（现代）")).toHaveCount(0);
  await expect(page.getByLabel("现代地点")).toHaveValue("beijing");
  await page.getByRole("button", { name: "开发者模式" }).click();
  await expect(page.getByLabel("北京（现代）")).toBeVisible();
});

test("Flow B: semantic point-label units increase with zoom while Strategy C stays frozen", async ({ page }) => {
  await page.goto("/");
  await selectSnapshot(page, "beijing", 1911);
  const map = page.getByTestId("map");
  const strategyIds = await map.getAttribute("data-strategy-ranked-point-ids");
  const counts: number[] = [];
  for (const zoom of [6.2, 7.4, 9.2]) {
    await setZoom(page, zoom);
    const pointCount = Number(await map.getAttribute("data-historical-point-count"));
    counts.push(pointCount);
    expect(Number(await map.getAttribute("data-historical-label-count"))).toBe(pointCount);
    expect(await map.getAttribute("data-strategy-ranked-point-ids")).toBe(strategyIds);
  }
  expect(counts[0]).toBeLessThanOrEqual(counts[1]);
  expect(counts[1]).toBeLessThanOrEqual(counts[2]);
  expect(counts[0]).toBeLessThan(counts[2]);
});

test("Flow C: Qing polity record remains ranked but is hidden only in User Mode", async ({ page }) => {
  await page.goto("/");
  await selectSnapshot(page, "beijing", 1911);
  const map = page.getByTestId("map");
  await expect(map).toHaveAttribute("data-strategy-ranked-point-ids", /hvd_113648/);
  await expect(page.locator('.history-marker[data-tgaz-id="hvd_113648"]')).toHaveCount(0);
  await page.getByRole("button", { name: "开发者模式" }).click();
  await expect(page.locator('.history-marker[data-tgaz-id="hvd_113648"]')).toBeVisible();
  await expect(page.locator('.history-marker[data-tgaz-id="hvd_113648"]')).toHaveAttribute(
    "data-display-family",
    "polity",
  );
});

test("Flow D: controls stack above markers and remain interactive", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  await selectSnapshot(page, "beijing", 1911);
  const result = await page.evaluate(() => {
    const panel = document.querySelector<HTMLElement>(".period-control")!;
    const marker = document.querySelector<HTMLElement>(".history-marker")!;
    return {
      panelZ: Number(getComputedStyle(panel).zIndex),
      markerZ: Number(getComputedStyle(marker).zIndex),
      panelPointerEvents: getComputedStyle(panel).pointerEvents,
    };
  });
  expect(result.panelZ).toBeGreaterThan(result.markerZ);
  expect(result.panelPointerEvents).not.toBe("none");
  await page.getByRole("button", { name: "← 上一时期" }).click();
  await expect(page.getByTestId("map")).toHaveAttribute("data-snapshot-year", "1368");
});

test("Flow E: Xian 23 keeps distinct source names and IDs", async ({ page }) => {
  await page.goto("/");
  await selectSnapshot(page, "xian", 23);
  const map = page.getByTestId("map");
  await expect(map).toHaveAttribute("data-strategy-ranked-point-ids", /hvd_116125/);
  await expect(map).toHaveAttribute("data-strategy-ranked-point-ids", /hvd_116126/);
  await expect(map).toHaveAttribute("data-strategy-ranked-point-ids", /hvd_116218/);
  await page.getByRole("button", { name: "开发者模式" }).click();
  const names = await page.locator(".history-marker").evaluateAll((nodes) =>
    Object.fromEntries(nodes.map((node) => [
      (node as HTMLElement).dataset.tgazId,
      node.querySelector(".history-marker__label")?.textContent,
    ])),
  );
  expect(names.hvd_116125).toBe("右扶风");
  expect(names.hvd_116126).toBe("右扶风郡");
  expect(names.hvd_116218).toBe("左冯翊");
});

test("capture Phase 1.3.1b evidence and all User Mode label IDs", async ({ page }) => {
  test.setTimeout(120_000);
  test.skip(!UPDATE_ARTIFACTS, "Set UPDATE_PHASE1_3_1B_ARTIFACTS=1 to refresh evidence.");
  const artifactRoot = resolve("../artifacts/phase1_3_1b");
  const userModeDir = resolve(artifactRoot, "user_mode");
  const zoomDir = resolve(artifactRoot, "zoom_labels");
  await mkdir(userModeDir, { recursive: true });
  await mkdir(zoomDir, { recursive: true });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");

  const observations = [];
  for (const [anchor, years] of Object.entries(snapshots)) {
    for (const year of years) {
      await selectSnapshot(page, anchor, year);
      await setZoom(page, 7.4);
      const map = page.getByTestId("map");
      observations.push({
        anchor,
        year,
        activeFeatureCount: Number(await map.getAttribute("data-active-feature-count")),
        strategyRankedPointIds: (await map.getAttribute("data-strategy-ranked-point-ids"))?.split(",").filter(Boolean),
        displayedPointIds: (await map.getAttribute("data-historical-point-ids"))?.split(",").filter(Boolean),
        displayedLabelIds: (await map.getAttribute("data-historical-label-ids"))?.split(",").filter(Boolean),
        families: await page.locator(".history-marker").evaluateAll((nodes) =>
          Object.fromEntries(nodes.map((node) => [
            (node as HTMLElement).dataset.tgazId,
            (node as HTMLElement).dataset.displayFamily,
          ])),
        ),
      });
    }
  }
  await writeFile(
    resolve("../data/qa/phase1_3_1b_browser_observations.json"),
    `${JSON.stringify(observations, null, 2)}\n`,
    "utf8",
  );

  for (const item of [
    { anchor: "beijing", year: 1368, slug: "beijing-1368" },
    { anchor: "beijing", year: 1911, slug: "beijing-1911" },
    { anchor: "xian", year: 23, slug: "xian-23" },
    { anchor: "chengdu", year: 553, slug: "chengdu-553" },
    { anchor: "qingdao", year: -201, slug: "qingdao-bce201" },
  ]) {
    await selectSnapshot(page, item.anchor, item.year);
    await setZoom(page, 7.4);
    await page.screenshot({ path: resolve(userModeDir, `${item.slug}.png`) });
  }

  const zoomMetrics = [];
  for (const item of [
    { anchor: "beijing", year: 1911 },
    { anchor: "chengdu", year: 553 },
  ]) {
    await selectSnapshot(page, item.anchor, item.year);
    for (const zoom of [6.2, 7.4, 9.2]) {
      await setZoom(page, zoom);
      const map = page.getByTestId("map");
      const slug = `${item.anchor}-${item.year}-z${String(zoom).replace(".", "_")}`;
      zoomMetrics.push({
        ...item,
        zoom,
        pointCount: Number(await map.getAttribute("data-historical-point-count")),
        labelCount: Number(await map.getAttribute("data-historical-label-count")),
        familyCounts: await page.locator(".history-marker").evaluateAll((nodes) =>
          nodes.reduce<Record<string, number>>((counts, node) => {
            const family = (node as HTMLElement).dataset.displayFamily ?? "unknown";
            counts[family] = (counts[family] ?? 0) + 1;
            return counts;
          }, {})),
      });
      await page.screenshot({ path: resolve(zoomDir, `${slug}.png`) });
    }
  }
  await writeFile(
    resolve("../data/qa/phase1_3_1b_zoom_label_metrics.json"),
    `${JSON.stringify(zoomMetrics, null, 2)}\n`,
    "utf8",
  );

  const panelOverlap = await page.evaluate(() => {
    const panel = document.querySelector<HTMLElement>(".period-control")!;
    const marker = document.querySelector<HTMLElement>(".history-marker")!;
    return {
      panelZIndex: Number(getComputedStyle(panel).zIndex),
      markerZIndex: Number(getComputedStyle(marker).zIndex),
      panelPointerEvents: getComputedStyle(panel).pointerEvents,
      result: Number(getComputedStyle(panel).zIndex) > Number(getComputedStyle(marker).zIndex)
        ? "PASS"
        : "FAIL",
    };
  });
  await writeFile(
    resolve("../data/qa/phase1_3_1b_panel_overlap_qa.json"),
    `${JSON.stringify(panelOverlap, null, 2)}\n`,
    "utf8",
  );
});
