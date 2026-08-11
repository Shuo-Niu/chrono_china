import { access, mkdir } from "node:fs/promises";

import { expect, test, type Page } from "@playwright/test";


const strategies = [
  ["Nearest N", "nearest_n"],
  ["Type Diverse", "type_diverse_distance"],
  ["Type + Spatial", "type_diverse_spatial"],
] as const;

async function markerIds(page: Page): Promise<Array<string | undefined>> {
  return page.locator(".history-marker").evaluateAll((elements) =>
    elements.map((element) => (element as HTMLElement).dataset.tgazId),
  );
}

async function persistentLabelIds(page: Page): Promise<Array<string | undefined>> {
  return page
    .locator(".history-marker[data-has-persistent-label='true']")
    .evaluateAll((elements) =>
      elements.map((element) => (element as HTMLElement).dataset.tgazId),
    );
}

async function viewportState(page: Page) {
  const map = page.getByTestId("map");
  await expect(map).toHaveAttribute("data-map-moving", "false");
  await expect(map).toHaveAttribute("data-map-center", /,/);
  await expect(map).toHaveAttribute("data-map-zoom", /\d/);
  return {
    center: await map.getAttribute("data-map-center"),
    zoom: await map.getAttribute("data-map-zoom"),
  };
}

async function selectSnapshot(page: Page, anchorId: string, yearLabel: string) {
  if ((await page.getByTestId("developer-controls").count()) === 0) {
    await page.getByRole("button", { name: "开发者模式" }).click();
  }
  await page.getByLabel("现代地点").selectOption(anchorId);
  await page.locator(".temporal-node").filter({ hasText: yearLabel }).click();
  await expect(page.getByTestId("slice-status")).toContainText("条有效记录");
  await expect(page.locator(".history-marker").first()).toBeVisible();
}

test("北京 1911 可公平切换三策略且无 label point 仍可打开详情", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  await page.getByRole("button", { name: "开发者模式" }).click();
  await expect(page.getByTestId("slice-status")).toContainText("底层 531 条有效记录");

  const anchorBefore = await page.getByLabel("现代地点").inputValue();
  const periodButton = page.locator(".temporal-node[data-snapshot-year='1911']");
  await expect(periodButton).toHaveAttribute("aria-current", "date");
  const viewportBefore = await viewportState(page);

  await page.getByRole("radio", { name: "Nearest N" }).check();
  await expect(page.locator(".history-marker")).toHaveCount(12);
  const nearestPoints = await markerIds(page);
  const nearestLabels = await persistentLabelIds(page);

  await page.getByRole("radio", { name: "Type Diverse" }).check();
  await expect(page.locator(".history-marker")).toHaveCount(30);
  const diversePoints = await markerIds(page);
  const diverseLabels = await persistentLabelIds(page);
  expect(diversePoints).not.toEqual(nearestPoints);
  expect(diverseLabels).not.toEqual(nearestLabels);
  expect(await page.getByLabel("现代地点").inputValue()).toBe(anchorBefore);
  await expect(periodButton).toHaveAttribute("aria-current", "date");
  expect(await viewportState(page)).toEqual(viewportBefore);
  await expect(page.getByTestId("slice-status")).toContainText(
    "展示 30 个可交互位置 · 当前标注 10 个",
  );

  await page.getByRole("radio", { name: "Type + Spatial" }).check();
  await expect(page.locator(".history-marker")).toHaveCount(30);
  const spatialPoints = await markerIds(page);
  expect(spatialPoints).not.toEqual(diversePoints);
  expect(await viewportState(page)).toEqual(viewportBefore);
  expect(await page.getByLabel("现代地点").inputValue()).toBe(anchorBefore);
  await expect(periodButton).toHaveAttribute("aria-current", "date");

  const unlabeledPoint = page
    .locator(".history-marker[data-has-persistent-label='false']")
    .first();
  await expect(unlabeledPoint).toBeVisible();
  const unlabeledId = await unlabeledPoint.getAttribute("data-tgaz-id");
  await unlabeledPoint.click();
  const detail = page.getByRole("article", { name: "历史地点详情" });
  await expect(detail).toBeVisible();
  await expect(detail).toContainText(unlabeledId!);
  await expect(detail).toContainText("地图不表示它们是现代城市的前身或旧称");
});

test("低密度青岛与中密度成都在三策略下均稳定", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  await page.getByRole("button", { name: "开发者模式" }).click();

  await selectSnapshot(page, "qingdao", "公元前 201 年");
  await expect(page.getByTestId("slice-status")).toContainText("底层 10 条有效记录");
  for (const [label] of strategies) {
    await page.getByRole("radio", { name: label }).check();
    await expect(page.locator(".history-marker")).toHaveCount(10);
    await expect(page.getByRole("alert")).toHaveCount(0);
  }

  await selectSnapshot(page, "chengdu", "公元 553 年");
  await expect(page.getByTestId("slice-status")).toContainText("底层 34 条有效记录");
  await page.getByRole("radio", { name: "Nearest N" }).check();
  await expect(page.locator(".history-marker")).toHaveCount(12);
  for (const label of ["Type Diverse", "Type + Spatial"] as const) {
    await page.getByRole("radio", { name: label }).check();
    await expect(page.locator(".history-marker")).toHaveCount(30);
    await expect(page.getByRole("alert")).toHaveCount(0);
  }
});

test("固定 viewport 生成三组策略对照截图", async ({ page }) => {
  if (process.env.UPDATE_PHASE1_1_ARTIFACTS !== "1") {
    for (const group of ["beijing-1911", "qingdao-bce201", "chengdu-553"]) {
      for (const [, strategy] of strategies) {
        await access(`../artifacts/phase1_1/${group}-${strategy}.png`);
      }
    }
    return;
  }
  await mkdir("../artifacts/phase1_1", { recursive: true });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  await page.getByRole("button", { name: "开发者模式" }).click();

  const groups = [
    { anchor: "beijing", year: "公元 1911 年", slug: "beijing-1911" },
    { anchor: "qingdao", year: "公元前 201 年", slug: "qingdao-bce201" },
    { anchor: "chengdu", year: "公元 553 年", slug: "chengdu-553" },
  ];
  for (const group of groups) {
    await selectSnapshot(page, group.anchor, group.year);
    const fixedViewport = await viewportState(page);
    for (const [label, slug] of strategies) {
      await page.getByRole("radio", { name: label }).check();
      await expect(page.getByTestId("slice-status")).toContainText("当前标注");
      expect(await viewportState(page)).toEqual(fixedViewport);
      await page.screenshot({
        path: `../artifacts/phase1_1/${group.slug}-${slug}.png`,
        fullPage: false,
      });
    }
  }
});
