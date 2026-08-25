const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { _electron: electron } = require("playwright");

const projectRoot = path.resolve(__dirname, "..", "..");
const sourceApp = path.join(projectRoot, "artifacts", "phase1_5", "windows", "win-unpacked");
const smokeRoot = path.join(os.tmpdir(), "ChronoChina User Smoke Test");
const copiedApp = path.join(smokeRoot, "Application Files");
const workingDirectory = path.join(smokeRoot, "Working Directory With Spaces");
const executable = path.join(copiedApp, "ChronoChina.exe");

function yearToOrdinal(year) {
  if (year === 0) throw new Error("year zero is unsupported");
  return year < 0 ? year : year - 1;
}

async function setYear(page, year) {
  await page.getByTestId("timeline-range").evaluate((element, ordinal) => {
    const input = element;
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(
      input,
      String(ordinal),
    );
    input.dispatchEvent(new Event("input", { bubbles: true }));
  }, yearToOrdinal(year));
  await page.getByTestId("map").waitFor({ state: "visible" });
  await page.waitForFunction(
    (value) => document.querySelector('[data-testid="map"]')?.getAttribute("data-query-result-year") === value,
    String(year),
  );
}

async function launchAndVerify(reopen = false) {
  const application = await electron.launch({
    executablePath: executable,
    cwd: workingDirectory,
    env: { ...process.env, CHRONOCHINA_PACKAGED_SMOKE: "1" },
    timeout: 60_000,
  });
  try {
    const page = await application.firstWindow({ timeout: 60_000 });
    const requests = [];
    page.on("request", (request) => requests.push(request.url()));
    const failedRequests = [];
    page.on("requestfailed", (request) => {
      failedRequests.push(`${request.url()} :: ${request.failure()?.errorText ?? "unknown"}`);
    });
    const errorResponses = [];
    page.on("response", (response) => {
      if (response.status() >= 400) errorResponses.push(`${response.status()} ${response.url()}`);
    });
    const errors = [];
    page.on("pageerror", (error) => errors.push(String(error)));
    const consoleMessages = [];
    page.on("console", (message) => consoleMessages.push(`${message.type()}: ${message.text()}`));

    await page.getByTestId("map").waitFor({ state: "visible", timeout: 60_000 });
    await page.waitForTimeout(3_000);
    const initialReferenceState = await page.evaluate(() => {
      const map = window.__CHRONOCHINA_QA_MAP__;
      if (!map) return null;
      return {
        sourceLoaded: map.isSourceLoaded("chronochina-offline-reference"),
        tilesLoaded: map.areTilesLoaded(),
        sourceFeatureCount: map.querySourceFeatures("chronochina-offline-reference").length,
        renderedWaterCount: map.queryRenderedFeatures({ layers: ["reference-water"] }).length,
        waterVisibility: map.getLayoutProperty("reference-water", "visibility"),
      };
    });
    await page.waitForFunction(() => {
      const map = document.querySelector('[data-testid="map"]');
      return map?.getAttribute("data-explore-index-status") === "ready" &&
        map?.getAttribute("data-coverage-metadata-status") === "ready" &&
        map?.getAttribute("data-institution-notes-status") === "ready" &&
        Number(map?.getAttribute("data-historical-point-count")) > 0;
    }, null, { timeout: 60_000 });

    assert.equal(new URL(page.url()).protocol, "chronochina:");
    assert.equal(
      requests.some((url) => /^https?:\/\/(localhost|127\.0\.0\.1)(:|\/)/.test(url)),
      false,
      "packaged application must not request a development server",
    );

    await page.waitForFunction(() => {
      const status = document.querySelector('[data-testid="map"]')
        ?.getAttribute("data-reference-source-status");
      return status === "ready" || status === "degraded" || status === "failed";
    }, null, { timeout: 20_000 });
    const referenceStatus = await page.getByTestId("map").getAttribute("data-reference-source-status");
    const canvasState = await page.evaluate(() => {
      const canvas = document.querySelector(".maplibregl-canvas");
      return canvas ? {
        width: canvas.width,
        height: canvas.height,
        clientWidth: canvas.clientWidth,
        clientHeight: canvas.clientHeight,
        webgl2: Boolean(canvas.getContext("webgl2")),
      } : null;
    });
    const maplibreState = await page.evaluate(() => {
      const map = window.__CHRONOCHINA_QA_MAP__;
      if (!map) return null;
      const source = map.getSource("chronochina-offline-reference");
      return {
        sourceExists: Boolean(source),
        sourceLoaded: map.isSourceLoaded("chronochina-offline-reference"),
        tilesLoaded: map.areTilesLoaded(),
        styleSource: map.getStyle().sources["chronochina-offline-reference"],
        waterVisibility: map.getLayoutProperty("reference-water", "visibility"),
        sourceFeatureCount: map.querySourceFeatures("chronochina-offline-reference").length,
      };
    });    assert.equal(referenceStatus, "ready", JSON.stringify({
      referenceStatus,
      networkRequests: requests.filter((url) => /^https?:/.test(url)),
      failedRequests,
      errorResponses,
      consoleMessages,
      lastError: await page.getByTestId("map").getAttribute("data-reference-last-error"),





      viewportBbox: await page.getByTestId("map").getAttribute("data-viewport-bbox"),
      mapCenter: await page.getByTestId("map").getAttribute("data-map-center"),
      mapZoom: await page.getByTestId("map").getAttribute("data-map-zoom"),
      canvasState,
      maplibreState,
      initialReferenceState,
      failedCriticalLayers: await page.getByTestId("map")
        .getAttribute("data-reference-failed-critical-layers"),
    }));
    assert.equal(maplibreState.sourceExists, true);
    assert.match(maplibreState.styleSource.url, /^pmtiles:\/\/chronochina:\/\/app\/reference\/china_z9\.pmtiles$/);
    assert.equal(
      requests.some((url) => /^https?:/.test(url)),
      false,
      "packaged application must render its basemap without runtime network requests",
    );
    assert.equal(await page.getByTestId("map").getAttribute("data-snapshot-year"), "1911");
    assert.equal(
      await page.getByTestId("map").getAttribute("data-enabled-display-tiers"),
      "province",
    );
    const initialBounds = (await page.getByTestId("map").getAttribute("data-viewport-bbox"))
      .split(",").map(Number);
    assert.ok(
      initialBounds[0] <= 73 && initialBounds[1] <= 18 &&
        initialBounds[2] >= 135 && initialBounds[3] >= 54,
      `initial viewport must contain China bounds: ${initialBounds.join(",")}`,
    );

    if (!reopen) {
      await page.screenshot({
        path: path.join(projectRoot, "artifacts", "phase1_5", "portable-default.png"),
        fullPage: true,
      });
    }

    if (!reopen) {
      await setYear(page, 1911);
      const highDensity = Number(await page.getByTestId("map").getAttribute("data-explore-active-record-count"));
      assert.ok(highDensity > 0, "1911 viewport must contain real historical records");

      const settlement = page.locator('[data-legend-tier="unclassified"]');
      assert.equal(await settlement.count(), 0, "settlement controls must stay hidden in User Mode");
      assert.equal((await page.getByTestId("layer-switcher").innerText()).includes("村镇、亭"), false);
      await setYear(page, 1820);
      assert.equal(
        (await page.getByTestId("map").getAttribute("data-historical-point-ids")).includes("hvd_15476"),
        false,
        "hidden settlement snapshots must not render",
      );
      await setYear(page, 1911);

      const county = page.locator('[data-legend-tier="county"]');
      assert.equal(await county.getAttribute("aria-pressed"), "false");
      await county.click();
      assert.equal(await county.getAttribute("aria-pressed"), "true");
      await county.click();
      assert.equal(await county.getAttribute("aria-pressed"), "false");

      await page.getByRole("button", { name: "仅点" }).click();
      assert.equal(await page.getByTestId("map").getAttribute("data-historical-display-mode"), "point_only");
      await page.getByRole("button", { name: "点/标签" }).click();
      assert.equal(await page.getByTestId("map").getAttribute("data-historical-display-mode"), "point_label");

      const historicalStateBeforeBasemapSwitch = {
        year: await page.getByTestId("map").getAttribute("data-snapshot-year"),
        pointIds: await page.getByTestId("map").getAttribute("data-historical-point-ids"),
        tiers: await page.getByTestId("map").getAttribute("data-enabled-display-tiers"),
        bbox: await page.getByTestId("map").getAttribute("data-viewport-bbox"),
        pointCount: Number(
          await page.getByTestId("map").getAttribute("data-historical-point-count"),
        ),
      };
      await page.getByRole("button", { name: "丰富" }).click();
      await page.waitForFunction(() =>
        document.querySelector('[data-testid="map"]')
          ?.getAttribute("data-reference-effective-mode") === "r4_color_geography",
      null, { timeout: 30_000 });
      assert.deepEqual({
        year: await page.getByTestId("map").getAttribute("data-snapshot-year"),
        pointIds: await page.getByTestId("map").getAttribute("data-historical-point-ids"),
        tiers: await page.getByTestId("map").getAttribute("data-enabled-display-tiers"),
        bbox: await page.getByTestId("map").getAttribute("data-viewport-bbox"),
        pointCount: Number(
          await page.getByTestId("map").getAttribute("data-historical-point-count"),
        ),
      }, historicalStateBeforeBasemapSwitch);

      const previousSequence = Number(
        await page.getByTestId("map").getAttribute("data-explore-query-sequence"),
      );
      await page.evaluate(() => {
        const map = window.__CHRONOCHINA_QA_MAP__;
        map.jumpTo({ center: [119.32158, 26.07395], zoom: 11 });
        map.fire("moveend");
      });
      await page.waitForFunction(
        (sequence) => Number(
          document.querySelector('[data-testid="map"]')?.getAttribute("data-explore-query-sequence"),
        ) > sequence,
        previousSequence,
      );
      const marker = page.locator('[data-member-ids*="hvd_30012"]').first();
      await marker.waitFor({ state: "visible" });
      await marker.click();
      const colocatedMember = page.locator('[data-colocated-member-id="hvd_30012"]');
      if (await colocatedMember.isVisible()) await colocatedMember.click();
      await page.locator(".detail-card,.colocated-card").waitFor({ state: "visible" });
      const institutionNote = page.getByTestId("institution-note");
      await institutionNote.waitFor({ state: "visible" });
      assert.match(await institutionNote.innerText(), /清末的省/);
      assert.doesNotMatch(await institutionNote.innerText(), /清末地方制度并非整齐的单一层级/);
      assert.deepEqual(errors, []);
    }

    return await application.evaluate(({ app }) => app.getPath("logs"));
  } finally {
    await application.close();
  }
}

async function main() {
  const sourceExecutable = path.join(sourceApp, "ChronoChina.exe");
  if (!fs.existsSync(sourceExecutable)) {
    throw new Error(`missing packaged executable: ${sourceExecutable}`);
  }
  fs.rmSync(smokeRoot, { recursive: true, force: true });
  fs.mkdirSync(workingDirectory, { recursive: true });
  fs.cpSync(sourceApp, copiedApp, { recursive: true });

  const logDirectory = await launchAndVerify(false);
  await launchAndVerify(true);
  const logFile = path.join(logDirectory, "main.log");
  assert.equal(fs.existsSync(logFile), true, "packaged application must create a support log");
  const log = fs.readFileSync(logFile, "utf8");
  assert.match(log, /application_start/);
  assert.doesNotMatch(log, /D:\\VibeCoding|C:\\Users\\shuon/i);

  process.stdout.write(`${JSON.stringify({
    status: "PASS",
    executable,
    copied_path: copiedApp,
    working_directory: workingDirectory,
    close_reopen: "PASS",
    dev_server_dependency: false,
    bundled_basemap_requires_network: false,
    log_file_created: true,
  }, null, 2)}\n`);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
