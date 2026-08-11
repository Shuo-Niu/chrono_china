import { mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { resolve } from "node:path";

import { expect, test, type Page } from "@playwright/test";

const UPDATE_ARTIFACTS = process.env.UPDATE_PHASE1_3_1C_TRACK_A === "1";
const snapshots: Record<string, number[]> = {
  beijing: [14, 220, 1368, 1911],
  xian: [23, 557, 627, 1911],
  chengdu: [14, 553, 742, 1911],
  qingdao: [-201, 14, 190, 1911],
  qufu: [14, 556, 596, 1911],
};
const zooms = [
  { band: "low", zoom: 6.2 },
  { band: "medium", zoom: 7.4 },
  { band: "high", zoom: 9.2 },
  { band: "maximum", zoom: 11 },
];

async function selectSnapshot(page: Page, anchor: string, year: number) {
  await page.getByLabel("现代地点").selectOption(anchor);
  const node = page.locator(`.temporal-node[data-snapshot-year="${year}"]`);
  await expect(node).toBeVisible();
  await node.click();
  await expect(page.getByTestId("map")).toHaveAttribute("data-snapshot-year", String(year));
}

async function setZoom(page: Page, zoom: number) {
  await page.evaluate((nextZoom) => {
    const qaMap = (window as typeof window & {
      __CHRONOCHINA_QA_MAP__?: { jumpTo(options: { zoom: number }): void };
    }).__CHRONOCHINA_QA_MAP__;
    if (!qaMap) throw new Error("QA map unavailable");
    qaMap.jumpTo({ zoom: nextZoom });
  }, zoom);
  await expect(page.getByTestId("map")).toHaveAttribute(
    "data-map-zoom",
    new RegExp(`^${zoom.toFixed(1)}`),
  );
}

function csv(value: string | null): string[] {
  return (value ?? "").split(",").filter(Boolean);
}

async function semanticObservation(page: Page, anchor: string, year: number, band: string, zoom: number) {
  const map = page.getByTestId("map");
  const pointCount = Number(await map.getAttribute("data-historical-point-count"));
  const labelCount = Number(await map.getAttribute("data-historical-label-count"));
  const markerState = await page.locator(".history-marker").evaluateAll((nodes) =>
    nodes.map((node) => ({
      unitId: (node as HTMLElement).dataset.displayUnitId,
      family: (node as HTMLElement).dataset.displayFamily,
      hasPersistentLabel: (node as HTMLElement).dataset.hasPersistentLabel,
      memberIds: (node as HTMLElement).dataset.memberIds?.split(",").filter(Boolean),
    })),
  );
  const legendFamilies = await page.locator("[data-legend-family]").evaluateAll((nodes) =>
    nodes.map((node) => (node as HTMLElement).dataset.legendFamily),
  );
  return {
    anchor,
    year,
    band,
    zoom,
    activeFamilies: csv(await map.getAttribute("data-active-display-families")),
    eligibleFamilies: csv(await map.getAttribute("data-eligible-display-families")),
    visibleFamilies: csv(await map.getAttribute("data-visible-display-families")),
    visibleUnitCount: pointCount,
    visibleLabelCount: labelCount,
    semanticHiddenFeatureCount: Number(await map.getAttribute("data-semantic-hidden-feature-count")),
    collisionHiddenUnitCount: Number(await map.getAttribute("data-historical-label-collision-count")),
    colocatedGroupCount: Number(await map.getAttribute("data-co-located-group-count")),
    markerState,
    legendFamilies,
  };
}

test("Track A Flow A: semantic zoom uses point-label units and registry-derived legend", async ({ page }) => {
  await page.goto("/");
  await selectSnapshot(page, "beijing", 1911);
  for (const { band, zoom } of zooms) {
    await setZoom(page, zoom);
    const observation = await semanticObservation(page, "beijing", 1911, band, zoom);
    expect(observation.visibleUnitCount).toBe(observation.visibleLabelCount);
    expect(observation.markerState.every((item) => item.hasPersistentLabel === "true")).toBe(true);
    expect([...observation.legendFamilies].sort()).toEqual([...observation.visibleFamilies].sort());
    if (band === "low") {
      expect(observation.eligibleFamilies).not.toContain("county");
      expect(observation.eligibleFamilies).not.toContain("settlement");
    }
    if (band === "high" || band === "maximum") {
      expect(observation.eligibleFamilies).toContain("settlement");
    }
  }
});

test("Track A Flow B: Xian 23 exact-coordinate records open as separate group members", async ({ page }) => {
  await page.goto("/");
  await selectSnapshot(page, "xian", 23);
  await page.evaluate(() => {
    (window as typeof window & {
      __CHRONOCHINA_QA_MAP__?: { jumpTo(options: { center: [number, number]; zoom: number }): void };
    }).__CHRONOCHINA_QA_MAP__?.jumpTo({ center: [109.06952, 34.36034], zoom: 11 });
  });
  const group = page.locator('.history-marker[data-display-unit-kind="colocated_group"]')
    .filter({ has: page.locator(".history-marker__count") })
    .filter({ hasText: "京兆郡" });
  await expect(group).toHaveCount(1);
  await expect(group).toHaveAttribute("data-member-ids", /hvd_112122/);
  await expect(group).toHaveAttribute("data-member-ids", /hvd_112123/);
  await expect(group).toHaveAttribute("data-member-ids", /hvd_112126/);
  await group.click();
  const card = page.getByRole("article", { name: "同址历史记录" });
  await expect(card).toContainText("只组合显示，不合并 ID");
  for (const id of ["hvd_112122", "hvd_112123", "hvd_112126"]) {
    await expect(card.locator(`[data-colocated-member-id="${id}"]`)).toBeVisible();
  }
  await card.locator('[data-colocated-member-id="hvd_112123"]').click();
  await expect(page.getByRole("article", { name: "历史地点详情" })).toContainText("hvd_112123");
});

test("Track A Flow C: a long canonical source note is fully reachable", async ({ page }) => {
  await page.goto("/");
  await selectSnapshot(page, "xian", 627);
  await page.evaluate(() => {
    (window as typeof window & {
      __CHRONOCHINA_QA_MAP__?: { jumpTo(options: { center: [number, number]; zoom: number }): void };
    }).__CHRONOCHINA_QA_MAP__?.jumpTo({ center: [108.6039, 34.11182], zoom: 11 });
  });
  const marker = page.locator('.history-marker[data-member-ids~="hvd_70747"], .history-marker[data-member-ids="hvd_70747"]');
  await expect(marker).toHaveCount(1);
  await marker.click();
  const note = page.getByTestId("source-note-full");
  await expect(note).toBeVisible();
  expect((await note.textContent())!.length).toBeGreaterThan(260);
  await expect(page.getByText("查看未经改写的源文本")).toBeVisible();
});

test("capture Track A semantic zoom, co-location, source fidelity, and screenshots", async ({ page }) => {
  test.setTimeout(180_000);
  test.skip(!UPDATE_ARTIFACTS, "Set UPDATE_PHASE1_3_1C_TRACK_A=1 to refresh evidence.");
  const artifactRoot = resolve("../artifacts/phase1_3_1c/track_a");
  await rm(artifactRoot, { recursive: true, force: true });
  await mkdir(artifactRoot, { recursive: true });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");

  const observations = [];
  for (const target of [
    { anchor: "beijing", year: 1911 },
    { anchor: "chengdu", year: 553 },
    { anchor: "xian", year: 23 },
  ]) {
    await selectSnapshot(page, target.anchor, target.year);
    for (const { band, zoom } of zooms) {
      await setZoom(page, zoom);
      observations.push(await semanticObservation(page, target.anchor, target.year, band, zoom));
    }
  }
  await writeFile(
    resolve("../data/qa/phase1_3_1c_semantic_zoom.json"),
    `${JSON.stringify({
      generatedAt: new Date().toISOString(),
      policy: "family eligibility, then exact-coordinate grouping, then whole-unit collision",
      cases: observations,
    }, null, 2)}\n`,
    "utf8",
  );
  const markdown = [
    "# Phase 1.3.1c semantic zoom QA",
    "",
    "User Mode always treats a point and its label as one display unit.",
    "",
    "| Anchor | Year | Band | Zoom | Eligible families | Visible units | Semantic hidden | Collision hidden |",
    "| --- | ---: | --- | ---: | --- | ---: | ---: | ---: |",
    ...observations.map((item) =>
      `| ${item.anchor} | ${item.year} | ${item.band} | ${item.zoom} | ${item.eligibleFamilies.join(", ")} | ${item.visibleUnitCount} | ${item.semanticHiddenFeatureCount} | ${item.collisionHiddenUnitCount} |`,
    ),
  ];
  await writeFile(
    resolve("../data/qa/phase1_3_1c_semantic_zoom.md"),
    `${markdown.join("\n")}\n`,
    "utf8",
  );

  const groups = [];
  for (const [anchor, years] of Object.entries(snapshots)) {
    for (const year of years) {
      const path = resolve(`../data/processed/phase1_1/anchors/${anchor}/slices/${year}.geojson`);
      const collection = JSON.parse(await readFile(path, "utf8"));
      const byCoordinate = new Map<string, typeof collection.features>();
      for (const feature of collection.features) {
        const key = feature.geometry.coordinates.join(":");
        byCoordinate.set(key, [...(byCoordinate.get(key) ?? []), feature]);
      }
      for (const [coordinateKey, members] of byCoordinate) {
        if (members.length < 2) continue;
        groups.push({
          anchor,
          year,
          coordinate: coordinateKey.split(":").map(Number),
          memberCount: members.length,
          members: members.map((feature: any) => ({
            tgazId: feature.properties.tgaz_id,
            name: feature.properties.name,
            featureType: feature.properties.feature_type,
            validFrom: feature.properties.valid_from,
            validTo: feature.properties.valid_to,
            parentName: feature.properties.parent_name,
            coordinate: feature.geometry.coordinates,
          })),
        });
      }
    }
  }
  const xianTarget = groups.find((group) =>
    group.anchor === "xian" && group.year === 23 &&
    ["hvd_112122", "hvd_112123", "hvd_112126"].every((id) =>
      group.members.some((member: any) => member.tgazId === id),
    ),
  );
  await writeFile(
    resolve("../data/qa/phase1_3_1c_colocated_groups.json"),
    `${JSON.stringify({
      generatedAt: new Date().toISOString(),
      groupingPolicy: "exact longitude and latitude equality; no tolerance",
      identityPolicy: "display grouping only; IDs, coordinates, and entity identity remain unchanged",
      groupCount: groups.length,
      xian23TargetFound: Boolean(xianTarget),
      xian23Target: xianTarget,
      groups,
    }, null, 2)}\n`,
    "utf8",
  );

  for (const { band, zoom } of zooms.filter(({ band }) => band === "low" || band === "high")) {
    await selectSnapshot(page, "beijing", 1911);
    await setZoom(page, zoom);
    await page.screenshot({ path: resolve(artifactRoot, `beijing-1911-${band}.png`) });
  }
  for (const { band, zoom } of zooms.filter(({ band }) => band === "low" || band === "high")) {
    await selectSnapshot(page, "chengdu", 553);
    await setZoom(page, zoom);
    await page.screenshot({ path: resolve(artifactRoot, `chengdu-553-${band}.png`) });
  }
  await selectSnapshot(page, "xian", 23);
  await page.evaluate(() => {
    (window as typeof window & {
      __CHRONOCHINA_QA_MAP__?: { jumpTo(options: { center: [number, number]; zoom: number }): void };
    }).__CHRONOCHINA_QA_MAP__?.jumpTo({ center: [109.06952, 34.36034], zoom: 11 });
  });
  await page.screenshot({ path: resolve(artifactRoot, "xian-23-colocated-marker.png") });
  await page.locator('.history-marker[data-display-unit-kind="colocated_group"]').filter({ hasText: "京兆郡" }).click();
  await page.screenshot({ path: resolve(artifactRoot, "xian-23-colocated-list.png") });
  await selectSnapshot(page, "xian", 627);
  await page.evaluate(() => {
    (window as typeof window & {
      __CHRONOCHINA_QA_MAP__?: { jumpTo(options: { center: [number, number]; zoom: number }): void };
    }).__CHRONOCHINA_QA_MAP__?.jumpTo({ center: [108.6039, 34.11182], zoom: 11 });
  });
  await page.locator('.history-marker[data-member-ids="hvd_70747"]').click();
  await page.screenshot({ path: resolve(artifactRoot, "xian-627-full-source.png") });
});
