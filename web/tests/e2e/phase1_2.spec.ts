import { mkdir, writeFile } from "node:fs/promises";

import { expect, test, type Page } from "@playwright/test";


const referenceModes = [
  {
    name: /R0.*抽象网格/,
    id: "r0_grid",
    slug: "r0-grid",
    geometryLayers: "0",
    labelLayers: "0",
  },
  {
    name: /R1.*自然地理/,
    id: "r1_physical",
    slug: "r1-physical",
    geometryLayers: "2",
    labelLayers: "0",
  },
  {
    name: /R2.*最小现代参考/,
    id: "r2_minimal_modern",
    slug: "r2-minimal-modern",
    geometryLayers: "3",
    labelLayers: "1",
  },
  {
    name: /R3.*现代行政参考/,
    id: "r3_modern_admin",
    slug: "r3-modern-admin",
    geometryLayers: "3",
    labelLayers: "1",
  },
] as const;

async function markerIds(page: Page): Promise<string[]> {
  return page.locator(".history-marker").evaluateAll((elements) =>
    elements.map((element) => (element as HTMLElement).dataset.tgazId ?? ""),
  );
}

async function viewportState(page: Page) {
  const map = page.getByTestId("map");
  await expect(map).toHaveAttribute("data-map-moving", "false");
  return {
    center: await map.getAttribute("data-map-center"),
    zoom: await map.getAttribute("data-map-zoom"),
  };
}

async function setReferenceMode(
  page: Page,
  mode: (typeof referenceModes)[number],
) {
  const map = page.getByTestId("map");
  await page.getByRole("radio", { name: mode.name }).check();
  await expect(map).toHaveAttribute("data-reference-mode", mode.id);
  await expect(map).toHaveAttribute(
    "data-reference-geometry-layer-count",
    mode.geometryLayers,
  );
  await expect(map).toHaveAttribute(
    "data-reference-label-layer-count",
    mode.labelLayers,
  );
  if (mode.id === "r0_grid") {
    await expect(map).toHaveAttribute("data-reference-source-status", "off");
  } else {
    await expect(map).toHaveAttribute("data-reference-source-status", "ready", {
      timeout: 20_000,
    });
  }
}

async function selectSnapshot(page: Page, anchorId: string, yearLabel: string) {
  if ((await page.getByTestId("developer-controls").count()) === 0) {
    await page.getByRole("button", { name: "开发者模式" }).click();
  }
  await page.getByLabel("现代地点").selectOption(anchorId);
  await page.locator(".temporal-node").filter({ hasText: yearLabel }).click();
  await expect(page.getByTestId("slice-status")).toContainText("条有效记录");
  await expect(page.locator(".history-marker").first()).toBeVisible();
  await expect(page.getByRole("radio", { name: "Type + Spatial" })).toBeChecked();
  await viewportState(page);
}

test("北京 1911 在 R0–R3 间保持 Strategy C、视口、点集与详情", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  await selectSnapshot(page, "beijing", "公元 1911 年");

  const beforeIds = await markerIds(page);
  const beforeViewport = await viewportState(page);
  const point = page.locator(".history-marker[data-has-persistent-label='false']").first();
  const selectedId = await point.getAttribute("data-tgaz-id");
  await point.click();
  const detail = page.getByRole("article", { name: "历史地点详情" });
  await expect(detail).toBeVisible();
  await expect(detail).toContainText(selectedId!);

  for (const mode of referenceModes) {
    await setReferenceMode(page, mode);
    expect(await markerIds(page)).toEqual(beforeIds);
    expect(await viewportState(page)).toEqual(beforeViewport);
    expect(await page.getByLabel("现代地点").inputValue()).toBe("beijing");
    await expect(page.locator(".temporal-node[data-snapshot-year='1911']")).toHaveAttribute(
      "aria-current",
      "date",
    );
    await expect(page.getByRole("radio", { name: "Type + Spatial" })).toBeChecked();
    await expect(detail).toContainText(selectedId!);
  }
});

test("青岛 BCE 201 参考层 smoke test 保持真实点集", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  await selectSnapshot(page, "qingdao", "公元前 201 年");
  const beforeIds = await markerIds(page);
  expect(beforeIds).toHaveLength(10);

  await setReferenceMode(page, referenceModes[3]);
  await expect(page.getByTestId("reference-badge")).toContainText(
    "现代行政参考 · 非历史边界",
  );
  expect(await markerIds(page)).toEqual(beforeIds);
  await expect(page.getByRole("alert")).toHaveCount(0);
  await setReferenceMode(page, referenceModes[0]);
  expect(await markerIds(page)).toEqual(beforeIds);
});

test("固定 1440×900 生成 3 snapshots × 4 reference modes", async ({ page }) => {
  test.setTimeout(90_000);
  await mkdir("../artifacts/phase1_2", { recursive: true });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");

  const snapshots = [
    { anchor: "beijing", year: "公元 1911 年", yearValue: 1911, slug: "beijing-1911" },
    { anchor: "chengdu", year: "公元 553 年", yearValue: 553, slug: "chengdu-553" },
    { anchor: "qingdao", year: "公元前 201 年", yearValue: -201, slug: "qingdao-bce201" },
  ] as const;
  const metrics: Array<Record<string, unknown>> = [];

  for (const snapshot of snapshots) {
    await selectSnapshot(page, snapshot.anchor, snapshot.year);
    await setReferenceMode(page, referenceModes[0]);
    const fixedIds = await markerIds(page);
    const fixedViewport = await viewportState(page);

    for (const mode of referenceModes) {
      await setReferenceMode(page, mode);
      expect(await markerIds(page)).toEqual(fixedIds);
      expect(await viewportState(page)).toEqual(fixedViewport);
      await page.waitForTimeout(mode.id === "r0_grid" ? 100 : 650);
      const map = page.getByTestId("map");
      metrics.push({
        anchor: snapshot.anchor,
        year: snapshot.yearValue,
        reference_mode: mode.id,
        display_strategy: await map.getAttribute("data-display-strategy"),
        historical_point_count: Number(
          await map.getAttribute("data-historical-point-count"),
        ),
        historical_displayed_label_count: Number(
          await map.getAttribute("data-historical-label-count"),
        ),
        historical_label_collision_count: Number(
          await map.getAttribute("data-historical-label-collision-count"),
        ),
        collision_metric_kind: await map.getAttribute(
          "data-historical-label-collision-metric",
        ),
        modern_reference_geometry_layer_count: Number(mode.geometryLayers),
        modern_reference_label_layer_count: Number(mode.labelLayers),
        modern_reference_label_count: null,
        modern_reference_label_count_note:
          "not_computed_for_vector_tile_canvas",
        historical_labels_hidden_by_modern_reference: 0,
        modern_labels_hidden_by_historical_layer: null,
        modern_labels_hidden_note:
          "not_computed_across_map_canvas_and_dom_markers",
        anchor_collision_hidden_historical_label_count: Number(
          await map.getAttribute("data-anchor-hidden-label-count"),
        ),
        reference_source_status: await map.getAttribute(
          "data-reference-source-status",
        ),
        map_center: fixedViewport.center,
        map_zoom: fixedViewport.zoom,
        historical_point_ids: fixedIds,
      });
      await page.screenshot({
        path: `../artifacts/phase1_2/${snapshot.slug}-${mode.slug}.png`,
        fullPage: false,
      });
    }
  }

  await writeFile(
    "../artifacts/phase1_2/metrics.json",
    `${JSON.stringify({ generated_by: "phase1_2.spec.ts", cases: metrics }, null, 2)}\n`,
    "utf8",
  );
});
