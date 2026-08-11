import { expect, test, type Page } from "@playwright/test";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

const artifactDir = path.resolve("../artifacts/phase1_3_1d");

function yearToOrdinal(year: number): number {
  if (year === 0) throw new Error("year zero is unsupported");
  return year < 0 ? year : year - 1;
}

async function waitForCommittedYear(page: Page, year: number) {
  const map = page.getByTestId("map");
  await expect(map).toHaveAttribute("data-snapshot-year", String(year));
  await expect(map).toHaveAttribute("data-query-result-year", String(year));
  await expect.poll(async () => Number(await map.getAttribute("data-explore-query-sequence"))).toBeGreaterThan(0);
}

async function setExactYear(page: Page, year: number) {
  await page.getByTestId("timeline-range").evaluate((element, ordinal) => {
    const input = element as HTMLInputElement;
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
    setter.call(input, String(ordinal));
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
  }, yearToOrdinal(year));
  await waitForCommittedYear(page, year);
}

async function setMapView(page: Page, center: [number, number], zoom: number) {
  const previousSequence = Number(
    await page.getByTestId("map").getAttribute("data-explore-query-sequence"),
  );
  await page.evaluate(({ center, zoom }) => {
    const qaMap = window.__CHRONOCHINA_QA_MAP__!;
    qaMap.jumpTo({ center, zoom });
    qaMap.fire("moveend");
  }, { center, zoom });
  await expect.poll(
    async () => Number(await page.getByTestId("map").getAttribute("data-explore-query-sequence")),
    { timeout: 5_000 },
  ).toBeGreaterThan(previousSequence);
}

async function waitForIndex(page: Page) {
  const map = page.getByTestId("map");
  await expect(map).toHaveAttribute("data-view-mode", "unified_viewport");
  await expect(map).toHaveAttribute("data-explore-index-status", "ready", { timeout: 30_000 });
  await expect(page.getByTestId("continuous-timeline")).toBeVisible();
  await expect.poll(async () => Number(await map.getAttribute("data-explore-query-sequence"))).toBeGreaterThan(0);
}

async function markerState(page: Page) {
  return page.locator(".history-marker").evaluateAll((markers) => Object.fromEntries(
    markers.map((marker) => {
      const element = marker as HTMLElement;
      return [element.dataset.displayUnitId!, {
        memberIds: element.dataset.memberIds,
        family: element.dataset.displayFamily,
        placement: element.dataset.labelPlacement,
        offset: element.dataset.labelOffset,
      }];
    }),
  ));
}

async function firstMarkerAlignmentError(page: Page): Promise<number> {
  return page.locator(".history-marker").first().evaluate((marker) => {
    const element = marker as HTMLElement;
    const markerRect = element.getBoundingClientRect();
    const mapRect = document.querySelector<HTMLElement>("[data-testid='map']")!.getBoundingClientRect();
    const coordinate: [number, number] = [
      Number(element.dataset.longitude),
      Number(element.dataset.latitude),
    ];
    const projected = window.__CHRONOCHINA_QA_MAP__!.project(coordinate);
    return Math.hypot(
      markerRect.left + markerRect.width / 2 - (mapRect.left + projected.x),
      markerRect.top + markerRect.height / 2 - (mapRect.top + projected.y),
    );
  });
}

