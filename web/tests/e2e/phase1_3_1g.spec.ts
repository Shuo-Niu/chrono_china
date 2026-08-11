import { expect, test, type Page } from "@playwright/test";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

function yearToOrdinal(year: number): number {
  if (year === 0) throw new Error("year zero is unsupported");
  return year < 0 ? year : year - 1;
}

async function waitForIndex(page: Page) {
  const map = page.getByTestId("map");
  await expect(map).toHaveAttribute("data-explore-index-status", "ready", { timeout: 30_000 });
  await expect.poll(async () => Number(await map.getAttribute("data-explore-query-sequence"))).toBeGreaterThan(0);
}

async function setYear(page: Page, year: number) {
  await page.getByTestId("timeline-range").evaluate((element, ordinal) => {
    const input = element as HTMLInputElement;
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, String(ordinal));
    input.dispatchEvent(new Event("input", { bubbles: true }));
  }, yearToOrdinal(year));
  await expect(page.getByTestId("map")).toHaveAttribute("data-query-result-year", String(year));
}

test("display controls are orthogonal and timeline updates retain keyed markers", async ({ page }) => {
  test.setTimeout(180_000);
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(String(error)));
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  await waitForIndex(page);
  const map = page.getByTestId("map");

  const initial = {
    year: await map.getAttribute("data-snapshot-year"),
    ids: await map.getAttribute("data-historical-point-ids"),
    families: await map.getAttribute("data-enabled-display-families"),
    bbox: await map.getAttribute("data-viewport-bbox"),
  };
  const highDensityActiveRecords = Number(await map.getAttribute("data-explore-active-record-count"));
  const highDensityVisiblePoints = Number(await map.getAttribute("data-historical-point-count"));

  const settlementToggle = page.locator('[data-legend-family="settlement"]');
  await settlementToggle.click();
  await expect(settlementToggle).toHaveAttribute("aria-pressed", "false");
  const familiesWithSettlementOff = await map.getAttribute("data-enabled-display-families");
  await page.getByRole("button", { name: "仅点" }).click();
  await expect(map).toHaveAttribute("data-historical-display-mode", "point_only");
  await expect(map).toHaveAttribute("data-historical-label-count", "0");
  await expect(page.locator(".history-marker__label--persistent")).toHaveCount(0);
  expect(await page.locator(".history-marker__label--hover").count()).toBeGreaterThan(0);
  const safeMarkerId = await page.locator(".history-marker").evaluateAll((elements) => {
    const timelineTop = document.querySelector(".continuous-timeline")!.getBoundingClientRect().top;
    return elements.find((element) => {
      const box = element.getBoundingClientRect();
      return box.top > 180 && box.bottom < timelineTop - 30;
    })?.getAttribute("data-display-unit-id") ?? "";
  });
  expect(safeMarkerId).not.toBe("");
  const safeMarker = page.locator(`[data-display-unit-id="${safeMarkerId}"]`);
  await safeMarker.hover();
  await expect(safeMarker.locator(".history-marker__label--hover")).toBeVisible();
  await safeMarker.click();
  await expect(page.locator(".detail-card, .colocated-card")).toBeVisible();
  await page.getByRole("button", { name: /关闭/ }).click();
  expect(await map.getAttribute("data-enabled-display-families")).toBe(familiesWithSettlementOff);

  await page.getByRole("button", { name: "点 + 标签" }).click();
  await expect(map).toHaveAttribute("data-historical-display-mode", "point_label");
  await expect(settlementToggle).toHaveAttribute("aria-pressed", "false");

  const historicalStateBeforeBasemap = {
    year: await map.getAttribute("data-snapshot-year"),
    ids: await map.getAttribute("data-historical-point-ids"),
    families: await map.getAttribute("data-enabled-display-families"),
    bbox: await map.getAttribute("data-viewport-bbox"),
  };
  await page.getByRole("button", { name: "彩色地理" }).click();
  await expect.poll(async () => await map.getAttribute("data-reference-effective-mode"))
    .toMatch(/r4_color_geography|r2_minimal_modern/);
  expect({
    year: await map.getAttribute("data-snapshot-year"),
    ids: await map.getAttribute("data-historical-point-ids"),
    families: await map.getAttribute("data-enabled-display-families"),
    bbox: await map.getAttribute("data-viewport-bbox"),
  }).toEqual(historicalStateBeforeBasemap);

  await settlementToggle.click();
  await setYear(page, 1900);
  await page.locator(".history-marker").evaluateAll((elements) => {
    for (const element of elements) {
      (element as HTMLElement).dataset.instanceProbe = element.getAttribute("data-display-unit-id") ?? "";
    }
  });
  await setYear(page, 1901);
  const retainedProbeCount = await page.locator(".history-marker").evaluateAll((elements) =>
    elements.filter((element) =>
      (element as HTMLElement).dataset.instanceProbe === element.getAttribute("data-display-unit-id"),
    ).length,
  );
  expect(retainedProbeCount).toBeGreaterThan(0);

  await page.evaluate(() => {
    const overlay = document.querySelector(".history-marker-overlay")!;
    (window as unknown as { __chronoEmptyTransitions: number }).__chronoEmptyTransitions = 0;
    const observer = new MutationObserver(() => {
      if (overlay.childElementCount === 0) {
        (window as unknown as { __chronoEmptyTransitions: number }).__chronoEmptyTransitions += 1;
      }
    });
    observer.observe(overlay, { childList: true });
    (window as unknown as { __chronoOverlayObserver: MutationObserver }).__chronoOverlayObserver = observer;
  });

  const dragStartedAt = Date.now();
  await page.getByTestId("timeline-range").evaluate(async (element) => {
    const input = element as HTMLInputElement;
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
    for (let year = 1400; year <= 1911; year += 11) {
      setter.call(input, String(year - 1));
      input.dispatchEvent(new Event("input", { bubbles: true }));
      await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
    }
    setter.call(input, String(1911 - 1));
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await expect(map).toHaveAttribute("data-query-result-year", "1911");
  const rapidDragWallTimeMs = Date.now() - dragStartedAt;
  await setYear(page, -1);
  await setYear(page, 1);
  const emptyTransitions = await page.evaluate(() => {
    const state = window as unknown as {
      __chronoEmptyTransitions: number;
      __chronoOverlayObserver: MutationObserver;
    };
    state.__chronoOverlayObserver.disconnect();
    return state.__chronoEmptyTransitions;
  });

  const metrics = {
    measured_at_utc: new Date().toISOString(),
    tested_browser: "chromium",
    tested_viewport: "1440x900",
    high_density_year: 1911,
    high_density_active_records: highDensityActiveRecords,
    high_density_visible_points: highDensityVisiblePoints,
    rapid_drag_year_span: 511,
    rapid_drag_input_count: 48,
    rapid_drag_wall_time_ms: rapidDragWallTimeMs,
    final_input_to_map_latency_ms: Number(await map.getAttribute("data-timeline-input-to-map-latency-ms")),
    final_viewport_query_latency_ms: Number(await map.getAttribute("data-explore-query-latency-ms")),
    retained_probe_count: retainedProbeCount,
    retained_marker_recreation_count: Number(await map.getAttribute("data-retained-marker-recreation-count")),
    full_layer_clear_count: Number(await map.getAttribute("data-full-historical-layer-clear-count")),
    observed_empty_transition_count: emptyTransitions,
    stale_commit_count: Number(await map.getAttribute("data-stale-commit-count")),
    max_visible_points: Number(await map.getAttribute("data-max-visible-point-count")),
    basemap_effective_mode: await map.getAttribute("data-reference-effective-mode"),
    page_errors: pageErrors,
  };
  expect(metrics.retained_marker_recreation_count).toBe(0);
  expect(metrics.full_layer_clear_count).toBe(0);
  expect(metrics.observed_empty_transition_count).toBe(0);
  expect(metrics.stale_commit_count).toBe(0);
  expect(metrics.final_input_to_map_latency_ms).toBeLessThan(100);
  expect(metrics.page_errors).toEqual([]);

  await mkdir(path.resolve("../artifacts/phase1_3_1g"), { recursive: true });
  await page.screenshot({ path: path.resolve("../artifacts/phase1_3_1g/user_controls.png"), fullPage: true });
  await writeFile(
    path.resolve("../data/qa/phase1_3_1g_interaction_performance.json"),
    `${JSON.stringify(metrics, null, 2)}\n`,
    "utf8",
  );

  expect(initial.year).toBe("1911");
  expect(initial.ids).toBeTruthy();
  expect(initial.families).toContain("settlement");
  expect(initial.bbox).toBeTruthy();
});
