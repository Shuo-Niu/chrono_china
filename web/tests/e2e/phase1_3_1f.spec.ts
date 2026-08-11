import { expect, test, type Page } from "@playwright/test";
import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";

type CompactRecord = [string, string, string | null, number, number, number, number, string];

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
    input.dispatchEvent(new Event("change", { bubbles: true }));
  }, yearToOrdinal(year));
  await expect(page.getByTestId("map")).toHaveAttribute("data-query-result-year", String(year));
}

async function setView(page: Page, center: [number, number], zoom = 10.8) {
  const mapElement = page.getByTestId("map");
  const previous = Number(await mapElement.getAttribute("data-explore-query-sequence"));
  await page.evaluate(({ center, zoom }) => {
    const map = window.__CHRONOCHINA_QA_MAP__!;
    map.jumpTo({ center, zoom });
    map.fire("moveend");
  }, { center, zoom });
  await expect.poll(async () => Number(await mapElement.getAttribute("data-explore-query-sequence"))).toBeGreaterThan(previous);
}

async function clickRecord(page: Page, record: CompactRecord) {
  const [id, name, , begin, end, lon, lat] = record;
  await setView(page, [lon, lat]);
  await setYear(page, begin === 0 ? end : begin);
  const markers = page.locator("[data-member-ids]");
  const index = await markers.evaluateAll((elements, targetId) =>
    elements.findIndex((element) => (element.getAttribute("data-member-ids") ?? "").split(",").includes(targetId)), id);
  expect(index, `${id} must enter the display pipeline`).toBeGreaterThanOrEqual(0);
  const marker = markers.nth(index);
  const kind = await marker.getAttribute("data-display-unit-kind");
  await marker.click();
  if (kind === "colocated_group") {
    await page.locator(`[data-colocated-member-id="${id}"]`).click();
  }
  const detail = page.getByLabel("历史地点详情");
  await expect(detail).toBeVisible();
  await expect(detail).toContainText(name);
  await detail.getByRole("button", { name: "关闭详情" }).click();
}

test("real-record detail clicks are contained and rapid timeline input stays frame-driven", async ({ page }) => {
  test.setTimeout(300_000);
  const payload = JSON.parse(await readFile(
    path.resolve("../data/processed/explore/tgaz_compact.json"),
    "utf8",
  )) as { records: CompactRecord[] };
  const targetTypes = ["省", "行省", "县", "侨县", "郡", "府", "州", "军", "军镇", "道", "村镇"];
  const records = targetTypes.map((rawType) => {
    const found = payload.records.find((record) => record[7] === rawType);
    if (!found) throw new Error(`missing real fixture type ${rawType}`);
    return found;
  });
  const xuanhua = payload.records.find((record) => record[0] === "hvd_88266");
  if (!xuanhua) throw new Error("missing real 宣化府 fixture hvd_88266");

  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(String(error)));
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  await waitForIndex(page);

  await clickRecord(page, xuanhua);
  for (const record of records) await clickRecord(page, record);
  expect(pageErrors).toEqual([]);
  await expect(page.getByTestId("continuous-timeline")).toBeVisible();

  await setView(page, [116.39723, 39.9075], 7.4);
  const map = page.getByTestId("map");
  const staleBefore = Number(await map.getAttribute("data-explore-cancelled-query-count"));
  await page.getByTestId("timeline-range").evaluate(async (element) => {
    const input = element as HTMLInputElement;
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
    for (let year = 1882; year <= 1911; year += 1) {
      setter.call(input, String(year - 1));
      input.dispatchEvent(new Event("input", { bubbles: true }));
      await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
    }
  });
  await expect(map).toHaveAttribute("data-query-result-year", "1911");
  const metrics = {
    measured_at_utc: new Date().toISOString(),
    tested_browser: "chromium",
    rapid_drag_input_count: 30,
    final_year: 1911,
    timeline_input_to_map_latency_ms: Number(await map.getAttribute("data-timeline-input-to-map-latency-ms")),
    viewport_query_latency_ms: Number(await map.getAttribute("data-explore-query-latency-ms")),
    rapid_drag_stale_result_count: Number(await map.getAttribute("data-explore-cancelled-query-count")) - staleBefore,
    high_density_viewport_active_records: Number(await map.getAttribute("data-explore-active-record-count")),
    final_rendered_units: Number(await map.getAttribute("data-historical-point-count")),
    page_errors: pageErrors,
  };
  expect(metrics.timeline_input_to_map_latency_ms).toBeLessThan(100);
  expect(metrics.page_errors).toEqual([]);
  await writeFile(
    path.resolve("../data/qa/phase1_3_1f_interaction_performance.json"),
    `${JSON.stringify(metrics, null, 2)}\n`,
    "utf8",
  );
});