test("unified continuous timeline and deterministic map interactions", async ({ page }) => {
  test.setTimeout(180_000);
  await mkdir(artifactDir, { recursive: true });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/");
  await waitForIndex(page);
  const map = page.getByTestId("map");

  await expect(page.getByLabel("代表时期")).toHaveCount(0);
  await expect(page.getByLabel("自由探索时间与范围")).toHaveCount(0);
  await expect(page.locator(".maplibregl-ctrl-scale")).toBeVisible();
  await expect(page.locator("[data-legend-family]")).toHaveCount(5);
  const legendHtml = await page.getByLabel("地图图例").textContent();
  await page.screenshot({ path: path.join(artifactDir, "01-user-mode-continuous-timeline.png"), fullPage: true });

  await setExactYear(page, 553);
  await expect(page.getByTestId("timeline-current-year")).toContainText("公元 553 年");
  await setExactYear(page, 600);
  await expect(page.getByTestId("timeline-current-year")).toContainText("公元 600 年");
  await setExactYear(page, -201);
  await expect(page.getByTestId("timeline-current-year")).toContainText("公元前 201 年");
  await expect(page.getByTestId("continuous-timeline")).not.toContainText("公元 0 年");

  for (const year of [1800, 23, 1900, 742, 1368, 1911]) {
    await page.getByTestId("timeline-range").evaluate((element, ordinal) => {
      const input = element as HTMLInputElement;
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
      setter.call(input, String(ordinal));
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.dispatchEvent(new Event("change", { bubbles: true }));
    }, yearToOrdinal(year));
  }
  await waitForCommittedYear(page, 1911);
  await expect(map).toHaveAttribute("data-snapshot-year", "1911");

  await setMapView(page, [104.5, 35.5], 4.5);
  await waitForCommittedYear(page, 1911);
  await expect(map).toHaveAttribute("data-eligible-display-families", "high_admin");
  const nationwideCount = Number(await map.getAttribute("data-historical-point-count"));
  expect(nationwideCount).toBeGreaterThan(1);
  await page.screenshot({ path: path.join(artifactDir, "02-beijing-1911-nationwide-low-zoom.png"), fullPage: true });

  await setMapView(page, [116.39723, 39.9075], 10.8);
  await waitForCommittedYear(page, 1911);
  await expect(map).toHaveAttribute("data-eligible-display-families", /county/);
  await page.screenshot({ path: path.join(artifactDir, "03-beijing-1911-high-zoom.png"), fullPage: true });

  await setMapView(page, [108.93719, 34.31799], 11.2);
  await setExactYear(page, 23);
  await expect.poll(async () => Number(await map.getAttribute("data-co-located-group-count"))).toBeGreaterThan(0);
  const group = page.locator(".history-marker--colocated").first();
  const year23Members = (await group.getAttribute("data-member-ids")) ?? "";
  for (const memberId of year23Members.split(",").filter(Boolean)) {
    await expect(page.locator(`[data-colocated-member-id="${memberId}"]`)).toHaveCount(0);
  }
  await group.click();
  await expect(page.getByLabel("同址历史记录")).toBeVisible();
  await page.screenshot({ path: path.join(artifactDir, "04-xian-23-colocation.png"), fullPage: true });
  await page.getByLabel("关闭同址记录").click();

  await setMapView(page, [114.3054, 30.5931], 9.3);
  await setExactYear(page, 600);
  await page.screenshot({ path: path.join(artifactDir, "05-non-anchor-wuhan-600.png"), fullPage: true });
  await expect(page.getByLabel("地图图例")).toContainText("郡、府、州、直隶州、路、侯国、厅、军、防镇");
  await page.screenshot({ path: path.join(artifactDir, "06-static-complete-legend.png"), fullPage: true });

  const scaleBefore = await page.locator(".maplibregl-ctrl-scale").textContent();
  await setMapView(page, [114.3054, 30.5931], 11.2);
  const scaleAfter = await page.locator(".maplibregl-ctrl-scale").textContent();
  expect(scaleAfter).not.toBe(scaleBefore);
  await page.screenshot({ path: path.join(artifactDir, "07-metric-scale-bar.png"), fullPage: true });

  const firstMarker = page.locator(".history-marker").first();
  await expect(firstMarker).toBeVisible();
  await firstMarker.click();
  const detailOrGroup = page.locator(".detail-card, .colocated-card").first();
  await expect(detailOrGroup).toBeVisible();
  await expect(page.getByTestId("continuous-timeline")).toBeVisible();
  await page.screenshot({ path: path.join(artifactDir, "08-detail-and-timeline.png"), fullPage: true });
  const close = page.locator(".detail-card__close").first();
  if (await close.isVisible()) await close.click();

  await setMapView(page, [116.39723, 39.9075], 9.3);
  await setExactYear(page, 1911);
  const beforePan = await markerState(page);
  await page.screenshot({ path: path.join(artifactDir, "09-pan-before-label-layout.png"), fullPage: true });
  await setMapView(page, [116.48, 39.96], 9.3);
  await waitForCommittedYear(page, 1911);
  const afterPan = await markerState(page);
  const commonIds = Object.keys(beforePan).filter((id) => id in afterPan);
  expect(commonIds.length).toBeGreaterThan(0);
  for (const id of commonIds) {
    expect(afterPan[id].placement).toBe(beforePan[id].placement);
    expect(afterPan[id].offset).toBe(beforePan[id].offset);
  }
  await page.screenshot({ path: path.join(artifactDir, "10-pan-after-label-layout.png"), fullPage: true });

  const anchorRegression = [];
  for (const anchorId of ["beijing", "xian", "chengdu", "qingdao", "qufu"]) {
    const sequenceBeforeSearch = Number(await map.getAttribute("data-explore-query-sequence"));
    await page.locator("#anchor-select").selectOption(anchorId);
    await expect.poll(
      async () => Number(await map.getAttribute("data-explore-query-sequence")),
    ).toBeGreaterThan(sequenceBeforeSearch);
    await waitForCommittedYear(page, 1911);
    await expect(page.locator(".history-marker").first()).toBeVisible();
    const alignmentErrorPx = await firstMarkerAlignmentError(page);
    expect(alignmentErrorPx).toBeLessThanOrEqual(1);
    anchorRegression.push({
      anchor_id: anchorId,
      display_unit_count: Number(await map.getAttribute("data-historical-point-count")),
      first_marker_alignment_error_px: alignmentErrorPx,
      view_mode: await map.getAttribute("data-view-mode"),
    });
  }
  expect(anchorRegression.every((item) => item.view_mode === "unified_viewport")).toBe(true);

  await writeFile(path.join(artifactDir, "browser_evidence.json"), JSON.stringify({
    phase: "1.3.1d",
    result: "PASS",
    continuous_years_checked: [553, 600, -201, 1800, 23, 1900, 742, 1368, 1911],
    nationwide_low_zoom_display_unit_count: nationwideCount,
    static_legend_text: legendHtml,
    scale_bar_before: scaleBefore,
    scale_bar_after: scaleAfter,
    pan_common_display_unit_count: commonIds.length,
    pan_label_placement_churn_count: 0,
    five_anchor_regression: anchorRegression,
    search_path: "locator-only; unified_viewport retained",
    screenshot_count: 10,
  }, null, 2) + "\n", "utf8");
});
