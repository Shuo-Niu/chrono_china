import { mkdir, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";

import { test } from "@playwright/test";

import {
  measureMarker,
  selectSnapshot,
  setReferenceMode,
} from "./marker-alignment-helpers";


const output = process.env.ALIGNMENT_CAPTURE_OUTPUT;

test("capture Qingdao BCE201 marker alignment metrics", async ({ page }) => {
  test.skip(!output, "Set ALIGNMENT_CAPTURE_OUTPUT to write an explicit QA capture.");

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  await selectSnapshot(page, "qingdao", "公元前 201 年");
  await setReferenceMode(page, /R1.*自然地理/);

  const measurements = await Promise.all([
    measureMarker(page, "hvd_112389"),
    measureMarker(page, "hvd_85344"),
  ]);
  const payload = {
    phase: process.env.ALIGNMENT_CAPTURE_PHASE ?? "unspecified",
    generatedAt: new Date().toISOString(),
    anchor: "qingdao",
    year: -201,
    referenceMode: "r1_physical",
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: await page.evaluate(() => window.devicePixelRatio),
    measurements,
  };
  const path = resolve(output!);
  await mkdir(dirname(path), { recursive: true });
  await writeFile(path, `${JSON.stringify(payload, null, 2)}\n`, "utf8");
});
