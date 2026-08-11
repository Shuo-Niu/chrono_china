import { expect, type Page } from "@playwright/test";

import { alignmentMetrics } from "../../src/map/markerAlignment";


const round = (value: number) => Math.round(value * 1000) / 1000;


export type AlignmentMeasurement = {
  tgazId: string;
  longitude: number;
  latitude: number;
  hasPersistentLabel: boolean;
  markerLane: string;
  markerAnchor: string;
  expectedScreenX: number;
  expectedScreenY: number;
  visualCenterX: number;
  visualCenterY: number;
  dx: number;
  dy: number;
  distancePx: number;
  debug: {
    markerRect: { left: number; top: number; width: number; height: number };
    dotRect: { left: number; top: number; width: number; height: number };
    mapRect: { left: number; top: number; width: number; height: number };
    inlineTransform: string;
    computedTransform: string;
  };
};

export async function selectSnapshot(
  page: Page,
  anchorId: string,
  yearLabel: string,
): Promise<void> {
  if ((await page.getByTestId("developer-controls").count()) === 0) {
    await page.getByRole("button", { name: "开发者模式" }).click();
  }
  await page.getByLabel("现代地点").selectOption(anchorId);
  await page.locator(".temporal-node").filter({ hasText: yearLabel }).click();
  await expect(page.getByTestId("slice-status")).toContainText("条有效记录");
  await expect(page.locator(".history-marker").first()).toBeVisible();
  await expect(page.getByRole("radio", { name: "Type + Spatial" })).toBeChecked();
  await expect(page.getByTestId("map")).toHaveAttribute("data-map-moving", "false");
}

export async function setReferenceMode(page: Page, name: RegExp): Promise<void> {
  await page.getByRole("radio", { name }).check();
  await expect(page.getByTestId("map")).toHaveAttribute(
    "data-reference-source-status",
    "ready",
    { timeout: 20_000 },
  );
}

export async function setMapZoom(page: Page, zoom: number): Promise<void> {
  await page.evaluate((nextZoom) => {
    const qaWindow = window as typeof window & {
      __CHRONOCHINA_QA_MAP__?: {
        jumpTo(options: { zoom: number }): void;
      };
    };
    if (!qaWindow.__CHRONOCHINA_QA_MAP__) throw new Error("QA map unavailable");
    qaWindow.__CHRONOCHINA_QA_MAP__.jumpTo({ zoom: nextZoom });
  }, zoom);
  await expect(page.getByTestId("map")).toHaveAttribute("data-map-moving", "false");
}

export async function measureMarker(
  page: Page,
  tgazId: string,
): Promise<AlignmentMeasurement> {
  const raw = await page.evaluate((id) => {
    const qaWindow = window as typeof window & {
      __CHRONOCHINA_QA_MAP__?: {
        project(coordinate: [number, number]): { x: number; y: number };
        getContainer(): HTMLElement;
      };
    };
    const map = qaWindow.__CHRONOCHINA_QA_MAP__;
    if (!map) throw new Error("QA map unavailable");
    const marker = document.querySelector<HTMLElement>(
      `.history-marker[data-tgaz-id="${id}"]`,
    );
    if (!marker) throw new Error(`marker unavailable: ${id}`);
    const dot = marker.querySelector<HTMLElement>(".history-marker__dot");
    if (!dot) throw new Error(`marker geometry unavailable: ${id}`);

    const longitude = Number(marker.dataset.longitude);
    const latitude = Number(marker.dataset.latitude);
    const projected = map.project([longitude, latitude]);
    const mapRect = map.getContainer().getBoundingClientRect();
    const markerRect = marker.getBoundingClientRect();
    const dotRect = dot.getBoundingClientRect();
    const expectedScreenX = mapRect.left + projected.x;
    const expectedScreenY = mapRect.top + projected.y;
    const visualCenterX = dotRect.left + dotRect.width / 2;
    const visualCenterY = dotRect.top + dotRect.height / 2;
    const roundValue = (value: number) => Math.round(value * 1000) / 1000;

    return {
      tgazId: id,
      longitude,
      latitude,
      hasPersistentLabel: marker.dataset.hasPersistentLabel === "true",
      markerLane:
        [...marker.classList].find((name) => name.startsWith("history-marker--lane-")) ??
        "unknown",
      markerAnchor: marker.dataset.markerAnchor ?? "unknown",
      expectedScreenX: roundValue(expectedScreenX),
      expectedScreenY: roundValue(expectedScreenY),
      visualCenterX: roundValue(visualCenterX),
      visualCenterY: roundValue(visualCenterY),
      debug: {
        markerRect: {
          left: roundValue(markerRect.left),
          top: roundValue(markerRect.top),
          width: roundValue(markerRect.width),
          height: roundValue(markerRect.height),
        },
        dotRect: {
          left: roundValue(dotRect.left),
          top: roundValue(dotRect.top),
          width: roundValue(dotRect.width),
          height: roundValue(dotRect.height),
        },
        mapRect: {
          left: roundValue(mapRect.left),
          top: roundValue(mapRect.top),
          width: roundValue(mapRect.width),
          height: roundValue(mapRect.height),
        },
        inlineTransform: marker.style.transform,
        computedTransform: getComputedStyle(marker).transform,
      },
    };
  }, tgazId);
  const metrics = alignmentMetrics(
    { x: raw.expectedScreenX, y: raw.expectedScreenY },
    { x: raw.visualCenterX, y: raw.visualCenterY },
  );
  return {
    ...raw,
    dx: round(metrics.dx),
    dy: round(metrics.dy),
    distancePx: round(metrics.distancePx),
  };
}

export async function markerIds(page: Page): Promise<string[]> {
  return page.locator(".history-marker").evaluateAll((elements) =>
    elements.map((element) => (element as HTMLElement).dataset.tgazId ?? ""),
  );
}
