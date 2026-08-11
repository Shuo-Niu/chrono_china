import { mkdir } from "node:fs/promises";
import { resolve } from "node:path";

import { expect, test, type Page } from "@playwright/test";


const UPDATE_ARTIFACTS = process.env.UPDATE_PHASE1_3_1_ARTIFACTS === "1";

async function selectUserSnapshot(page: Page, anchorId: string, year: number) {
  await page.getByLabel("现代地点").selectOption(anchorId);
  const node = page.locator(`.temporal-node[data-snapshot-year="${year}"]`);
  await expect(node).toBeVisible();
  await node.click();
  await expect(page.getByTestId("map")).toHaveAttribute("data-snapshot-year", String(year));
  await expect(node).toHaveAttribute("aria-current", "date");
  await expect(page.locator(".history-marker").first()).toBeVisible();
}

test("Flow A: User Mode reaches Beijing Ming without era shortcuts", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  const map = page.getByTestId("map");
  await expect(map).toHaveAttribute("data-app-mode", "user");
  await expect(map).toHaveAttribute("data-display-strategy", "type_diverse_spatial");
  await expect(map).toHaveAttribute("data-reference-mode", "r2_minimal_modern");
  await expect(page.getByRole("group", { name: "时期捷径" })).toHaveCount(0);
  await expect(page.getByTestId("developer-controls")).toHaveCount(0);

  await selectUserSnapshot(page, "beijing", 1368);
  await expect(page.getByRole("heading", { name: "公元 1368 年" })).toBeVisible();
  await expect(page.getByTestId("temporal-context")).toContainText("明代");
  await expect(page.getByTestId("snapshot-sequence")).toHaveCount(0);
  await expect(page.getByText(/地图仅显示已收录的代表时期/)).toBeVisible();
  await expect(page.getByTestId("reference-badge")).toHaveText("现代地理参考");
});

test("Flow B: Qingdao earliest state uses Chinese BCE and only real nodes", async ({ page }) => {
  await page.goto("/");
  await selectUserSnapshot(page, "qingdao", -201);
  await expect(page.getByRole("heading", { name: "公元前 201 年" })).toBeVisible();
  await expect(page.getByTestId("temporal-context")).toContainText("汉代（西汉）");
  const years = await page.locator(".temporal-node").evaluateAll((nodes) =>
    nodes.map((node) => Number((node as HTMLElement).dataset.snapshotYear)),
  );
  expect(years).toEqual([-201, 14, 190, 1911]);
  const visibleText = await page.locator("body").innerText();
  expect(visibleText).not.toContain("-201");
  expect(visibleText).not.toMatch(/BCE|\bBC\b/);
  await expect(page.getByRole("group", { name: "时期捷径" })).toHaveCount(0);
});

test("Flow C: Chengdu previous and next remain supported-state navigation", async ({ page }) => {
  await page.goto("/");
  await selectUserSnapshot(page, "chengdu", 553);
  await page.getByRole("button", { name: "下一时期 →" }).click();
  await expect(page.getByTestId("map")).toHaveAttribute("data-snapshot-id", "chengdu:742");
  await expect(page.getByRole("heading", { name: "公元 742 年" })).toBeVisible();
  await page.getByRole("button", { name: "← 上一时期" }).click();
  await expect(page.getByTestId("map")).toHaveAttribute("data-snapshot-id", "chengdu:553");
  await expect(page.getByRole("heading", { name: "公元 553 年" })).toBeVisible();
});

test("Flow D: Developer Mode retains experiments and returns without losing state", async ({
  page,
}) => {
  await page.goto("/");
  await selectUserSnapshot(page, "chengdu", 742);
  const map = page.getByTestId("map");
  const before = {
    anchor: await page.getByLabel("现代地点").inputValue(),
    snapshot: await map.getAttribute("data-snapshot-id"),
    center: await map.getAttribute("data-map-center"),
    zoom: await map.getAttribute("data-map-zoom"),
  };

  await page.locator('.history-marker[data-display-unit-kind="feature"]').first().click();
  const detail = page.getByRole("article", { name: "历史地点详情" });
  await expect(detail).toBeVisible();
  const detailHeading = await detail.getByRole("heading", { level: 2 }).textContent();

  await page.getByRole("button", { name: "开发者模式" }).click();
  await expect(page.getByRole("group", { name: "时期捷径" })).toBeVisible();
  await expect(page.getByRole("radio", { name: "Type + Spatial" })).toBeChecked();
  await expect(page.getByRole("radio", { name: /R2.*最小现代参考/ })).toBeChecked();
  await expect(page.getByText("display position")).toBeVisible();
  await expect(page.getByText("minimum spacing")).toBeVisible();
  await page.getByRole("radio", { name: "Nearest N" }).check();
  await page.getByRole("radio", { name: /R1.*自然地理/ }).check();

  await page.getByRole("button", { name: "返回用户模式" }).click();
  await expect(page.getByRole("group", { name: "时期捷径" })).toHaveCount(0);
  await expect(map).toHaveAttribute("data-app-mode", "user");
  await expect(map).toHaveAttribute("data-display-strategy", "type_diverse_spatial");
  await expect(map).toHaveAttribute("data-reference-mode", "r2_minimal_modern");
  await expect(page.getByLabel("现代地点")).toHaveValue(before.anchor);
  await expect(map).toHaveAttribute("data-snapshot-id", before.snapshot!);
  await expect(map).toHaveAttribute("data-map-center", before.center!);
  await expect(map).toHaveAttribute("data-map-zoom", before.zoom!);
  await expect(detail).toBeVisible();
  await expect(detail.getByRole("heading", { level: 2 })).toHaveText(detailHeading!);
});

test("generate three fixed Phase 1.3.1 User Mode screenshots", async ({ page }) => {
  test.skip(!UPDATE_ARTIFACTS, "Set UPDATE_PHASE1_3_1_ARTIFACTS=1 to refresh evidence.");
  await mkdir(resolve("../artifacts/phase1_3_1"), { recursive: true });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");

  const cases = [
    { anchor: "beijing", year: 1368, slug: "beijing-1368" },
    { anchor: "qingdao", year: -201, slug: "qingdao-bce201" },
    { anchor: "chengdu", year: 553, slug: "chengdu-553" },
  ];
  for (const item of cases) {
    await selectUserSnapshot(page, item.anchor, item.year);
    const map = page.getByTestId("map");
    await expect(map).toHaveAttribute("data-app-mode", "user");
    await expect(map).toHaveAttribute("data-display-strategy", "type_diverse_spatial");
    await expect(map).toHaveAttribute("data-reference-mode", "r2_minimal_modern");
    await expect(page.getByRole("group", { name: "时期捷径" })).toHaveCount(0);
    await expect(page.getByTestId("developer-controls")).toHaveCount(0);
    await expect(page.getByTestId("temporal-rail")).toBeVisible();
    await page.waitForTimeout(700);
    await page.screenshot({
      path: resolve(`../artifacts/phase1_3_1/${item.slug}.png`),
      fullPage: false,
    });
  }
});
