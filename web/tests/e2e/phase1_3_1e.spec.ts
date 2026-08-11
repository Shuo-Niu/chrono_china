import { expect, test, type Page } from "@playwright/test";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

const artifactDir = path.resolve("../artifacts/phase1_3_1e");
const collisionReport = path.resolve("../data/qa/phase1_3_1e_overlay_collision.json");

const viewports = [
  [2560, 1080], [1920, 1080], [1600, 900], [1440, 900], [1366, 768],
  [1280, 720], [1024, 768], [900, 1200],
] as const;

function yearToOrdinal(year: number): number {
  if (year === 0) throw new Error("year zero is unsupported");
  return year < 0 ? year : year - 1;
}

async function waitForIndex(page: Page) {
  const map = page.getByTestId("map");
  await expect(map).toHaveAttribute("data-explore-index-status", "ready", { timeout: 30_000 });
  await expect.poll(async () => Number(await map.getAttribute("data-explore-query-sequence"))).toBeGreaterThan(0);
}

async function setExactYear(page: Page, year: number) {
  const map = page.getByTestId("map");
  const previousSequence = Number(await map.getAttribute("data-explore-query-sequence"));
  const previousYear = Number(await map.getAttribute("data-snapshot-year"));
  await page.getByTestId("timeline-range").evaluate((element, ordinal) => {
    const input = element as HTMLInputElement;
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
    setter.call(input, String(ordinal));
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
  }, yearToOrdinal(year));
  await expect(map).toHaveAttribute("data-snapshot-year", String(year));
  await expect(map).toHaveAttribute("data-query-result-year", String(year));
  if (previousYear !== year) {
    await expect.poll(async () => Number(await map.getAttribute("data-explore-query-sequence"))).toBeGreaterThan(previousSequence);
  }
}

async function setMapView(page: Page, center: [number, number], zoom: number) {
  const previousSequence = Number(await page.getByTestId("map").getAttribute("data-explore-query-sequence"));
  await page.evaluate(({ center, zoom }) => {
    const map = window.__CHRONOCHINA_QA_MAP__!;
    map.jumpTo({ center, zoom });
    map.fire("moveend");
  }, { center, zoom });
  await expect.poll(async () => Number(await page.getByTestId("map").getAttribute("data-explore-query-sequence"))).toBeGreaterThan(previousSequence);
}

type Box = { x: number; y: number; right: number; bottom: number; width: number; height: number };

function intersects(first: Box | null, second: Box | null): boolean {
  if (!first || !second) return false;
  return first.x < second.right && first.right > second.x && first.y < second.bottom && first.bottom > second.y;
}

async function overlayState(page: Page) {
  return page.evaluate(() => {
    const box = (selector: string) => {
      const element = document.querySelector<HTMLElement>(selector);
      if (!element || getComputedStyle(element).display === "none") return null;
      const rect = element.getBoundingClientRect();
      return { x: rect.x, y: rect.y, right: rect.right, bottom: rect.bottom, width: rect.width, height: rect.height };
    };
    const legend = document.querySelector<HTMLElement>(".legend")!;
    return {
      timeline: box(".continuous-timeline"),
      legend: box(".legend"),
      zoom: box(".maplibregl-ctrl-group"),
      scale: box(".maplibregl-ctrl-scale"),
      attribution: box(".provenance-bar"),
      detail: box(".detail-card,.colocated-card"),
      legend_layout: {
        white_space: getComputedStyle(legend).whiteSpace,
        overflow_x: getComputedStyle(legend).overflowX,
        overflow_y: getComputedStyle(legend).overflowY,
        scroll_width: legend.scrollWidth,
        client_width: legend.clientWidth,
        scroll_height: legend.scrollHeight,
        client_height: legend.clientHeight,
      },
    };
  });
}

