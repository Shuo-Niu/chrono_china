import { expect, test, type Page } from "@playwright/test";

const realRecords = {
  pavilion14: { id: "hvd_41144", center: [115.94367, 29.64157] as [number, number] },
  pavilion626: { id: "hvd_115201", center: [108.85463, 34.41219] as [number, number] },
  town1820: { id: "hvd_15476", center: [115.04019, 35.09462] as [number, number] },
  town1911: { id: "hvd_122406", center: [107.35506, 22.4202] as [number, number] },
  highAdmin1911: { id: "hvd_30012", center: [119.32158, 26.07395] as [number, number] },
};

const responsiveViewports = [
  { width: 1440, height: 900 },
  { width: 1024, height: 768 },
  { width: 900, height: 1200 },
] as const;

function yearToOrdinal(year: number): number {
  if (year === 0) throw new Error("year zero is unsupported");
  return year < 0 ? year : year - 1;
}

async function waitForIndex(page: Page, coverageStatus: "ready" | "failed" = "ready") {
  const map = page.getByTestId("map");
  await expect(map).toHaveAttribute("data-explore-index-status", "ready", { timeout: 30_000 });
  await expect(map).toHaveAttribute("data-coverage-metadata-status", coverageStatus, { timeout: 30_000 });
  await expect.poll(async () => Number(await map.getAttribute("data-explore-query-sequence")))
    .toBeGreaterThan(0);
}

async function setYear(page: Page, year: number) {
  const map = page.getByTestId("map");
  await page.getByTestId("timeline-range").evaluate((element, ordinal) => {
    const input = element as HTMLInputElement;
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, String(ordinal));
    input.dispatchEvent(new Event("input", { bubbles: true }));
  }, yearToOrdinal(year));
  await expect(map).toHaveAttribute("data-snapshot-year", String(year));
  await expect(map).toHaveAttribute("data-query-result-year", String(year));
}

async function setView(page: Page, center: [number, number], zoom = 11) {
  const map = page.getByTestId("map");
  const previousSequence = Number(await map.getAttribute("data-explore-query-sequence"));
  await page.evaluate(({ center, zoom }) => {
    const instance = window.__CHRONOCHINA_QA_MAP__!;
    instance.jumpTo({ center, zoom });
    instance.fire("moveend");
  }, { center, zoom });
  await expect.poll(async () => Number(await map.getAttribute("data-explore-query-sequence")))
    .toBeGreaterThan(previousSequence);
}

function markerFor(page: Page, id: string) {
  return page.locator(`[data-member-ids="${id}"], [data-member-ids^="${id},"], [data-member-ids$=",${id}"], [data-member-ids*=",${id},"]`);
}

async function settlementState(page: Page) {
  const serialized = await page.getByTestId("map").getAttribute("data-coverage-family-states");
  return (JSON.parse(serialized ?? "{}") as Record<string, {
    support: string;
    temporalModels: string[];
    viewportResult: string;
    viewportCount: number;
  }>).settlement;
}

type Box = { x: number; y: number; right: number; bottom: number };

function intersects(first: Box | null, second: Box | null): boolean {
  if (!first || !second) return false;
  return first.x < second.right && first.right > second.x &&
    first.y < second.bottom && first.bottom > second.y;
}

