import { mkdir, readFile } from "node:fs/promises";
import { resolve } from "node:path";

import { expect, test, type Page } from "@playwright/test";


const UPDATE_ARTIFACTS = process.env.UPDATE_PHASE1_3_ARTIFACTS === "1";

async function selectUserSnapshot(page: Page, anchorId: string, year: number) {
  await page.getByLabel("现代地点").selectOption(anchorId);
  const node = page.locator(`.temporal-node[data-snapshot-year="${year}"]`);
  await expect(node).toBeVisible();
  await node.click();
  await expect(page.getByTestId("map")).toHaveAttribute("data-snapshot-year", String(year));
  await expect(node).toHaveAttribute("aria-current", "date");
  await expect(page.locator(".history-marker").first()).toBeVisible();
}

async function markerIds(page: Page): Promise<string[]> {
  return page.locator(".history-marker").evaluateAll((elements) =>
    elements.map((element) => (element as HTMLElement).dataset.tgazId ?? ""),
  );
}

test("Beijing rail enters the real 1368 snapshot with audited context and frozen IDs", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  const map = page.getByTestId("map");
  await expect(map).toHaveAttribute("data-app-mode", "user");
  await expect(map).toHaveAttribute("data-display-strategy", "type_diverse_spatial");
  await expect(map).toHaveAttribute("data-reference-mode", "r2_minimal_modern");
  await expect(page.getByTestId("developer-controls")).toHaveCount(0);

  await selectUserSnapshot(page, "beijing", 1368);
  await expect(page.getByRole("heading", { name: "公元 1368 年" })).toBeVisible();
  await expect(page.getByTestId("temporal-context")).toContainText("明代");
  await expect(page.getByText("第 3 / 4 个代表状态")).toHaveCount(0);
  await expect(page.getByRole("group", { name: "时期捷径" })).toHaveCount(0);
  await expect(page.getByTestId("snapshot-change-summary")).toContainText(
    "新增 7 条记录，移除 8 条记录",
  );

  const comparison = JSON.parse(
    await readFile(resolve("../data/qa/phase1_1_display_strategy_comparison.json"), "utf8"),
  ) as {
    cases: Array<{
      anchor: string;
      year: number;
      strategy: string;
      displayed_point_ids: string[];
    }>;
  };
  const baseline = comparison.cases.find(
    (item) =>
      item.anchor === "beijing" &&
      item.year === 1368 &&
      item.strategy === "type_diverse_spatial",
  );
  expect(baseline).toBeDefined();
  expect((await map.getAttribute("data-strategy-ranked-point-ids"))?.split(",")).toEqual(
    baseline!.displayed_point_ids,
  );
  expect(await markerIds(page)).not.toContain("hvd_113644");
});

test("Chengdu previous and next navigate only the supported sequence", async ({ page }) => {
  await page.goto("/");
  await selectUserSnapshot(page, "chengdu", 553);
  await page.getByRole("button", { name: "下一时期 →" }).click();
  await expect(page.getByTestId("map")).toHaveAttribute("data-snapshot-id", "chengdu:742");
  await expect(page.getByRole("heading", { name: "公元 742 年" })).toBeVisible();
  await page.getByRole("button", { name: "← 上一时期" }).click();
  await expect(page.getByTestId("map")).toHaveAttribute("data-snapshot-id", "chengdu:553");
  await expect(page.getByRole("heading", { name: "公元 553 年" })).toBeVisible();
});

test("Qingdao BCE user interface uses Chinese era formatting without raw negative years", async ({
  page,
}) => {
  await page.goto("/");
  await selectUserSnapshot(page, "qingdao", -201);
  await expect(page.getByRole("heading", { name: "公元前 201 年" })).toBeVisible();
  await expect(page.getByTestId("temporal-context")).toContainText("汉代（西汉）");
  const visibleText = await page.locator("body").innerText();
  expect(visibleText).not.toContain("-201");
  expect(visibleText).not.toMatch(/BCE|\bBC\b/);
});

test("dragging between nodes snaps deterministically and never requests a fake year", async ({
  page,
}) => {
  const requestedSliceYears: number[] = [];
  page.on("request", (request) => {
    const match = request.url().match(/\/slices\/(-?\d+)\.geojson/);
    if (match) requestedSliceYears.push(Number(match[1]));
  });
  await page.goto("/");
  await expect(page.getByTestId("map")).toHaveAttribute("data-snapshot-year", "1911");
  requestedSliceYears.length = 0;

  await page.getByRole("slider", { name: "时间轨道" }).fill("450");
  await expect(page.getByTestId("map")).toHaveAttribute("data-snapshot-year", "1368");
  expect(requestedSliceYears.length).toBeGreaterThan(0);
  expect(requestedSliceYears.every((year) => [14, 220, 1368, 1911].includes(year))).toBe(true);
  expect(requestedSliceYears).not.toContain(450);
});

test("developer controls are isolated and mode changes preserve anchor and exact year", async ({
  page,
}) => {
  await page.goto("/");
  await selectUserSnapshot(page, "chengdu", 742);
  const map = page.getByTestId("map");
  await page.getByRole("button", { name: "开发者模式" }).click();
  await expect(page.getByTestId("developer-controls")).toBeVisible();
  await expect(page.getByRole("radio", { name: "Type + Spatial" })).toBeChecked();
  await expect(page.getByRole("radio", { name: /R2.*最小现代参考/ })).toBeChecked();
  await expect(page.getByRole("definition").filter({ hasText: "chengdu:742" })).toBeVisible();

  await page.getByRole("button", { name: "返回用户模式" }).click();
  await expect(page.getByTestId("developer-controls")).toHaveCount(0);
  await expect(map).toHaveAttribute("data-snapshot-id", "chengdu:742");
  await expect(map).toHaveAttribute("data-display-strategy", "type_diverse_spatial");
  await expect(map).toHaveAttribute("data-reference-mode", "r2_minimal_modern");
});

test("generate seven fixed User Mode temporal screenshots", async ({ page }) => {
  test.skip(!UPDATE_ARTIFACTS, "Set UPDATE_PHASE1_3_ARTIFACTS=1 to refresh evidence.");
  await mkdir(resolve("../artifacts/phase1_3"), { recursive: true });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");

  const cases = [
    { anchor: "beijing", year: 14, slug: "beijing-14" },
    { anchor: "beijing", year: 1368, slug: "beijing-1368" },
    { anchor: "beijing", year: 1911, slug: "beijing-1911" },
    { anchor: "chengdu", year: 553, slug: "chengdu-553" },
    { anchor: "chengdu", year: 742, slug: "chengdu-742" },
    { anchor: "qingdao", year: -201, slug: "qingdao-bce201" },
    { anchor: "qingdao", year: 1911, slug: "qingdao-1911" },
  ];
  for (const item of cases) {
    await selectUserSnapshot(page, item.anchor, item.year);
    const map = page.getByTestId("map");
    await expect(map).toHaveAttribute("data-app-mode", "user");
    await expect(map).toHaveAttribute("data-display-strategy", "type_diverse_spatial");
    await expect(map).toHaveAttribute("data-reference-mode", "r2_minimal_modern");
    await page.waitForTimeout(700);
    await page.screenshot({
      path: resolve(`../artifacts/phase1_3/${item.slug}.png`),
      fullPage: false,
    });
  }
});