test("manual layers, neutral timeline, responsive safe areas, and formal screenshots", async ({ page }) => {
  test.setTimeout(300_000);
  await mkdir(artifactDir, { recursive: true });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  await waitForIndex(page);
  const map = page.getByTestId("map");
  const initialIndexRequestCount = await page.evaluate(() => performance.getEntriesByType("resource")
    .filter((entry) => entry.name.includes("/explore/tgaz_compact.json")).length);

  await expect(page.getByLabel("现代地点")).toHaveCount(0);
  await expect(page.locator("[data-legend-family]")).toHaveCount(5);
  await expect(page.getByTestId("continuous-timeline")).toHaveAttribute("data-progress-fill", "none");
  await expect(page.getByTestId("continuous-timeline")).not.toContainText("精确年份");
  await expect(page.getByTestId("continuous-timeline")).not.toContainText("拖动查看任意整数年份");
  await expect(page.getByTestId("continuous-timeline")).not.toContainText("公元纪年无 0 年");
  await page.screenshot({ path: path.join(artifactDir, "01-default-user-mode-no-selector.png"), fullPage: true });
  await page.screenshot({ path: path.join(artifactDir, "02-single-line-complete-legend-all-on.png"), fullPage: true });

  const familyIds = ["high_admin", "regional_admin", "county", "settlement", "other"];
  for (const family of familyIds) {
    await expect(page.locator(`[data-legend-family="${family}"]`)).toHaveAttribute("aria-pressed", "true");
  }
  const allTypes = "省、行省、省级、王畿郡、侨郡、府、州、直隶州、路、道、侯国、厅、军、军镇、防镇、监县、侨县村镇、亭其他未分类来源类型";
  expect((await page.getByTestId("layer-switcher").textContent())?.replace(/\s+/g, "")).toContain(allTypes);

  const toggleStart = Date.now();
  for (const family of ["regional_admin", "county", "settlement", "other"]) {
    await page.locator(`[data-legend-family="${family}"]`).click();
  }
  const toggleLatencyMs = Date.now() - toggleStart;
  await expect(map).toHaveAttribute("data-enabled-display-families", "high_admin");
  await page.screenshot({ path: path.join(artifactDir, "03-legend-high-admin-only.png"), fullPage: true });

  const enabledBeforeViewChange = await map.getAttribute("data-enabled-display-families");
  await setMapView(page, [116.48, 39.96], 11.1);
  await setExactYear(page, 1800);
  expect(await map.getAttribute("data-enabled-display-families")).toBe(enabledBeforeViewChange);
  for (const family of ["regional_admin", "county", "settlement", "other"]) {
    await page.locator(`[data-legend-family="${family}"]`).click();
  }
  await expect(map).toHaveAttribute("data-enabled-display-families", /settlement/);

  await setExactYear(page, 600);
  await page.screenshot({ path: path.join(artifactDir, "04-timeline-middle-year.png"), fullPage: true });
  await setExactYear(page, -763);
  await page.screenshot({ path: path.join(artifactDir, "05-timeline-earliest-year.png"), fullPage: true });
  await setExactYear(page, 1912);
  await page.screenshot({ path: path.join(artifactDir, "06-timeline-latest-year.png"), fullPage: true });

  for (const year of [-763, 1912, 1, -1]) {
    await setExactYear(page, year);
    const bounds = await page.evaluate(() => {
      const panel = document.querySelector<HTMLElement>(".continuous-timeline")!.getBoundingClientRect();
      const current = document.querySelector<HTMLElement>(".continuous-timeline__current")!.getBoundingClientRect();
      const ticks = [...document.querySelectorAll<HTMLElement>(".continuous-timeline__ticks b")];
      return {
        panel: { left: panel.left, right: panel.right },
        current: { left: current.left, right: current.right },
        first: ticks[0] ? { left: ticks[0].getBoundingClientRect().left, right: ticks[0].getBoundingClientRect().right } : null,
        last: ticks.at(-1) ? { left: ticks.at(-1)!.getBoundingClientRect().left, right: ticks.at(-1)!.getBoundingClientRect().right } : null,
      };
    });
    expect(bounds.current.left).toBeGreaterThanOrEqual(bounds.panel.left);
    expect(bounds.current.right).toBeLessThanOrEqual(bounds.panel.right);
    expect(bounds.first!.left).toBeGreaterThanOrEqual(bounds.panel.left);
    expect(bounds.last!.right).toBeLessThanOrEqual(bounds.panel.right);
  }
  await expect(page.getByTestId("continuous-timeline")).not.toContainText("公元 0 年");

  await setExactYear(page, 1911);
  await setMapView(page, [116.39723, 39.9075], 9.5);
  await expect(page.locator(".history-marker").first()).toBeVisible();
  await page.locator(".history-marker").first().click();
  await expect(page.locator(".detail-card,.colocated-card").first()).toBeVisible();
  await page.screenshot({ path: path.join(artifactDir, "09-detail-timeline-scale-legend.png"), fullPage: true });

  const collisionResults = [];
  const forbiddenPairs = [
    ["timeline", "legend"], ["timeline", "zoom"], ["timeline", "scale"],
    ["timeline", "detail"], ["timeline", "attribution"], ["legend", "zoom"],
    ["legend", "scale"], ["legend", "detail"], ["detail", "zoom"], ["detail", "scale"],
  ] as const;
  for (const [width, height] of viewports) {
    await page.setViewportSize({ width, height });
    await page.waitForTimeout(120);
    const state = await overlayState(page);
    const collisions = forbiddenPairs.filter(([first, second]) => intersects(state[first], state[second]));
    expect(collisions, `${width}x${height} overlay collision`).toEqual([]);
    expect(state.legend_layout.white_space).toBe("nowrap");
    expect(state.legend_layout.overflow_x).not.toMatch(/auto|scroll/);
    expect(state.legend_layout.overflow_y).not.toMatch(/auto|scroll/);
    expect(state.legend_layout.scroll_width).toBeLessThanOrEqual(state.legend_layout.client_width + 2);
    expect(state.legend_layout.scroll_height).toBeLessThanOrEqual(state.legend_layout.client_height + 2);
    collisionResults.push({ viewport: { width, height }, collisions, ...state });
    if (width === 1024) await page.screenshot({ path: path.join(artifactDir, "07-responsive-1024x768.png"), fullPage: true });
    if (width === 900) await page.screenshot({ path: path.join(artifactDir, "08-responsive-900x1200.png"), fullPage: true });
  }

  const close = page.locator(".detail-card__close").first();
  if (await close.isVisible()) await close.click();
  await page.setViewportSize({ width: 1440, height: 900 });
  for (const family of ["regional_admin", "county", "settlement", "other"]) {
    const toggle = page.locator(`[data-legend-family="${family}"]`);
    if (await toggle.getAttribute("aria-pressed") === "true") await toggle.click();
  }
  await setMapView(page, [104.5, 35.5], 4.5);
  await setExactYear(page, 1911);
  await expect(map).toHaveAttribute("data-enabled-display-families", "high_admin");
  await page.screenshot({ path: path.join(artifactDir, "10-nationwide-high-admin-only.png"), fullPage: true });

  for (const family of ["regional_admin", "county", "settlement", "other"]) {
    await page.locator(`[data-legend-family="${family}"]`).click();
  }
  await setMapView(page, [116.39723, 39.9075], 9.5);
  const sparseStart = Date.now();
  await setExactYear(page, 1912);
  const timelineUpdateLatencyMs = Date.now() - sparseStart;
  await page.screenshot({ path: path.join(artifactDir, "11-sparse-year-1912-counters.png"), fullPage: true });
  await setExactYear(page, 1911);
  await page.screenshot({ path: path.join(artifactDir, "12-dense-year-1911-counters.png"), fullPage: true });
  await page.setViewportSize({ width: 2560, height: 1080 });
  await page.screenshot({ path: path.join(artifactDir, "13-wide-layout-2560x1080.png"), fullPage: true });

  const indexRequestCount = await page.evaluate(() => performance.getEntriesByType("resource")
    .filter((entry) => entry.name.includes("/explore/tgaz_compact.json")).length);
  expect(indexRequestCount).toBe(initialIndexRequestCount);
  const legendRenderLatencyMs = await page.evaluate(() => {
    const started = performance.now();
    document.querySelector(".legend")!.getBoundingClientRect();
    return performance.now() - started;
  });
  await writeFile(collisionReport, JSON.stringify({
    phase: "1.3.1e",
    status: "PASS",
    minimum_tested_width: 900,
    forbidden_pairs: forbiddenPairs,
    cases: collisionResults,
  }, null, 2) + "\n", "utf8");
  await writeFile(path.join(artifactDir, "browser_evidence.json"), JSON.stringify({
    phase: "1.3.1e",
    result: "PASS",
    manual_layer_default: "all_user_families_on",
    toggle_latency_ms: toggleLatencyMs,
    timeline_year_update_latency_ms: timelineUpdateLatencyMs,
    viewport_query_latency_ms: Number(await map.getAttribute("data-explore-query-latency-ms")),
    legend_render_latency_ms: legendRenderLatencyMs,
    compact_index_request_count_after_toggles: indexRequestCount,
    compact_index_request_count_before_toggles: initialIndexRequestCount,
    tested_viewports: viewports.map(([width, height]) => ({ width, height })),
    screenshot_count: 13,
  }, null, 2) + "\n", "utf8");
});