async function overlayState(page: Page) {
  return page.evaluate(() => {
    const box = (selector: string) => {
      const element = document.querySelector<HTMLElement>(selector);
      if (!element || getComputedStyle(element).display === "none") return null;
      const rect = element.getBoundingClientRect();
      return { x: rect.x, y: rect.y, right: rect.right, bottom: rect.bottom };
    };
    const legend = document.querySelector<HTMLElement>(".legend")!;
    const legendStyle = getComputedStyle(legend);
    const legendBox = legend.getBoundingClientRect();
    const entries = [...legend.querySelectorAll<HTMLElement>("[data-legend-tier]")].map((entry) => {
      const entryBox = entry.getBoundingClientRect();
      const badgeBox = entry.querySelector<HTMLElement>("[data-coverage-family]")?.getBoundingClientRect();
      return {
        family: entry.dataset.legendTier ?? "",
        box: { x: entryBox.x, y: entryBox.y, right: entryBox.right, bottom: entryBox.bottom },
        badge: badgeBox
          ? { x: badgeBox.x, y: badgeBox.y, right: badgeBox.right, bottom: badgeBox.bottom }
          : null,
      };
    });
    return {
      timeline: box(".continuous-timeline"),
      legend: box(".legend"),
      zoom: box(".maplibregl-ctrl-group"),
      scale: box(".maplibregl-ctrl-scale"),
      attribution: box(".provenance-bar"),
      detail: box(".detail-card,.colocated-card"),
      legendLayout: {
        whiteSpace: legendStyle.whiteSpace,
        overflowX: legendStyle.overflowX,
        overflowY: legendStyle.overflowY,
        scrollWidth: legend.scrollWidth,
        clientWidth: legend.clientWidth,
        scrollHeight: legend.scrollHeight,
        clientHeight: legend.clientHeight,
      },
      viewport: { width: innerWidth, height: innerHeight },
      legendBox: { x: legendBox.x, y: legendBox.y, right: legendBox.right, bottom: legendBox.bottom },
      entries,
    };
  });
}

test("settlement facts remain diagnostic-only while User Mode hides their controls and points", async ({ page }) => {
  test.setTimeout(240_000);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  await waitForIndex(page);
  await expect(page.locator('[data-legend-tier="unresolved"]')).toHaveCount(0);
  await expect(page.getByTestId("coverage-settlement")).toHaveCount(0);
  await expect(page.getByTestId("layer-switcher")).not.toContainText("村镇、亭");

  await setView(page, realRecords.town1820.center);
  for (const year of [1819, 1820, 1821]) {
    await setYear(page, year);
    await expect(markerFor(page, realRecords.town1820.id)).toHaveCount(0);
  }
  expect(await settlementState(page)).toMatchObject({
    support: "UNSUPPORTED", viewportResult: "NO_RECORDS", viewportCount: 0,
  });
  await setYear(page, 1820);
  const state1820 = await settlementState(page);
  expect(state1820).toMatchObject({
    support: "SUPPORTED", temporalModels: ["TIME_SLICE"], viewportResult: "HAS_RECORDS",
  });
  expect(state1820.viewportCount).toBeGreaterThan(0);

  await setView(page, realRecords.town1911.center);
  await setYear(page, 1911);
  await expect(markerFor(page, realRecords.town1911.id)).toHaveCount(0);
  const state1911 = await settlementState(page);
  expect(state1911).toMatchObject({
    support: "SUPPORTED", temporalModels: ["TIME_SLICE"], viewportResult: "HAS_RECORDS",
  });
  expect(state1911.viewportCount).toBeGreaterThan(0);

  await setView(page, realRecords.pavilion626.center);
  for (const year of [14, 626, 750]) {
    await setYear(page, year);
    await expect(markerFor(page, year === 14 ? realRecords.pavilion14.id : realRecords.pavilion626.id))
      .toHaveCount(0);
  }

  await page.getByRole("button", { name: "开发者模式" }).click();
  const diagnostics = page.getByTestId("coverage-family-diagnostics");
  await expect(diagnostics).toContainText("raw_town_snapshots · 村镇 · TIME_SLICE");
  await expect(diagnostics).toContainText("raw_pavilion_intervals · 亭 · TIME_SERIES");
});

test("Phase 1.4.1 malformed coverage metadata fails open without an absence claim", async ({ page }) => {
  test.setTimeout(120_000);
  await page.route("**/coverage/historical_layer_coverage.json", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: "{\"schema_version\":\"broken\"}" });
  });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  await waitForIndex(page, "failed");
  await expect(page.locator('[data-legend-tier="unresolved"]')).toHaveCount(0);
  await setView(page, realRecords.highAdmin1911.center);
  await setYear(page, 1911);
  await expect(markerFor(page, realRecords.highAdmin1911.id)).toBeVisible();
  await expect(page.locator("[data-coverage-family]")).toHaveCount(0);
  await expect(page.getByTestId("layer-switcher")).not.toContainText("来源无资料");
});

