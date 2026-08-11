import { expect, test } from "@playwright/test";


test("北京可切换真实代表时期并打开来源完整的详情卡", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByLabel("北京（现代）")).toHaveCount(0);
  await expect(page.getByTestId("slice-status")).toContainText("个可交互历史位置");
  const beforeIds = await page.locator(".history-marker").evaluateAll((elements) =>
    elements.map((element) => (element as HTMLElement).dataset.tgazId),
  );
  expect(beforeIds.length).toBeGreaterThan(0);

  await page.getByRole("button", { name: "公元 14 年" }).click();
  await expect(page.getByTestId("slice-status")).toContainText("个可交互历史位置");
  const afterIds = await page.locator(".history-marker").evaluateAll((elements) =>
    elements.map((element) => (element as HTMLElement).dataset.tgazId),
  );
  expect(afterIds.length).toBeGreaterThan(0);
  expect(afterIds).not.toEqual(beforeIds);

  await page.locator('.history-marker[data-display-unit-kind="feature"]').first().click();
  const card = page.getByRole("article", { name: "历史地点详情" });
  await expect(card).toBeVisible();
  await expect(card).toContainText("公元 14 年");
  await expect(card).toContainText("CC BY-NC 4.0");
  await expect(card).toContainText(/hvd_\d+/);
  await expect(card).toContainText("地图不表示它们是现代城市的前身或旧称");
  await expect(card.getByRole("link", { name: /TGAZ canonical record/ })).toHaveAttribute(
    "href",
    /tgaz\.fudan\.edu\.cn/,
  );
});

test("五个固定锚点均能载入真实默认切片且页面不崩溃", async ({ page }) => {
  const anchors = [
    ["beijing", "北京"],
    ["xian", "西安"],
    ["chengdu", "成都"],
    ["qingdao", "青岛"],
    ["qufu", "曲阜"],
  ] as const;

  await page.goto("/");
  for (const [anchorId, displayName] of anchors) {
    await page.getByLabel("现代地点").selectOption(anchorId);
    await expect(page.getByLabel(`${displayName}（现代）`)).toHaveCount(0);
    await expect(page.getByTestId("slice-status")).toContainText("个可交互历史位置");
    await expect(page.locator(".history-marker").first()).toBeVisible();
    await expect(page.getByRole("alert")).toHaveCount(0);
  }
});