test("Phase 1.4.1 unit-category controls preserve responsive overlay safe areas", async ({ page }) => {
  test.setTimeout(180_000);
  await page.setViewportSize(responsiveViewports[0]);
  await page.goto("/");
  await waitForIndex(page);
  await expect(page.locator('[data-legend-tier="unclassified"]')).toHaveCount(0);
  await setView(page, realRecords.highAdmin1911.center);
  await setYear(page, 1911);
  await expect(page.locator("[data-coverage-family]")).toHaveCount(0);
  await markerFor(page, realRecords.highAdmin1911.id).click();
  const colocatedCard = page.locator(".colocated-card");
  if (await colocatedCard.isVisible()) {
    await page.locator(`[data-colocated-member-id="${realRecords.highAdmin1911.id}"]`).click();
  }
  await expect(page.locator(".detail-card")).toBeVisible();

  const forbiddenPairs = [
    ["timeline", "legend"], ["timeline", "zoom"], ["timeline", "scale"],
    ["timeline", "attribution"], ["timeline", "detail"],
    ["legend", "zoom"], ["legend", "scale"], ["legend", "attribution"], ["legend", "detail"],
    ["zoom", "scale"], ["zoom", "attribution"], ["zoom", "detail"],
    ["scale", "attribution"], ["scale", "detail"],
    ["attribution", "detail"],
  ] as const;
  for (const viewport of responsiveViewports) {
    await page.setViewportSize(viewport);
    await page.waitForTimeout(120);
    const state = await overlayState(page);
    for (const [name, box] of Object.entries({
      timeline: state.timeline,
      legend: state.legend,
      zoom: state.zoom,
      scale: state.scale,
      attribution: state.attribution,
      detail: state.detail,
    })) {
      expect(box, `${viewport.width}x${viewport.height} ${name} must exist and be visible`).not.toBeNull();
    }
    const collisions = forbiddenPairs.filter(([first, second]) =>
      intersects(state[first], state[second]));
    expect(collisions, `${viewport.width}x${viewport.height} forbidden collision`).toEqual([]);
    expect(state.legendLayout.whiteSpace).toBe("nowrap");
    expect(state.legendLayout.overflowX).not.toMatch(/auto|scroll/);
    expect(state.legendLayout.overflowY).not.toMatch(/auto|scroll/);
    expect(state.legendLayout.scrollWidth).toBeLessThanOrEqual(state.legendLayout.clientWidth + 2);
    expect(state.legendLayout.scrollHeight).toBeLessThanOrEqual(state.legendLayout.clientHeight + 2);
    expect(state.entries).toHaveLength(6);
    const firstCenter = (state.entries[0].box.y + state.entries[0].box.bottom) / 2;
    for (const [index, entry] of state.entries.entries()) {
      expect(entry.box.x, `${viewport.width} ${entry.family} left viewport bound`)
        .toBeGreaterThanOrEqual(0);
      expect(entry.box.right, `${viewport.width} ${entry.family} right viewport bound`)
        .toBeLessThanOrEqual(state.viewport.width);
      expect(entry.box.x, `${viewport.width} ${entry.family} left legend bound`)
        .toBeGreaterThanOrEqual(state.legendBox.x);
      expect(entry.box.right, `${viewport.width} ${entry.family} right legend bound`)
        .toBeLessThanOrEqual(state.legendBox.right);
      expect(
        Math.abs((entry.box.y + entry.box.bottom) / 2 - firstCenter),
        `${viewport.width} ${entry.family} stays on the single legend baseline`,
      ).toBeLessThanOrEqual(1);
      expect(entry.box.bottom - entry.box.y).toBeLessThanOrEqual(34);
      if (entry.badge) {
        expect(entry.badge.x).toBeGreaterThanOrEqual(entry.box.x);
        expect(entry.badge.right).toBeLessThanOrEqual(entry.box.right);
        for (const [otherIndex, other] of state.entries.entries()) {
          if (otherIndex !== index) {
            expect(
              intersects(entry.badge, other.box),
              `${viewport.width} ${entry.family} badge overlaps ${other.family}`,
            ).toBe(false);
          }
        }
      }
    }
    const minimumFontSizes = await page.locator("[data-legend-tier], [data-coverage-family]")
      .evaluateAll((elements) => elements.map((element) => Number.parseFloat(getComputedStyle(element).fontSize)));
    expect(Math.min(...minimumFontSizes), `${viewport.width} legend minimum font size`).toBeGreaterThanOrEqual(9);
  }
});
